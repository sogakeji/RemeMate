"""批改解析与降级（用假 LLM，不触真实 API）。"""
from app.services import llm
from app.services import correction


class _FP:
    name = "fake"

    def __init__(self, content):
        self.content = content

    def call(self, messages, *, timeout, json_mode=False):
        return llm.LLMResult(self.content, 3, 4, "fake", "m")


def _set(content):
    llm.set_registry({"correction": [_FP(content)]})


def teardown_function():
    llm.set_registry(None)
    llm.reset_breaker()


def test_parses_structured_fields():
    _set('{"corrected":"X","translation":"译","target_word_used":true,'
         '"incomplete":false,"errors":[{"type":"grammar","detail":"d"}],'
         '"is_nsfw":false,"feedback":"f"}')
    r = correction.correct_sentence(sentence="s", target_word="w", language_code="fr")
    assert r.corrected == "X" and r.translation == "译"
    assert r.target_word_used is True and r.incomplete is False
    assert r.errors[0]["type"] == "grammar"
    # Correction output cannot grant publish eligibility.
    assert r.is_nsfw is True
    assert r.prompt_tokens == 3 and r.degraded is False


def test_missing_nsfw_fails_closed():
    _set('{"corrected":"X","target_word_used":false}')   # 缺 is_nsfw
    r = correction.correct_sentence(sentence="s", target_word="w", language_code="fr")
    assert r.is_nsfw is True                 # fail-closed
    assert r.target_word_used is False


def test_malformed_json_recovered_or_failclosed():
    _set('垃圾前缀 {"corrected":"Y","is_nsfw":false} 垃圾后缀')
    r = correction.correct_sentence(sentence="s", target_word="w", language_code="fr")
    assert r.corrected == "Y"                # 截取首个 {...} 成功
    assert r.is_nsfw is True


def test_unparseable_failclosed_and_degraded():
    _set("完全不是 JSON")
    r = correction.correct_sentence(sentence="s", target_word="w", language_code="fr")
    assert r.is_nsfw is True                 # 解析不出 → 保守
    assert r.degraded is True                # 标记降级，不伪装成"真批改"
    assert "解析异常" in r.feedback


def test_all_providers_down_degraded():
    llm.set_registry({"correction": []})     # 无 provider → AllProvidersDown
    r = correction.correct_sentence(sentence="orig", target_word="w", language_code="fr")
    assert r.degraded is True
    assert r.corrected == "orig"             # 原样返回，不替写
    assert r.is_nsfw is True                 # fail-closed
    assert "暂时不可用" in r.feedback


def test_correct_diary_parses_structured_fields():
    _set('{"corrected":"L1\\nL2\\nL3","translation":"一\\n二\\n三",'
         '"target_word_used":false,"incomplete":false,"errors":[],'
         '"is_nsfw":false,"feedback":"ok"}')
    r = correction.correct_diary(
        diary="a\nb\nc", prompt="p", language_code="fr")
    assert r.corrected == "L1\nL2\nL3"
    assert r.translation == "一\n二\n三"
    assert r.target_word_used is True
    assert r.is_nsfw is True


def test_correction_prompt_uses_feedback_language():
    messages = correction._build_messages(
        "我喜欢学习中文。", "学习", "zh", feedback_language_code="fr")
    assert "中文写作批改老师" in messages[0]["content"]
    assert "法语翻译" in messages[0]["content"]
    assert "errors.detail 都用法语" in messages[0]["content"]


def test_invalid_schema_is_degraded_and_keeps_usage():
    _set('{"title":"not a correction","sentences":[]}')
    r = correction.correct_sentence(sentence="s", target_word="w", language_code="fr")
    assert r.degraded is True
    assert r.error_code == "invalid_schema"
    assert r.prompt_tokens == 3 and r.completion_tokens == 4
    assert r.corrected == "s"


def test_empty_corrected_is_unusable():
    _set('{"corrected":"","translation":"t","target_word_used":true,'
         '"incomplete":false,"errors":[],"feedback":"f"}')
    r = correction.correct_sentence(sentence="orig", target_word="w", language_code="fr")
    assert r.degraded is True
    assert r.error_code == "empty_result"
    assert r.corrected == "orig"
    assert r.prompt_tokens == 3


def test_empty_provider_content_is_unusable():
    _set("")
    r = correction.correct_sentence(sentence="orig", target_word="w", language_code="fr")
    assert r.degraded is True
    assert r.error_code == "empty_result"
    assert r.prompt_tokens == 3


def test_provider_timeout_is_degraded():
    class TimeoutP:
        name = "fake"

        def call(self, messages, *, timeout, json_mode=False):
            raise llm.ProviderError("fake: timeout")

    llm.set_registry({"correction": [TimeoutP()]})
    r = correction.correct_sentence(sentence="orig", target_word="w", language_code="fr")
    assert r.degraded is True
    assert r.error_code == "timeout"
    assert r.corrected == "orig"


def test_invalid_schema_retries_once_then_succeeds():
    class P:
        def __init__(self, name, content, prompt_tokens, completion_tokens):
            self.name = name
            self.content = content
            self.prompt_tokens = prompt_tokens
            self.completion_tokens = completion_tokens
            self.calls = 0

        def call(self, messages, *, timeout, json_mode=False):
            self.calls += 1
            return llm.LLMResult(
                self.content, self.prompt_tokens, self.completion_tokens,
                self.name, "m",
            )

    primary = P("fake", '{"oops":true}', 3, 4)
    backup = P(
        "backup",
        '{"corrected":"X","translation":"译","target_word_used":true,'
        '"incomplete":false,"errors":[],"feedback":"f"}',
        5, 6,
    )
    llm.set_registry({"correction": [primary, backup]})
    r = correction.correct_sentence(sentence="s", target_word="w", language_code="fr")
    assert primary.calls == 1 and backup.calls == 1
    assert r.degraded is False
    assert r.corrected == "X"
    assert r.prompt_tokens == 8 and r.completion_tokens == 10


def test_unparseable_keeps_provider_usage():
    _set("完全不是 JSON")
    r = correction.correct_sentence(sentence="s", target_word="w", language_code="fr")
    assert r.degraded is True
    assert r.error_code == "parse_error"
    assert r.prompt_tokens == 3 and r.completion_tokens == 4
