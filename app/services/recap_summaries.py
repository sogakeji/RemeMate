"""Fail-soft AI summaries for user-owned SessionPad recaps."""
import hashlib
import json

from app.models.recap import PartnerRecap
from app.services import llm, quota as quota_svc, recaps as recaps_svc
from app.services.timeutil import utc_now
from app.services.words import _feedback_language_name


MAX_PROMPT_CHARS = 16_000
PRIVATE_KINDS = {"private_note"}


class SummaryUnavailable(Exception):
    """The optional AI enhancement failed without affecting recap data."""


def summary_snapshot(grouped_items: dict) -> tuple[list[dict], str]:
    """Return the provider-safe learning snapshot and its stable fingerprint."""
    rows = []
    for side in ("for_me", "for_partner"):
        for item in grouped_items.get(side, []):
            if item.kind in PRIVATE_KINDS:
                continue
            rows.append({
                "side": item.side,
                "kind": item.kind,
                "content": item.content.strip(),
            })
    encoded = json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return rows, hashlib.sha256(encoded).hexdigest()


def normalize_summary(data) -> dict | None:
    """Validate and bound the model's structured response."""
    if not isinstance(data, dict):
        return None
    gains = _string_list(data.get("gains"), limit=5, chars=240)
    topics = _string_list(data.get("topics"), limit=8, chars=40)
    next_steps = _string_list(data.get("next_steps"), limit=5, chars=240)
    depth = data.get("depth")
    if not isinstance(depth, str) or not depth.strip():
        return None
    if not gains or not topics or not next_steps:
        return None
    return {
        "gains": gains,
        "depth": depth.strip()[:400],
        "topics": topics,
        "next_steps": next_steps,
    }


def summary_state(recap: PartnerRecap, grouped_items: dict) -> dict:
    _, fingerprint = summary_snapshot(grouped_items)
    return {
        "payload": recap.ai_summary,
        "generated_at": recap.ai_summary_generated_at,
        "stale": bool(
            recap.ai_summary
            and recap.ai_summary_source_hash != fingerprint
        ),
    }


def generate_summary(
    user_id: int,
    partner_id: int,
    recap_id: int,
    *,
    feedback_language_code: str,
) -> dict | None:
    """Generate and atomically store one current summary for an owned recap."""
    recap = recaps_svc.get_recap(user_id, partner_id, recap_id)
    grouped = recaps_svc.list_items(user_id, partner_id, recap_id)
    if recap is None or grouped is None:
        return None
    rows, fingerprint = summary_snapshot(grouped)
    if not rows:
        raise ValueError("请先记录至少一条可总结的学习内容")
    if (
        recap.ai_summary
        and recap.ai_summary_source_hash == fingerprint
    ):
        return {"state": "current", "recap": recap}

    messages = _build_messages(
        rows, _feedback_language_name(feedback_language_code),
    )
    try:
        result = llm.chat(messages, task="general", json_mode=True)
    except llm.AllProvidersDown as exc:
        raise SummaryUnavailable() from exc
    payload = normalize_summary(_parse_json(result.content))
    if payload is None:
        raise SummaryUnavailable()

    locked = (
        PartnerRecap.query
        .filter_by(id=recap_id, user_id=user_id, partner_id=partner_id)
        .with_for_update()
        .first()
    )
    if locked is None:
        return None
    locked.ai_summary = payload
    locked.ai_summary_source_hash = fingerprint
    locked.ai_summary_generated_at = utc_now()
    quota_svc.record_feature_usage(
        user_id,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        provider=result.provider,
        model=result.model,
        feature="sessionpad_summary",
    )
    return {"state": "generated", "recap": locked}


def _build_messages(rows: list[dict], feedback_language: str) -> list[dict]:
    serialized = json.dumps(rows, ensure_ascii=False)
    if len(serialized) > MAX_PROMPT_CHARS:
        raise ValueError("复盘内容较多，请先整理后再生成总结")
    system = (
        "你是语言交换复盘助手。只根据用户提供的学习记录总结，不推断伙伴隐私。"
        f"所有内容使用{feedback_language}，严格输出 JSON，不要输出额外文字。"
    )
    user = f"""请总结这次双人语言交换。输出：
{{"gains":["本次收获，1-5条"],"depth":"讨论深度及简短依据","topics":["主题词，1-8个"],"next_steps":["下次建议，1-5条"]}}

记录中的 for_me 表示帮自己记，for_partner 表示帮伙伴记。
学习记录：{serialized}"""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _parse_json(content: str):
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        start = content.index("{")
        end = content.rindex("}") + 1
        return json.loads(content[start:end])
    except (ValueError, json.JSONDecodeError):
        return None


def _string_list(value, *, limit: int, chars: int) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = item.strip()[:chars]
        if normalized and normalized not in result:
            result.append(normalized)
        if len(result) == limit:
            break
    return result
