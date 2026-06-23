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

# 必须用独立测试库：conftest 会 DELETE 全表，绝不能指向 dev 的 DATABASE_URL。
# 缺 TEST_* 直接报错，而不是回退到 dev 库把数据清空。
try:
    APP_URL = os.environ["TEST_DATABASE_URL"]
    BYPASS_URL = os.environ["TEST_DISPATCH_DATABASE_URL"]
except KeyError as e:
    raise RuntimeError(
        f"缺少环境变量 {e}. 测试必须连独立的 rememate_test 库，"
        f"不能复用 dev 库。见 scripts/dev/init-test-db.sql 与 .env.example。"
    ) from None

if "rememate_test" not in APP_URL:
    raise RuntimeError(
        f"TEST_DATABASE_URL 必须指向 rememate_test 库，实际={APP_URL!r}，"
        f"拒绝在非测试库上跑清库测试。"
    )

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


@pytest.fixture
def app():
    from app import create_app

    return create_app("testing")


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def runner(app):
    return app.test_cli_runner()


@pytest.fixture
def fake_llm():
    """注入假 provider 链，让 correction 返回可控 JSON，不触真实 API。

    用法：mutate holder["content"] 改批改返回；holder["empty"]=True 模拟 AI 全挂。
    """
    from app.services import llm

    holder = {
        "content": ('{"corrected":"phrase corrigée","translation":"修正的句子",'
                    '"target_word_used":true,"incomplete":false,"errors":[],'
                    '"is_nsfw":false,"feedback":"很好"}'),
        "empty": False,
    }

    class FP:
        name = "fake"

        def call(self, messages, *, timeout, json_mode=False):
            return llm.LLMResult(holder["content"], 10, 20, "fake", "fake-model")

    def install():
        chain = [] if holder["empty"] else [FP()]
        llm.set_registry({"correction": chain, "nsfw": chain, "general": chain})

    install()
    holder["reinstall"] = install
    llm.reset_breaker()
    yield holder
    llm.set_registry(None)
    llm.reset_breaker()


@pytest.fixture
def fake_extract():
    """注入假 provider 给 extract 链，返回可控 {"items":[...]} JSON。"""
    from app.services import llm

    holder = {
        "content": ('{"items":[{"word":"décollage","part_of_speech":"nm",'
                    '"meaning":"起飞","example":"e"},'
                    '{"word":"essai","meaning":"尝试"}]}'),
    }

    class FP:
        name = "fake"

        def call(self, messages, *, timeout, json_mode=False):
            return llm.LLMResult(holder["content"], 10, 20, "fake", "fake-model")

    llm.set_registry({"extract": [FP()], "correction": [FP()], "general": [FP()]})
    llm.reset_breaker()
    yield holder
    llm.set_registry(None)
    llm.reset_breaker()
