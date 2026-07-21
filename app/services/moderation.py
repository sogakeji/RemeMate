"""Dedicated public-content moderation.

Correction output is advice, not moderation authority.  This module is the
only service allowed to decide whether a saved output may be published.
"""
import json
from dataclasses import dataclass

from app.services import llm


@dataclass
class ModerationResult:
    is_nsfw: bool
    provider: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    degraded: bool = False


_SYSTEM = """你是公开学习社区的内容安全审核器。
判断用户准备公开的文本是否包含成人、露骨性内容、严重暴力或其他不适宜公开内容。
只输出 JSON：{"is_nsfw": true|false}。不要改写文本，不要输出解释。"""


def classify_public_text(text: str) -> ModerationResult:
    """Classify publish eligibility through the dedicated ``nsfw`` chain.

    Missing providers and malformed output fail closed without turning a
    successful correction into a degraded correction.
    """
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": text or ""},
    ]
    try:
        response = llm.chat(messages, task="nsfw", json_mode=True)
    except llm.AllProvidersDown:
        return ModerationResult(is_nsfw=True, degraded=True)

    data = _parse(response.content)
    value = data.get("is_nsfw") if isinstance(data, dict) else None
    if not isinstance(value, bool):
        return ModerationResult(
            is_nsfw=True,
            provider=response.provider,
            model=response.model,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            degraded=True,
        )
    return ModerationResult(
        is_nsfw=value,
        provider=response.provider,
        model=response.model,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
    )


def _parse(content):
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        start = content.index("{")
        end = content.rindex("}") + 1
        return json.loads(content[start:end])
    except (AttributeError, ValueError, json.JSONDecodeError):
        return None
