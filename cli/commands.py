"""管理 CLI：建账号 / 重置密码 / 停用 / 重置额度。

全部走 provisioning 的 BYPASSRLS 连接，不依赖请求上下文。
"""
import click
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from flask import current_app
from sqlalchemy import create_engine, text

from app.extensions import db
from app.models.user import User
from app.services import provisioning
from app.services import llm
from app.services import words as words_svc
from app.services import notifications
from config import INSECURE_SECRET_DEFAULT, is_configured, validate_fernet_key


def register_commands(app):

    @app.cli.command("create-user")
    @click.option("--email", required=True)
    @click.option("--name", required=True)
    @click.option("--admin", is_flag=True, default=False)
    @click.option("--tz", default="Asia/Shanghai", help="用户时区，默认 Asia/Shanghai")
    @click.option("--language", "languages", multiple=True,
                  help="预设正在学的语言，可重复传，如 --language zh --language fr")
    @click.option("--feedback-language", default="zh",
                  help="AI 解释和点评语言，默认 zh；法国朋友可用 fr")
    @click.option("--password", default=None, help="指定初始密码；不传则随机生成")
    def create_user(email, name, admin, tz, languages, feedback_language, password):
        """建账号（一事务建 User + UserSettings + UserQuota）。"""
        try:
            uid, pw = provisioning.create_user_with_defaults(
                email, name, admin=admin, timezone=tz, password=password,
                learning_languages=list(languages),
                feedback_language=feedback_language,
            )
        except provisioning.UserExistsError:
            raise click.ClickException(f"邮箱已存在：{email}")
        except ValueError as e:
            raise click.ClickException(str(e))
        click.echo(f"用户已创建：{email} (id={uid})  初始密码：{pw}")
        if languages:
            names = "、".join(words_svc._language_name(c) for c in languages)
            click.echo(f"正在学：{names}")
        click.echo(f"母语：{words_svc._feedback_language_name(feedback_language)}")

    @app.cli.command("reset-password")
    @click.option("--email", required=True)
    def reset_password(email):
        """重置密码，打印新密码。"""
        try:
            pw = provisioning.reset_password(email)
        except provisioning.UserNotFoundError:
            raise click.ClickException(f"用户不存在：{email}")
        click.echo(f"已重置：{email}  新密码：{pw}")

    @app.cli.command("deactivate-user")
    @click.option("--email", required=True)
    def deactivate_user(email):
        """停用账号（is_active=False）。"""
        try:
            provisioning.deactivate_user(email)
        except provisioning.UserNotFoundError:
            raise click.ClickException(f"用户不存在：{email}")
        click.echo(f"已停用：{email}")

    @app.cli.command("reset-quota")
    @click.option("--email", required=True)
    def reset_quota(email):
        """清零今日 token 额度。"""
        try:
            provisioning.reset_quota(email)
        except provisioning.UserNotFoundError:
            raise click.ClickException(f"用户不存在：{email}")
        click.echo(f"已重置额度：{email}")

    @app.cli.command("send-review-reminders")
    @click.option("--limit", default=1, show_default=True,
                  help="每个用户最多推送几个到期词")
    @click.option("--dry-run", is_flag=True, default=False,
                  help="只统计和输出，不发送 Bark，不写 push_log")
    @click.option("--public-base-url", default=None,
                  help="通知点击后打开的站点根地址，默认读 PUBLIC_BASE_URL")
    def send_review_reminders(limit, dry_run, public_base_url):
        """扫描已配置 Bark 的用户并发送到期复习提醒。"""
        dispatch_url = current_app.config.get("DISPATCH_DATABASE_URL")
        if not dispatch_url:
            raise click.ClickException("DISPATCH_DATABASE_URL missing")
        engine = create_engine(dispatch_url, pool_pre_ping=True)
        try:
            with engine.begin() as conn:
                stats = notifications.send_review_reminders(
                    conn, limit_per_user=limit, dry_run=dry_run,
                    secret_key=current_app.config.get("SECRET_KEY"),
                    public_base_url=(public_base_url
                                     or current_app.config.get("PUBLIC_BASE_URL")))
        except ValueError as exc:
            raise click.ClickException(str(exc))
        finally:
            engine.dispose()
        click.echo(
            "review reminders: "
            f"users={stats.users_seen} sent={stats.sent} "
            f"duplicates={stats.skipped_duplicate} no_due={stats.skipped_no_due} "
            f"failed={stats.failed}"
        )

    @app.cli.command("doctor")
    @click.option("--strict", is_flag=True, default=False,
                  help="把警告也视为失败，适合部署后检查")
    def doctor(strict):
        """闭测部署自检：数据库、迁移、LLM 配置、关键密钥。"""
        checks = []

        def ok(name, detail=""):
            checks.append(("ok", name, detail))

        def warn(name, detail=""):
            checks.append(("warn", name, detail))

        def fail(name, detail=""):
            checks.append(("fail", name, detail))

        try:
            db.session.execute(text("SELECT 1")).scalar()
            ok("app database", "connected")
        except Exception as e:
            fail("app database", str(e))

        dispatch_url = current_app.config.get("DISPATCH_DATABASE_URL")
        if dispatch_url:
            engine = create_engine(dispatch_url, pool_pre_ping=True)
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1")).scalar()
                ok("dispatch database", "connected")
            except Exception as e:
                fail("dispatch database", str(e))
            finally:
                engine.dispose()
        else:
            fail("dispatch database", "DISPATCH_DATABASE_URL missing")

        migrate_url = current_app.config.get("MIGRATE_DATABASE_URL")
        if migrate_url:
            engine = create_engine(migrate_url, pool_pre_ping=True)
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1")).scalar()
                ok("migrate database", "connected")
            except Exception as e:
                fail("migrate database", str(e))
            finally:
                engine.dispose()
        else:
            fail("migrate database", "MIGRATE_DATABASE_URL missing")

        try:
            current_rev = db.session.execute(text(
                "SELECT version_num FROM alembic_version"
            )).scalar()
            cfg = AlembicConfig("migrations/alembic.ini")
            cfg.set_main_option("script_location", "migrations")
            head_rev = ScriptDirectory.from_config(cfg).get_current_head()
            if current_rev == head_rev:
                ok("migrations", current_rev)
            else:
                fail("migrations", f"current={current_rev}, head={head_rev}")
        except Exception as e:
            fail("migrations", str(e))

        secret = current_app.config.get("SECRET_KEY")
        if is_configured(secret) and secret != INSECURE_SECRET_DEFAULT and len(secret) >= 32:
            ok("SECRET_KEY", "configured")
        else:
            warn("SECRET_KEY", "missing, placeholder, or too short")

        data_key = current_app.config.get("DATA_ENCRYPTION_KEY")
        if validate_fernet_key(data_key):
            ok("DATA_ENCRYPTION_KEY", "configured")
        else:
            warn("DATA_ENCRYPTION_KEY", "missing, placeholder, or invalid Fernet key")

        try:
            active_admins = User.query.filter_by(role="admin", is_active=True).count()
            if active_admins:
                ok("admin account", f"{active_admins} active")
            else:
                warn("admin account", "no active admin user")
        except Exception as e:
            fail("admin account", str(e))

        if llm.get_chain("correction"):
            ok("LLM correction", "provider configured")
        else:
            warn("LLM correction", "no provider configured")

        if llm.get_chain("nsfw"):
            ok("LLM nsfw", "provider configured")
        else:
            warn("LLM nsfw", "no provider configured")

        # 阅读词典数据目录检查
        from pathlib import Path
        dict_dir = current_app.config.get("DICTIONARY_DATA_DIR")
        READING_LANGS = ["zh", "en", "ja", "fr"]
        if not dict_dir:
            warn("reading dictionaries", "DICTIONARY_DATA_DIR not set")
        else:
            d = Path(dict_dir)
            if not d.is_dir():
                warn("reading dictionaries", f"DICTIONARY_DATA_DIR not a directory: {dict_dir}")
            else:
                missing = [lc for lc in READING_LANGS if not (d / lc).is_dir()]
                if missing:
                    warn("reading dictionaries", f"missing languages: {', '.join(missing)}")
                else:
                    ok("reading dictionaries", f"zh/en/ja/fr present in {dict_dir}")

        for level, name, detail in checks:
            marker = {"ok": "OK", "warn": "WARN", "fail": "FAIL"}[level]
            click.echo(f"[{marker}] {name}: {detail}")

        has_fail = any(level == "fail" for level, _, _ in checks)
        has_warn = any(level == "warn" for level, _, _ in checks)
        if has_fail or (strict and has_warn):
            raise click.ClickException("doctor check failed")
