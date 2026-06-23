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


def _build_registry() -> dict:
    """从 config 构建各 task 的 provider 链；缺 key 的 provider 不入链。"""
    cfg = current_app.config
    deepseek = None
    if cfg.get("DEEPSEEK_API_KEY"):
        deepseek = OpenAICompatProvider(
            "deepseek", cfg["DEEPSEEK_API_KEY"],
            cfg.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"), "deepseek-chat")
    gpt = None
    if cfg.get("OPENAI_API_KEY"):
        gpt = OpenAICompatProvider(
            "openai", cfg["OPENAI_API_KEY"],
            cfg.get("OPENAI_BASE_URL", "https://api.openai.com/v1"), "gpt-4o-mini")

    def chain(*providers):
        return [p for p in providers if p is not None]

    return {
        # NSFW 仅 DeepSeek（GPT/Groq 审核 prompt 未验证）
        "nsfw":       chain(deepseek),
        "correction": chain(deepseek, gpt),
        "translate":  chain(deepseek, gpt),
        "extract":    chain(deepseek, gpt),
        "tutor":      chain(deepseek, gpt),
        "general":    chain(deepseek, gpt),
    }


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
