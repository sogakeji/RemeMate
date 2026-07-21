from app.services import llm, moderation


class _Provider:
    name = "moderator"

    def __init__(self, content):
        self.content = content
        self.calls = []

    def call(self, messages, *, timeout, json_mode=False):
        self.calls.append((messages, json_mode))
        return llm.LLMResult(self.content, 2, 1, self.name, "safe-model")


def teardown_function():
    llm.set_registry(None)
    llm.reset_breaker()


def test_uses_only_nsfw_task_and_accepts_boolean_decision():
    provider = _Provider('{"is_nsfw":false}')
    llm.set_registry({"correction": [], "nsfw": [provider]})

    result = moderation.classify_public_text("A learner sentence")

    assert result.is_nsfw is False
    assert result.degraded is False
    assert result.provider == "moderator"
    assert len(provider.calls) == 1
    assert provider.calls[0][1] is True


def test_missing_or_non_boolean_decision_fails_closed():
    for content in ('{}', '{"is_nsfw":"false"}', 'not json'):
        llm.set_registry({"nsfw": [_Provider(content)]})
        result = moderation.classify_public_text("text")
        assert result.is_nsfw is True
        assert result.degraded is True


def test_provider_outage_fails_closed():
    llm.set_registry({"nsfw": []})

    result = moderation.classify_public_text("text")

    assert result.is_nsfw is True
    assert result.degraded is True
