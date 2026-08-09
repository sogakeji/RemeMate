"""应用工厂。

阶段一只装地基：扩展、RLS 钩子、models 注册（供 Flask-Migrate 发现）。
蓝图在后续阶段逐个接入。
"""
from flask import Flask, redirect, request, url_for
from flask_login import current_user

from config import get_config
from app.extensions import db, login_manager, migrate, csrf


def create_app(config_name=None):
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))

    # 扩展初始化
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    from app.services.resend_auth_mail import ResendAuthMailer
    app.extensions["auth_mailer"] = ResendAuthMailer(
        api_key=app.config.get("RESEND_API_KEY"),
        from_address=app.config.get("AUTH_EMAIL_FROM"),
        timeout=app.config.get("AUTH_MAIL_TIMEOUT_SECONDS", 5),
    )

    # 导入全部 models，确保 metadata 完整（Flask-Migrate autogenerate 依赖）
    from app import models  # noqa: F401

    # RLS：before_request 把 uid 缓存进 g；after_begin 事件每个事务注入 GUC（多 commit 安全）。
    # 见 app/services/rls.py。
    from app.services.rls import set_request_rls_user
    from app.i18n import bind_ui_locale

    app.before_request(set_request_rls_user)
    app.before_request(bind_ui_locale)

    @app.before_request
    def enforce_initial_password():
        if not current_user.is_authenticated or not current_user.password_setup_required:
            return None
        endpoint = request.endpoint or ""
        if endpoint in {"auth.set_password", "auth.logout", "healthz"}:
            return None
        if endpoint.startswith("static"):
            return None
        return redirect(url_for("auth.set_password"))

    @login_manager.user_loader
    def load_user(user_id):
        from app.models.user import User

        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            return None                 # 脏/篡改的 cookie → 视为未登录，不 500（M3）
        return db.session.get(User, uid)

    # 蓝图
    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.main import bp as main_bp
    from app.blueprints.words import bp as words_bp
    from app.blueprints.write import bp as write_bp
    from app.blueprints.intake import bp as intake_bp
    from app.blueprints.square import bp as square_bp
    from app.blueprints.admin import bp as admin_bp
    from app.blueprints.reading import bp as reading_bp
    from app.blueprints.partners import bp as partners_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(words_bp)
    app.register_blueprint(write_bp)
    app.register_blueprint(intake_bp)
    app.register_blueprint(square_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(reading_bp)
    app.register_blueprint(partners_bp)

    # CLI 命令
    from cli.commands import register_commands

    register_commands(app)

    # 全局模板上下文：把「当前语言 + 语言清单」注入所有模板，供 base.html 全局语言
    # 切换器用。无请求未登录时为 None/空。service 层显式收 user_id，不依赖 request。
    from app.services import words as _words_svc
    from app.i18n import (get_ui_locale, localized_language_names,
                          localized_timezone_names, translate)

    app.jinja_env.globals["_"] = translate

    @app.context_processor
    def inject_lang():
        from flask_login import current_user
        lang = None
        if current_user.is_authenticated:
            try:
                lang = _words_svc.get_current_language(current_user.id)
            except Exception:                       # 容错：模板渲染绝不因 service 挂
                lang = None
        return {"current_language": lang,
                "lang_choices": _words_svc._LANGUAGE_NAMES}

    @app.context_processor
    def inject_learning():
        """注入「在学语言集合」（首页切换器 menu 只列这些）。与上方 inject_lang 同模式。"""
        from flask_login import current_user
        learning = []
        if current_user.is_authenticated:
            try:
                learning = _words_svc.get_learning_languages(current_user.id)
            except Exception:
                learning = []
        return {"learning_languages": learning}

    @app.context_processor
    def inject_i18n():
        return {
            "ui_locale": get_ui_locale(),
            "ui_language_names": localized_language_names(),
            "ui_timezone_names": localized_timezone_names(),
        }

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    return app
