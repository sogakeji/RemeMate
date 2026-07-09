"""RemeMate 配置。

三套数据库连接对应三角色（见 docs/design/data-isolation-security.md §角色分离）：
- DATABASE_URL          → app 运行时（rememate，受 FORCE RLS）
- MIGRATE_DATABASE_URL  → 迁移/建表（rememate_owner，表 owner）
- DISPATCH_DATABASE_URL → 后台任务（rememate_dispatch，BYPASSRLS）
"""
import os
from dotenv import load_dotenv
from cryptography.fernet import Fernet

load_dotenv()

INSECURE_SECRET_DEFAULT = "dev-insecure-change-me"
PLACEHOLDER_VALUES = {"", "CHANGE_ME", "changeme", "your-api-key", "your-secret-key"}


def is_configured(value: str | None) -> bool:
    return (value or "").strip() not in PLACEHOLDER_VALUES


def require_configured(name: str) -> str:
    value = os.environ.get(name)
    if not is_configured(value):
        raise RuntimeError(f"生产环境必须设置 {name}，且不能使用占位值。")
    return value.strip()


def optional_configured(name: str) -> str | None:
    value = os.environ.get(name)
    return value.strip() if is_configured(value) else None


def validate_fernet_key(value: str | None) -> bool:
    if not is_configured(value):
        return False
    try:
        Fernet(value.encode("utf-8"))
    except Exception:
        return False
    return True


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", INSECURE_SECRET_DEFAULT)
    DATA_ENCRYPTION_KEY = os.environ.get("DATA_ENCRYPTION_KEY")

    # 运行时用 app 角色连接
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 迁移与后台任务的连接串（不走 Flask-SQLAlchemy，分别由 env.py / dispatch 使用）
    MIGRATE_DATABASE_URL = os.environ.get("MIGRATE_DATABASE_URL")
    DISPATCH_DATABASE_URL = os.environ.get("DISPATCH_DATABASE_URL")
    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL")

    # PDF 上传文件大小上限（MB），需大于 parser 内部限制（25MB）以让 parser 给出明确提示，
    # 而不是直接报 413 原始错误给用户。
    MAX_CONTENT_LENGTH = 31 * 1024 * 1024

    # 阅读词典数据目录（外置，不进 git）
    DICTIONARY_DATA_DIR = os.environ.get("DICTIONARY_DATA_DIR")
    # 阅读 PDF 上传限制（需与 parser 的 max_bytes/max_pages/max_chars 联动）
    READING_MAX_PDF_BYTES = int(os.environ.get("READING_MAX_PDF_BYTES", 8 * 1024 * 1024))
    READING_MAX_PDF_PAGES = int(os.environ.get("READING_MAX_PDF_PAGES", 80))
    READING_MAX_PDF_CHARS = int(os.environ.get("READING_MAX_PDF_CHARS", 250_000))

    # LLM
    DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
    DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")        # OpenAI-compatible failover/primary（可选）
    OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

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
        # 启动期断言：生产绝不允许用不安全默认密钥或空密钥（H1）。
        secret = require_configured("SECRET_KEY")
        if secret == INSECURE_SECRET_DEFAULT:
            raise RuntimeError(
                "生产环境必须设置强随机 SECRET_KEY（不能为空或用 dev 默认值）。"
                "生成：python -c \"import secrets;print(secrets.token_hex(32))\""
            )
        if len(secret) < 32:
            raise RuntimeError("生产环境 SECRET_KEY 至少 32 字符。")

        data_key = require_configured("DATA_ENCRYPTION_KEY")
        if not validate_fernet_key(data_key):
            raise RuntimeError(
                "生产环境 DATA_ENCRYPTION_KEY 必须是 Fernet key。"
                "生成：python -c \"from cryptography.fernet import Fernet;"
                "print(Fernet.generate_key().decode())\""
            )

        self.SECRET_KEY = secret
        self.DATA_ENCRYPTION_KEY = data_key
        self.SQLALCHEMY_DATABASE_URI = require_configured("DATABASE_URL")
        self.MIGRATE_DATABASE_URL = require_configured("MIGRATE_DATABASE_URL")
        self.DISPATCH_DATABASE_URL = require_configured("DISPATCH_DATABASE_URL")
        self.PUBLIC_BASE_URL = optional_configured("PUBLIC_BASE_URL")
        self.DEEPSEEK_API_KEY = optional_configured("DEEPSEEK_API_KEY")
        self.DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        self.OPENAI_API_KEY = optional_configured("OPENAI_API_KEY")
        self.OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        if not (self.DEEPSEEK_API_KEY or self.OPENAI_API_KEY):
            raise RuntimeError("生产环境必须设置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY，且不能使用占位值。")


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
