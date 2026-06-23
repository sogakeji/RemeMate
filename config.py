"""RemeMate 配置。

三套数据库连接对应三角色（见 docs/design/data-isolation-security.md §角色分离）：
- DATABASE_URL          → app 运行时（rememate，受 FORCE RLS）
- MIGRATE_DATABASE_URL  → 迁移/建表（rememate_owner，表 owner）
- DISPATCH_DATABASE_URL → 后台任务（rememate_dispatch，BYPASSRLS）
"""
import os
from dotenv import load_dotenv

load_dotenv()

INSECURE_SECRET_DEFAULT = "dev-insecure-change-me"


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", INSECURE_SECRET_DEFAULT)
    DATA_ENCRYPTION_KEY = os.environ.get("DATA_ENCRYPTION_KEY")

    # 运行时用 app 角色连接
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 迁移与后台任务的连接串（不走 Flask-SQLAlchemy，分别由 env.py / dispatch 使用）
    MIGRATE_DATABASE_URL = os.environ.get("MIGRATE_DATABASE_URL")
    DISPATCH_DATABASE_URL = os.environ.get("DISPATCH_DATABASE_URL")

    # LLM
    DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
    DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")        # GPT-4o-mini failover（可选）
    OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

    WTF_CSRF_ENABLED = True


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    WTF_CSRF_ENABLED = False
    # 测试一律连独立 rememate_test 库，app 与 dispatch(provisioning) 都指向它，
    # 绝不在测试中误写 dev 库。
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL")
    DISPATCH_DATABASE_URL = os.environ.get("TEST_DISPATCH_DATABASE_URL")
    MIGRATE_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


class ProductionConfig(BaseConfig):
    DEBUG = False

    def __init__(self):
        # 启动期断言：生产绝不允许用不安全默认密钥或空密钥（H1）
        secret = os.environ.get("SECRET_KEY")
        if not secret or secret == INSECURE_SECRET_DEFAULT:
            raise RuntimeError(
                "生产环境必须设置强随机 SECRET_KEY（不能为空或用 dev 默认值）。"
                "生成：python -c \"import secrets;print(secrets.token_hex(32))\""
            )
        if not os.environ.get("DATABASE_URL"):
            raise RuntimeError("生产环境必须设置 DATABASE_URL。")


_CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name=None):
    # 默认回落到 production（fail-safe）：漏配 FLASK_ENV 时不静默跑 DEBUG（H2）。
    # 返回实例而非类，确保 ProductionConfig.__init__ 的启动期断言会执行（H1）。
    name = name or os.environ.get("FLASK_ENV", "production")
    cls = _CONFIGS.get(name, ProductionConfig)
    return cls()
