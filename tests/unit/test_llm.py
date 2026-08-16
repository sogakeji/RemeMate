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


def test_excluded_provider_is_skipped():
    p1, p2 = FakeProvider("deepseek"), FakeProvider("openai")
    llm.set_registry({"general": [p1, p2]})
    result = llm.chat(
        [{"role": "user", "content": "hi"}],
        task="general",
        excluded_provider_names={"deepseek"},
    )
    assert result.provider == "openai"
    assert p1.calls == 0 and p2.calls == 1


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


def test_openai_compatible_deepseek_model_can_be_primary(app):
    app.config["DEEPSEEK_API_KEY"] = None
    app.config["OPENAI_API_KEY"] = "sk-opencode"
    app.config["OPENAI_BASE_URL"] = "http://127.0.0.1:11434/v1"
    app.config["OPENAI_MODEL"] = "deepseek-chat"

    with app.app_context():
        correction_chain = llm.get_chain("correction")
        nsfw_chain = llm.get_chain("nsfw")

    assert len(correction_chain) == 1
    assert correction_chain[0].name == "openai"
    assert correction_chain[0].api_key == "sk-opencode"
    assert correction_chain[0].base_url == "http://127.0.0.1:11434/v1"
    assert correction_chain[0].model == "deepseek-chat"
    assert len(nsfw_chain) == 1
    assert nsfw_chain[0].name == "openai"
    assert nsfw_chain[0].model == "deepseek-chat"


def test_openai_default_model_is_not_used_for_nsfw(app):
    app.config["DEEPSEEK_API_KEY"] = None
    app.config["OPENAI_API_KEY"] = "sk-openai"
    app.config["OPENAI_BASE_URL"] = "https://api.openai.com/v1"
    app.config["OPENAI_MODEL"] = "gpt-4o-mini"

    with app.app_context():
        assert llm.get_chain("correction")
        assert llm.get_chain("nsfw") == []


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
