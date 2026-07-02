"""生产配置启动护栏：闭测部署缺硬配置时必须 fail fast。"""
import pytest
from cryptography.fernet import Fernet

from config import get_config


def _set_production_env(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "s" * 64)
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("DATABASE_URL", "postgresql://app@example.com/db")
    monkeypatch.setenv("MIGRATE_DATABASE_URL", "postgresql://owner@example.com/db")
    monkeypatch.setenv("DISPATCH_DATABASE_URL", "postgresql://dispatch@example.com/db")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")


def test_production_config_accepts_complete_env(monkeypatch):
    _set_production_env(monkeypatch)

    cfg = get_config("production")

    assert cfg.SECRET_KEY == "s" * 64
    assert cfg.DATA_ENCRYPTION_KEY
    assert cfg.SQLALCHEMY_DATABASE_URI == "postgresql://app@example.com/db"
    assert cfg.MIGRATE_DATABASE_URL == "postgresql://owner@example.com/db"
    assert cfg.DISPATCH_DATABASE_URL == "postgresql://dispatch@example.com/db"
    assert cfg.DEEPSEEK_API_KEY == "sk-test"


@pytest.mark.parametrize("name", [
    "SECRET_KEY",
    "DATA_ENCRYPTION_KEY",
    "DATABASE_URL",
    "MIGRATE_DATABASE_URL",
    "DISPATCH_DATABASE_URL",
    "DEEPSEEK_API_KEY",
])
def test_production_config_rejects_missing_required_env(monkeypatch, name):
    _set_production_env(monkeypatch)
    monkeypatch.delenv(name)

    with pytest.raises(RuntimeError, match=name):
        get_config("production")


def test_production_config_rejects_invalid_data_encryption_key(monkeypatch):
    _set_production_env(monkeypatch)
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", "not-a-fernet-key")

    with pytest.raises(RuntimeError, match="DATA_ENCRYPTION_KEY"):
        get_config("production")


def test_production_config_rejects_development_secret(monkeypatch):
    from config import INSECURE_SECRET_DEFAULT

    _set_production_env(monkeypatch)
    monkeypatch.setenv("SECRET_KEY", INSECURE_SECRET_DEFAULT)

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        get_config("production")


def test_production_config_rejects_short_secret(monkeypatch):
    _set_production_env(monkeypatch)
    monkeypatch.setenv("SECRET_KEY", "too-short")

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        get_config("production")
