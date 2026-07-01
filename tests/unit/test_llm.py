"""LLM 抽象层单测：failover / 熔断 / 全挂，用假 provider，不触真实 API。"""
import pytest

from app.services import llm


class FakeProvider:
    def __init__(self, name, mode="ok"):
        self.name = name
        self.mode = mode          # "ok" | "fail"
        self.calls = 0

    def call(self, messages, *, timeout, json_mode=False):
        self.calls += 1
        if self.mode == "fail":
            raise llm.ProviderError(f"{self.name} down")
        return llm.LLMResult(f"ok-{self.name}", 5, 7, self.name, "m")


@pytest.fixture(autouse=True)
def _reset():
    llm.reset_breaker()
    yield
    llm.set_registry(None)
    llm.reset_breaker()


def test_primary_success():
    p1, p2 = FakeProvider("deepseek"), FakeProvider("openai")
    llm.set_registry({"correction": [p1, p2]})
    r = llm.chat([{"role": "user", "content": "hi"}], task="correction")
    assert r.content == "ok-deepseek"
    assert p1.calls == 1 and p2.calls == 0       # 主成功不碰备


def test_failover_to_secondary():
    p1, p2 = FakeProvider("deepseek", "fail"), FakeProvider("openai")
    llm.set_registry({"correction": [p1, p2]})
    r = llm.chat([{"role": "user", "content": "hi"}], task="correction")
    assert r.content == "ok-openai"
    assert p1.calls == 1 and p2.calls == 1


def test_all_down_raises():
    p1, p2 = FakeProvider("deepseek", "fail"), FakeProvider("openai", "fail")
    llm.set_registry({"correction": [p1, p2]})
    with pytest.raises(llm.AllProvidersDown):
        llm.chat([{"role": "user", "content": "hi"}], task="correction")


def test_empty_chain_raises():
    llm.set_registry({"nsfw": []})
    with pytest.raises(llm.AllProvidersDown):
        llm.chat([{"role": "user", "content": "x"}], task="nsfw")


def test_placeholder_keys_are_not_configured():
    assert llm._configured_key(None) is None
    assert llm._configured_key("") is None
    assert llm._configured_key("CHANGE_ME") is None
    assert llm._configured_key("sk-real") == "sk-real"


def test_breaker_opens_after_threshold():
    p1 = FakeProvider("deepseek", "fail")
    p2 = FakeProvider("openai")
    llm.set_registry({"correction": [p1, p2]})
    # 连续 3 次失败后 deepseek 熔断，后续直接跳过它
    for _ in range(llm.CB_THRESHOLD):
        llm.chat([{"role": "user", "content": "x"}], task="correction")
    calls_before = p1.calls
    llm.chat([{"role": "user", "content": "x"}], task="correction")
    assert p1.calls == calls_before              # 熔断后不再调用 deepseek
    assert llm._breaker.is_open("deepseek")
