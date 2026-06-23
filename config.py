"""RemeMate 配置。

三套数据库连接对应三角色（见 docs/design/data-isolation-security.md §角色分离）：
- DATABASE_URL          → app 运行时（rememate，受 FORCE RLS）
- MIGRATE_DATABASE_URL  → 迁移/建表（rememate_owner，表 owner）
- DISPATCH_DATABASE_URL → 后台任务（rememate_dispatch，BYPASSRLS）
"""
import os
from dotenv import load_dotenv

load_dotenv()


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-change-me")
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

    WTF_CSRF_ENABLED = True


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    WTF_CSRF_ENABLED = False
    # 测试库默认复用同一 dev 库；conftest 负责建表与清理
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL", os.environ.get("DATABASE_URL")
    )


class ProductionConfig(BaseConfig):
    DEBUG = False


_CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name=None):
    name = name or os.environ.get("FLASK_ENV", "development")
    return _CONFIGS.get(name, DevelopmentConfig)
