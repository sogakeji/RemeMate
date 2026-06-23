"""测试夹具：双角色连接。

- bypass_engine（rememate_dispatch, BYPASSRLS）：建 fixture 数据、清库。
  注意 owner 也受 FORCE RLS 约束，建数据必须用 BYPASSRLS 角色。
- app_engine（rememate, FORCE RLS）：验证 RLS 隔离的本层连接。

数据构造 helper 见 tests/helpers.py。
"""
import os

import pytest
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

APP_URL = os.environ["DATABASE_URL"]
BYPASS_URL = os.environ["DISPATCH_DATABASE_URL"]

# FK 安全的删除顺序（子表在前，users 最后）。
# 用 DELETE 而非 TRUNCATE：dispatch 角色有 DML 权限但无 TRUNCATE（非 owner）。
_TABLES = [
    "push_log", "token_usage_log", "user_quota", "user_settings",
    "sentence_upvotes", "messages", "conversations",
    "word_candidates", "source_segments", "intake_sources",
    "output_entries", "review_logs", "definitions", "words", "word_lists",
    "users",
]


def _wipe(bypass_engine):
    with bypass_engine.begin() as conn:
        for t in _TABLES:
            conn.execute(text(f"DELETE FROM {t}"))


@pytest.fixture(scope="session")
def app_engine():
    e = create_engine(APP_URL)
    yield e
    e.dispose()


@pytest.fixture(scope="session")
def bypass_engine():
    e = create_engine(BYPASS_URL)
    yield e
    e.dispose()


@pytest.fixture(autouse=True)
def clean_db(bypass_engine):
    """每个测试前后清库（BYPASSRLS 角色 DELETE，前置清理规避上一轮残留）。"""
    _wipe(bypass_engine)
    yield
    _wipe(bypass_engine)
