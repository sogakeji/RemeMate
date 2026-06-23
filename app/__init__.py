"""应用工厂。

阶段一只装地基：扩展、RLS 钩子、models 注册（供 Flask-Migrate 发现）。
蓝图在后续阶段逐个接入。
"""
from flask import Flask

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

    # 导入全部 models，确保 metadata 完整（Flask-Migrate autogenerate 依赖）
    from app import models  # noqa: F401

    # RLS 请求钩子（第三层防御的注入/清除）
    from app.services.rls import set_rls_user, reset_rls_user

    app.before_request(set_rls_user)
    app.teardown_request(reset_rls_user)

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

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(words_bp)

    # CLI 命令
    from cli.commands import register_commands

    register_commands(app)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    return app
