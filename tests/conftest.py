"""测试夹具：双角色连接。

- bypass_engine（rememate_dispatch, BYPASSRLS）：建 fixture 数据、清库。
  注意 owner 也受 FORCE RLS 约束，建数据必须用 BYPASSRLS 角色。
- app_engine（rememate, FORCE RLS）：验证 RLS 隔离的本层连接。

数据构造 helper 见 tests/helpers.py。
"""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
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
    "auth_mail_events", "auth_challenges",
    "learning_funnel_events", "review_story_runs",
    "partner_packet_item_adoptions",
    "partner_packet_intakes",
    "partner_packet_thanks",
    "partner_packet_items",
    "partner_packets",
    "partner_recap_items",
    "partner_recaps",
    "language_partners",
    "push_log", "token_usage_log", "user_quota", "user_settings",
    "sentence_upvotes", "messages", "conversations",
    "reading_lookups", "word_candidates", "source_segments",
    "reading_documents", "intake_sources",
    "output_entries", "review_logs", "definitions", "words", "word_lists",
    "users",
]


def _wipe(bypass_engine):
    """每个测试前后清库；父表 FK 冲突时逐用户重试。"""
    # 先尝试批量 DELETE（BYPASSRLS 生效时一次事务搞定，快且简单）
    try:
        with bypass_engine.begin() as conn:
            for t in _TABLES:
                conn.execute(text(f"DELETE FROM {t}"))
        return
    except IntegrityError:
        # 批量清理仍在父表处遇到 FK 时，换用一笔新的逐用户清理事务。
        # 仅对此类数据库完整性失败回退，其他 fixture/schema 错误必须直接暴露。
        pass

    # 逐用户清理：为每个 user 设事务级 app.current_user_id 后逐表 DELETE。
    # 这样可覆盖 RLS 表的按用户策略，同时不会把 GUC 泄漏到连接池的下一次测试。
    with bypass_engine.begin() as conn:
        rows = conn.execute(text("SELECT id FROM users")).fetchall()
        for (uid,) in rows:
            conn.execute(
                text("SELECT set_config('app.current_user_id', :u, true)"),
                {"u": str(uid)},
            )
            for t in _TABLES:
                if t != "users":
                    conn.execute(text(f"DELETE FROM {t}"))
        conn.execute(text("DELETE FROM users"))


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
        "nsfw_content": '{"is_nsfw":false}',
        "empty": False,
        "nsfw_empty": False,
    }

    class FP:
        name = "fake"

        def __init__(self, content):
            self.content = content

        def call(self, messages, *, timeout, json_mode=False):
            return llm.LLMResult(self.content, 10, 20, "fake", "fake-model")

    def install():
        correction = [] if holder["empty"] else [FP(holder["content"])]
        nsfw = [] if holder["nsfw_empty"] else [FP(holder["nsfw_content"])]
        llm.set_registry({
            "correction": correction, "nsfw": nsfw, "general": correction,
        })

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
