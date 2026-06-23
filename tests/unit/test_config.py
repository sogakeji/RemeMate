"""H1/H2：生产配置启动期断言。"""
import pytest

import config


def test_production_rejects_missing_secret(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    with pytest.raises(RuntimeError):
        config.ProductionConfig()


def test_production_rejects_default_secret(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", config.INSECURE_SECRET_DEFAULT)
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    with pytest.raises(RuntimeError):
        config.ProductionConfig()


def test_production_requires_database_url(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "a-real-strong-secret")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        config.ProductionConfig()


def test_production_ok_with_real_secret(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "a-real-strong-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    cfg = config.ProductionConfig()       # 不应抛
    assert cfg.DEBUG is False


def test_get_config_defaults_to_production(monkeypatch):
    # 漏配 FLASK_ENV → 默认 production（fail-safe），且因缺密钥而 raise
    monkeypatch.delenv("FLASK_ENV", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        config.get_config()
