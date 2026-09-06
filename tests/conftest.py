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
from tests.database_config import database_urls

# Explicit environment only: never load a shared .env before destructive fixtures.
# Validate both URLs before constructing any engine; errors never include credentials.
APP_URL, BYPASS_URL = database_urls(os.environ)
# config.py also imports dotenv; prohibit implicit .env loading in later app imports.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

# FK 安全的删除顺序（子表在前，users 最后）。
# 用 DELETE 而非 TRUNCATE：dispatch 角色有 DML 权限但无 TRUNCATE（非 owner）。
_TABLES = [
    "practice_items", "practice_sessions",
    "auth_rate_limit_buckets",
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
        "timeout": False,
        "sequence": None,
        "calls": 0,
        "prompt_tokens": 10,
        "completion_tokens": 20,
    }

    class FP:
        name = "fake"

        def __init__(self, kind):
            self.kind = kind

        def call(self, messages, *, timeout, json_mode=False):
            if self.kind == "nsfw":
                return llm.LLMResult(
                    holder["nsfw_content"], 10, 20, "fake", "fake-model",
                )
            holder["calls"] += 1
            if holder["timeout"]:
                raise llm.ProviderError("fake: timeout")
            sequence = holder["sequence"]
            if sequence:
                idx = min(holder["calls"] - 1, len(sequence) - 1)
                item = sequence[idx]
                if item == "timeout":
                    raise llm.ProviderError("fake: timeout")
                if item == "fail":
                    raise llm.ProviderError("fake: down")
                content = item
            else:
                content = holder["content"]
            return llm.LLMResult(
                content,
                holder["prompt_tokens"],
                holder["completion_tokens"],
                "fake",
                "fake-model",
            )

    def install():
        holder["calls"] = 0
        correction = [] if holder["empty"] else [FP("correction")]
        nsfw = [] if holder["nsfw_empty"] else [FP("nsfw")]
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
