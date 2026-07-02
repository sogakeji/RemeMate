"""LLM 服务层：唯一对外接口 chat()，调用方不感知底层 provider。

见 docs/design/llm-provider-failover.md。
- provider 链按 task；DeepSeek 主，GPT-4o-mini 备（NSFW 仅 DeepSeek）。
- 内存熔断器（-w 2 下每 worker 一份，差异可接受，不引入 Redis）。
- 单 provider 超时 10s，请求级总 deadline 25s。
- 批改/结构化输出走非流式（整段返回后解析）；流式留给对话场景。

返回 LLMResult 带 usage，供 quota.record 记账。
"""
import time
from dataclasses import dataclass

from flask import current_app

PER_PROVIDER_TIMEOUT = 10
TOTAL_DEADLINE = 25
CB_THRESHOLD = 3
CB_COOLDOWN = 300  # 秒


class ProviderError(Exception):
    pass


class AllProvidersDown(Exception):
    pass


@dataclass
class LLMResult:
    content: str
    prompt_tokens: int
    completion_tokens: int
    provider: str
    model: str


class CircuitBreaker:
    """单进程内存熔断：连续 N 次失败标记 DOWN，冷却 T 秒后半开试探。"""

    def __init__(self, threshold=CB_THRESHOLD, cooldown=CB_COOLDOWN):
        self.threshold = threshold
        self.cooldown = cooldown
        self._fail = {}        # name -> 连续失败数
        self._open_until = {}  # name -> 冷却结束时间戳

    def is_open(self, name):
        until = self._open_until.get(name)
        if until is None:
            return False
        if time.time() >= until:        # 冷却到 → 半开（允许一次试探）
            self._open_until.pop(name, None)
            return False
        return True

    def record_success(self, name):
        self._fail.pop(name, None)
        self._open_until.pop(name, None)

    def record_failure(self, name):
        n = self._fail.get(name, 0) + 1
        self._fail[name] = n
        if n >= self.threshold:
            self._open_until[name] = time.time() + self.cooldown


_breaker = CircuitBreaker()


class OpenAICompatProvider:
    """DeepSeek / OpenAI 等 OpenAI 兼容接口的 provider。"""

    def __init__(self, name, api_key, base_url, model):
        self.name = name
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    def call(self, messages, *, timeout, json_mode=False) -> LLMResult:
        from openai import OpenAI  # 延迟导入，便于测试替换

        client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=timeout)
        kwargs = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = client.chat.completions.create(
                model=self.model, messages=messages, **kwargs
            )
        except Exception as e:                       # 网络/超时/限流 → 统一 ProviderError
            raise ProviderError(f"{self.name}: {e}") from e
        usage = resp.usage
        return LLMResult(
            content=resp.choices[0].message.content or "",
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            provider=self.name,
            model=self.model,
        )


def _configured_key(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value or value in {"CHANGE_ME", "changeme", "your-api-key"}:
        return None
    return value


def _build_registry() -> dict:
    """从 config 构建各 task 的 provider 链；缺 key 的 provider 不入链。"""
    cfg = current_app.config
    deepseek = None
    deepseek_key = _configured_key(cfg.get("DEEPSEEK_API_KEY"))
    if deepseek_key:
        deepseek = OpenAICompatProvider(
            "deepseek", deepseek_key,
            cfg.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            cfg.get("DEEPSEEK_MODEL", "deepseek-chat"))
    gpt = None
    openai_key = _configured_key(cfg.get("OPENAI_API_KEY"))
    if openai_key:
        gpt = OpenAICompatProvider(
            "openai", openai_key,
            cfg.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            cfg.get("OPENAI_MODEL", "gpt-4o-mini"))

    def chain(*providers):
        return [p for p in providers if p is not None]

    return {
        # NSFW 仅 DeepSeek 系列；OpenAI-compatible 网关跑 deepseek-* 时可复用。
        "nsfw":       chain(deepseek, gpt if _is_deepseek_model(gpt) else None),
        "correction": chain(deepseek, gpt),
        "translate":  chain(deepseek, gpt),
        "extract":    chain(deepseek, gpt),
        "tutor":      chain(deepseek, gpt),
        "general":    chain(deepseek, gpt),
    }


def _is_deepseek_model(provider) -> bool:
    return bool(provider and "deepseek" in (provider.model or "").lower())


# 测试可通过 set_registry 注入假 provider 链
_registry_override = None


def set_registry(registry):
    global _registry_override
    _registry_override = registry


def reset_breaker():
    global _breaker
    _breaker = CircuitBreaker()


def get_chain(task):
    reg = _registry_override if _registry_override is not None else _build_registry()
    return reg.get(task, reg.get("general", []))


def chat(messages, *, task="general", json_mode=False) -> LLMResult:
    """统一入口：按 task 的 provider 链做 failover，返回 LLMResult。"""
    chain = get_chain(task)
    if not chain:
        raise AllProvidersDown(f"task={task} 无可用 provider（检查 API key 配置）")

    started = time.time()
    last_err = None
    for provider in chain:
        if _breaker.is_open(provider.name):
            continue
        remaining = TOTAL_DEADLINE - (time.time() - started)
        if remaining <= 0:
            break
        timeout = min(PER_PROVIDER_TIMEOUT, remaining)
        try:
            result = provider.call(messages, timeout=timeout, json_mode=json_mode)
            _breaker.record_success(provider.name)
            return result
        except ProviderError as e:
            _breaker.record_failure(provider.name)
            last_err = e
            continue
    raise AllProvidersDown(f"task={task} 全部 provider 不可用：{last_err}")


# ---- 加词中心高层封装（对齐 demo services/llm_service.py） ----
# 走 chat() + failover；失败 fail-closed：返回 None（生成例句/笔记）或 {"error":...}
# （一键填充）。调方负责提示「AI 暂不可用」，不抛异常打断流程。
#
# language 传中文语言名（如「法语」），feedback_language 传解释/翻译语言名。
# service 层外可由 language_code→name 映射后传入（见 words._language_name）。

def _strip_quotes(s: str) -> str:
    """demo 同款清理：去成对引号包裹。"""
    s = (s or "").strip()
    s = s.replace("“", "").replace("”", "").replace("\"", "")
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        s = s[1:-1]
    return s


def generate_example(word, part_of_speech, meaning, *, language="英语",
                     feedback_language="中文"):
    """为一个词生成例句。失败返回 None（fail-closed）。"""
    if not word or not meaning:
        return None
    prompt = (
        f"请为{language}词或短语 '{word}' ({part_of_speech}) 生成一个自然、简单易懂且地道的{language}例句，"
        f"要体现它的含义：'{meaning}'与常用用法。"
        f"直接输出{language}例句与这句话的{feedback_language}意思，不要有任何其它解释。")
    messages = [
        {"role": "system", "content": f"你是一个{language}学习助手，擅长生成简单易懂的例句。"},
        {"role": "user", "content": prompt},
    ]
    try:
        return _strip_quotes(chat(messages, task="general").content)
    except AllProvidersDown:
        return None


def generate_note(word, part_of_speech, meaning, *, language="英语",
                  feedback_language="中文"):
    """生成学习笔记/记忆技巧。失败返回 None。"""
    if not word or not meaning:
        return None
    prompt = (
        f"请为{language}词或短语 '{word}' ({part_of_speech}) 编写一个简短的学习笔记或记忆技巧，50字以内，包含：\n"
        "1. 记忆技巧或联想方法\n2. 常见用法提示（如固定搭配等）\n3. 易混淆点提醒\n"
        f"帮助使用{feedback_language}学习的学生记住它的含义：'{meaning}'。"
        "只返回笔记内容，不要有标题或任何其他说明。")
    messages = [
        {"role": "system", "content": f"你是一个{language}学习助手，擅长帮助使用{feedback_language}学习的学生记忆{language}词语。"},
        {"role": "user", "content": prompt},
    ]
    try:
        return _strip_quotes(chat(messages, task="general").content)
    except AllProvidersDown:
        return None


def generate_full_word_info(word, *, language="英语", feedback_language="中文"):
    """AI 一键填充：返回 {"definitions": [{part_of_speech,meaning,example,note}, ...]}。

    失败/非法输入返回 {"error": "..."}（对齐 demo generate_full_word_info）。
    provenance：走 extract 链（DeepSeek 主），JSON 模式保证可解析。
    """
    import json
    if not word:
        return {"error": "单词不能为空"}
    prompt = f"""请为{language}词或短语 '{word}' 生成完整的学习信息。

可用的词性列表（共12个）：
- n. (名词)  - v. (动词)  - adj. (形容词)  - adv. (副词)
- prep. (介词)  - conj. (连词)  - pron. (代词)  - interj. (感叹词)
- num. (数词)  - art. (冠词)  - phr. (短语)

要求：
1. 首先验证输入是否为合法的{language}词或短语，如果不是（如其它语言、数字、乱码等），返回包含error字段的JSON
2. 按词性分组，每个词性一个definition对象
3. 同一词性如果有多个释义，用分号"；"分隔放在meaning字段中；meaning 必须使用{feedback_language}
4. 例句：{language}例句\n{feedback_language}翻译，自然简单易懂，体现释义含义与常用用法
5. 学习笔记包含巧记技巧、常用搭配等，80字以内，必须使用{feedback_language}
6. 排在前面的更常用
严格只返回如下 JSON：
{{"definitions":[{{"part_of_speech":"词性","meaning":"{feedback_language}释义","example":"{language}例句\\n{feedback_language}翻译","note":"{feedback_language}学习笔记"}}]}}
失败：{{"error":"原因"}}"""
    messages = [
        {"role": "system", "content": f"你是一个专业的{language}学习助手，擅长分析单词并生成完整的学习资料。你必须返回有效的JSON格式。请仔细验证输入是否为合法的{language}单词。"},
        {"role": "user", "content": prompt},
    ]
    try:
        content = chat(messages, task="extract", json_mode=True).content
    except AllProvidersDown:
        return {"error": "AI服务暂时不可用，请稍后重试"}
    try:
        data = json.loads(content)
    except (ValueError, TypeError):
        return {"error": "AI返回格式错误，请重试"}
    if isinstance(data, dict) and "error" in data:
        return data
    if not (isinstance(data, dict) and data.get("definitions")):
        return {"error": "AI返回数据格式错误"}
    return {"definitions": data["definitions"]}
