"""Create and read immutable SessionPad feedback packet snapshots."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import case, func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from app.extensions import db
from app.models.intake import IntakeSource, WordCandidate
from app.models.packet import (
    PartnerPacket, PartnerPacketIntake, PartnerPacketItem,
    PartnerPacketItemAdoption, PartnerPacketThank,
)
from app.models.partner import LanguagePartner
from app.models.recap import PartnerRecap, PartnerRecapItem
from app.models.user import User
from app.models.word import Word, WordList
from app.services import llm, quota as quota_svc
from app.services import sessionpad_candidates as candidate_svc
from app.services import words as words_svc
from app.services.timeutil import utc_now


MAX_PACKET_ITEMS = 20
MAX_ADOPTION_TERMS = 20
MAX_TERM_SUGGESTIONS = 8
MAX_SUGGESTED_TERM_CHARS = 80
ADOPTABLE_KINDS = {"expression", "natural_phrase", "correction"}


class TermSuggestionUnavailable(Exception):
    """Optional AI suggestions failed; manual candidate splitting still works."""


@dataclass(frozen=True)
class RecapDeliveryStatus:
    state: str
    packet_count: int
    packet_id: int | None

    @property
    def label(self) -> str:
        if self.state == "thanked":
            return "对方已感谢"
        if self.state == "sent":
            return f"已发送 {self.packet_count} 份"
        return "待发送"


def recap_delivery_statuses(
    sender_user_id: int,
    recap_ids,
) -> dict[int, RecapDeliveryStatus]:
    """Batch recap-level delivery facts for one partner page."""
    normalized_ids = list(dict.fromkeys(int(value) for value in recap_ids))
    if not normalized_ids:
        return {}

    item_counts = dict(
        db.session.query(
            PartnerRecapItem.recap_id,
            func.count(PartnerRecapItem.id),
        )
        .filter(
            PartnerRecapItem.user_id == sender_user_id,
            PartnerRecapItem.recap_id.in_(normalized_ids),
            PartnerRecapItem.side == "for_partner",
        )
        .group_by(PartnerRecapItem.recap_id)
        .all()
    )
    packet_rows = (
        db.session.query(
            PartnerPacket.recap_id,
            func.count(PartnerPacket.id),
            func.max(PartnerPacket.id),
            func.max(case(
                (PartnerPacketThank.packet_id.isnot(None), PartnerPacket.id),
                else_=None,
            )),
        )
        .outerjoin(
            PartnerPacketThank,
            PartnerPacketThank.packet_id == PartnerPacket.id,
        )
        .filter(
            PartnerPacket.sender_user_id == sender_user_id,
            PartnerPacket.recap_id.in_(normalized_ids),
        )
        .group_by(PartnerPacket.recap_id)
        .all()
    )
    packets_by_recap = {row[0]: row[1:] for row in packet_rows}

    statuses = {}
    for recap_id in normalized_ids:
        packet_count, latest_packet_id, thanked_packet_id = (
            packets_by_recap.get(recap_id, (0, None, None))
        )
        if thanked_packet_id is not None:
            statuses[recap_id] = RecapDeliveryStatus(
                "thanked", packet_count, thanked_packet_id,
            )
        elif packet_count:
            statuses[recap_id] = RecapDeliveryStatus(
                "sent", packet_count, latest_packet_id,
            )
        elif item_counts.get(recap_id, 0):
            statuses[recap_id] = RecapDeliveryStatus(
                "pending", 0, None,
            )
    return statuses


def create_packet(
    sender_user_id: int,
    partner_id: int,
    recap_id: int,
    selected_item_ids,
) -> dict | None:
    item_ids = _normalize_item_ids(selected_item_ids)
    partner = (
        LanguagePartner.query
        .filter_by(id=partner_id, user_id=sender_user_id)
        .with_for_update()
        .first()
    )
    recap = (
        PartnerRecap.query
        .filter_by(
            id=recap_id, user_id=sender_user_id, partner_id=partner_id,
        )
        .with_for_update()
        .first()
    )
    if partner is None or recap is None:
        return None
    if partner.linked_user_id is None:
        raise ValueError("请先邀请伙伴绑定账号")
    if not partner.learning_language_code:
        raise ValueError("请先为伙伴设置正在学的语言")
    recipient_user_id = partner.linked_user_id

    rows = (
        PartnerRecapItem.query
        .filter(
            PartnerRecapItem.user_id == sender_user_id,
            PartnerRecapItem.recap_id == recap_id,
            PartnerRecapItem.side == "for_partner",
            PartnerRecapItem.id.in_(item_ids),
        )
        .with_for_update()
        .all()
    )
    item_by_id = {item.id: item for item in rows}
    if len(item_by_id) != len(item_ids):
        raise ValueError("只能发送当前复盘中帮他记的内容")
    ordered_items = [item_by_id[item_id] for item_id in item_ids]

    sender = db.session.get(User, sender_user_id)
    if sender is None:
        return None
    fingerprint = _snapshot_fingerprint(
        recap, sender.display_name, partner.display_name,
        partner.learning_language_code, ordered_items,
    )
    existing = _find_exact_packet(
        sender_user_id, recipient_user_id, recap_id, fingerprint,
    )
    if existing is not None:
        return {"state": "existing", "packet": existing}

    packet = PartnerPacket(
        sender_user_id=sender_user_id,
        recipient_user_id=recipient_user_id,
        partner_id=partner_id,
        recap_id=recap_id,
        sender_display_name=sender.display_name,
        recipient_display_name=partner.display_name,
        recap_title=recap.title,
        session_date=recap.session_date,
        language_code=partner.learning_language_code,
        content_fingerprint=fingerprint,
        item_count=len(ordered_items),
    )
    db.session.add(packet)
    for position, item in enumerate(ordered_items):
        packet.items.append(PartnerPacketItem(
            kind=item.kind,
            content=item.content,
            position=position,
        ))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = _find_exact_packet(
            sender_user_id, recipient_user_id, recap_id, fingerprint,
        )
        if existing is None:
            raise
        return {"state": "existing", "packet": existing}
    return {"state": "created", "packet": packet}


def list_received_packets(user_id: int) -> list[PartnerPacket]:
    return (
        PartnerPacket.query
        .filter_by(recipient_user_id=user_id)
        .order_by(PartnerPacket.created_at.desc(), PartnerPacket.id.desc())
        .all()
    )


def get_packet_for_user(
    user_id: int,
    packet_id: int,
) -> PartnerPacket | None:
    return (
        PartnerPacket.query
        .options(
            selectinload(PartnerPacket.items),
            joinedload(PartnerPacket.thank),
        )
        .filter(
            PartnerPacket.id == packet_id,
            or_(
                PartnerPacket.sender_user_id == user_id,
                PartnerPacket.recipient_user_id == user_id,
            ),
        )
        .first()
    )


def thank_packet(recipient_user_id: int, packet_id: int) -> str | None:
    packet = (
        PartnerPacket.query
        .options(joinedload(PartnerPacket.thank))
        .filter_by(id=packet_id, recipient_user_id=recipient_user_id)
        .first()
    )
    if packet is None:
        return None
    if packet.thank is not None:
        return "existing"

    thank = PartnerPacketThank(
        packet_id=packet_id,
        recipient_user_id=recipient_user_id,
    )
    db.session.add(thank)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = PartnerPacketThank.query.filter_by(
            packet_id=packet_id, recipient_user_id=recipient_user_id,
        ).first()
        if existing is None:
            raise
        return "existing"
    return "created"


def adoption_source_ids(
    recipient_user_id: int,
    packet_items,
) -> dict[int, int]:
    item_ids = [item.id for item in packet_items]
    if not item_ids:
        return {}
    rows = (
        db.session.query(
            PartnerPacketItemAdoption.packet_item_id,
            WordCandidate.source_id,
        )
        .join(
            WordCandidate,
            WordCandidate.id == PartnerPacketItemAdoption.candidate_id,
        )
        .filter(
            PartnerPacketItemAdoption.recipient_user_id == recipient_user_id,
            PartnerPacketItemAdoption.packet_item_id.in_(item_ids),
        )
        .all()
    )
    return {item_id: source_id for item_id, source_id in rows}


def get_received_packet_item(
    recipient_user_id: int,
    packet_id: int,
    packet_item_id: int,
) -> PartnerPacketItem | None:
    received = _received_packet_item(
        recipient_user_id, packet_id, packet_item_id,
    )
    return received[1] if received else None


def add_received_item_to_candidates(
    recipient_user_id: int,
    packet_id: int,
    packet_item_id: int,
    terms: str = "",
    candidate_rows: list[dict] | None = None,
) -> dict | None:
    received = _received_adoptable_item(
        recipient_user_id, packet_id, packet_item_id,
    )
    if received is None:
        return None
    packet, item = received

    if candidate_rows is None:
        drafts = candidate_svc.normalize_manual_candidates([
            {"term": term, "context": None}
            for term in _normalize_adoption_terms(terms)
        ])
    else:
        drafts = candidate_svc.normalize_submitted_candidates(
            candidate_rows,
            item.content,
        )

    language_code = packet.language_code
    if not language_code:
        raise ValueError("这份旧反馈没有语言信息，暂时不能加入候选词")
    if language_code not in words_svc.get_learning_languages(recipient_user_id):
        language_name = words_svc._language_name(language_code)
        raise ValueError(f"请先在设置中把{language_name}加入正在学")

    word_list = WordList.query.filter_by(
        user_id=recipient_user_id, language_code=language_code,
    ).first()
    if word_list is None:
        word_list = words_svc.get_or_create_language_list(
            recipient_user_id, language_code,
        )

    db.session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": 7_700_000_000 + packet_id},
    )
    source = _source_for_received_packet(
        recipient_user_id, packet, word_list.id, language_code,
    )
    creation = candidate_svc.create_sessionpad_candidates(
        recipient_user_id,
        source.id,
        drafts,
    )
    if creation is None:
        return None

    candidate_ids = list(creation.candidate_ids)
    if not candidate_ids:
        db.session.commit()
        return {
            "state": "existing-word",
            "candidate_count": 0,
            "created_count": 0,
            "existing_word_count": creation.existing_word_count,
        }

    adopted_ids = set(
        candidate_id for candidate_id, in (
            PartnerPacketItemAdoption.query
            .with_entities(PartnerPacketItemAdoption.candidate_id)
            .filter(
                PartnerPacketItemAdoption.packet_item_id == packet_item_id,
                PartnerPacketItemAdoption.recipient_user_id == recipient_user_id,
                PartnerPacketItemAdoption.candidate_id.in_(candidate_ids),
            )
            .all()
        )
    )
    for candidate_id in candidate_ids:
        if candidate_id not in adopted_ids:
            db.session.add(PartnerPacketItemAdoption(
                packet_item_id=packet_item_id,
                packet_id=packet_id,
                recipient_user_id=recipient_user_id,
                candidate_id=candidate_id,
            ))
    db.session.commit()
    return {
        "state": "created" if creation.created_count else "already-candidate",
        "candidate_count": len(candidate_ids),
        "created_count": creation.created_count,
        "existing_word_count": creation.existing_word_count,
        "source_id": source.id,
    }


def suggest_received_item_terms(
    recipient_user_id: int,
    packet_id: int,
    packet_item_id: int,
) -> dict | None:
    """Suggest editable word-level terms without creating any learning data."""
    received = _received_adoptable_item(
        recipient_user_id, packet_id, packet_item_id,
    )
    if received is None:
        return None
    packet, item = received
    language_code = packet.language_code
    if not language_code:
        raise ValueError("这份旧反馈没有语言信息，暂时不能提取词语")
    if language_code not in words_svc.get_learning_languages(recipient_user_id):
        language_name = words_svc._language_name(language_code)
        raise ValueError(f"请先在设置中把{language_name}加入正在学")

    language_name = words_svc._language_name(language_code)
    messages = _term_suggestion_messages(item.content, language_name)
    try:
        result = llm.chat(messages, task="extract", json_mode=True)
    except llm.AllProvidersDown as exc:
        raise TermSuggestionUnavailable() from exc
    quota_svc.record_feature_usage(
        recipient_user_id,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        provider=result.provider,
        model=result.model,
        feature="sessionpad_term_suggestions",
    )
    suggestions = candidate_svc.normalize_ai_suggestions(
        _parse_json_object(result.content),
        item.content,
    )
    if not suggestions:
        raise TermSuggestionUnavailable()
    return {"candidates": suggestions, "item": item}


def _normalize_adoption_terms(value: str) -> list[str]:
    terms = []
    seen = set()
    for line in (value or "").splitlines():
        term = line.strip()
        if not term:
            continue
        if len(term) > 200:
            raise ValueError("每个候选词需为 1-200 个字符")
        key = term.lower()
        if key not in seen:
            seen.add(key)
            terms.append(term)
    if not terms:
        raise ValueError("请至少填写一个候选词或表达")
    if len(terms) > MAX_ADOPTION_TERMS:
        raise ValueError(f"一次最多加入 {MAX_ADOPTION_TERMS} 个候选词")
    return terms


def normalize_term_suggestions(data) -> list[str]:
    """Accept only a small editable list from an untrusted model response."""
    if not isinstance(data, dict) or not isinstance(data.get("terms"), list):
        return []
    terms = []
    seen = set()
    for value in data["terms"]:
        if not isinstance(value, str):
            continue
        term = value.strip()
        if not term or len(term) > MAX_SUGGESTED_TERM_CHARS:
            continue
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        terms.append(term)
        if len(terms) == MAX_TERM_SUGGESTIONS:
            break
    return terms


def _term_suggestion_messages(content: str, language_name: str) -> list[dict]:
    system = (
        f"你是{language_name}学习材料整理助手。"
        "只提取可独立复用、值得记忆的词语、固定搭配或地道短表达。"
        "不要机械切句，不要返回完整句子、代词片段、功能词或普通高频句段。"
        "如果反馈包含错误修正，优先提取修正后的目标表达。"
        "严格输出 JSON，不要添加解释。"
    )
    user = (
        "从下面这条语言交换反馈中谨慎提取 1-8 个学习项；宁缺毋滥。"
        "每项脱离原句后仍应有学习价值，保留原语言写法并去重，"
        "每项不超过 80 个字符。"
        "context 必须是反馈原文中连续出现的短语或句子，只允许折叠空白，"
        "不得改写或编造；找不到可靠原文时设为 null。"
        "输出格式："
        "{\"candidates\":[{\"term\":\"词语或短表达\","
        "\"context\":\"原文中的连续片段\"}]}。"
        "找不到语境时，context 必须使用 JSON null，而不是字符串。\n\n"
        f"反馈：{content}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _parse_json_object(content: str):
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


def _received_adoptable_item(
    recipient_user_id: int,
    packet_id: int,
    packet_item_id: int,
) -> tuple[PartnerPacket, PartnerPacketItem] | None:
    received = _received_packet_item(
        recipient_user_id, packet_id, packet_item_id,
    )
    if received is None:
        return None
    packet, item = received
    if item.kind not in ADOPTABLE_KINDS:
        raise ValueError("这类反馈不能加入候选词")
    return packet, item


def _received_packet_item(
    recipient_user_id: int,
    packet_id: int,
    packet_item_id: int,
) -> tuple[PartnerPacket, PartnerPacketItem] | None:
    packet = PartnerPacket.query.filter_by(
        id=packet_id, recipient_user_id=recipient_user_id,
    ).first()
    item = PartnerPacketItem.query.filter_by(
        id=packet_item_id, packet_id=packet_id,
    ).first()
    if packet is None or item is None:
        return None
    return packet, item


def _source_for_received_packet(
    recipient_user_id: int,
    packet: PartnerPacket,
    word_list_id: int,
    language_code: str,
) -> IntakeSource:
    packet_intake = PartnerPacketIntake.query.filter_by(
        packet_id=packet.id, recipient_user_id=recipient_user_id,
    ).first()
    if packet_intake is not None:
        source = IntakeSource.query.filter_by(
            id=packet_intake.source_id, user_id=recipient_user_id,
        ).first()
        if source is None:
            raise RuntimeError("feedback packet intake source missing")
        return source

    source = IntakeSource(
        user_id=recipient_user_id,
        source_type="sessionpad",
        language_code=language_code,
        word_list_id=word_list_id,
        original_name=(
            f"反馈 · {packet.sender_display_name} · "
            f"{packet.session_date.isoformat()}"
        )[:200],
        status="done",
        total_segments=0,
        total_candidates=0,
        completed_at=utc_now(),
    )
    db.session.add(source)
    db.session.flush()
    db.session.add(PartnerPacketIntake(
        packet_id=packet.id,
        recipient_user_id=recipient_user_id,
        source_id=source.id,
    ))
    return source


def _normalize_item_ids(values) -> list[int]:
    normalized = []
    seen = set()
    try:
        for value in values or []:
            item_id = int(value)
            if item_id <= 0:
                raise ValueError
            if item_id not in seen:
                seen.add(item_id)
                normalized.append(item_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("选择的反馈内容不正确") from exc
    if not normalized:
        raise ValueError("请至少选择一条帮他记的内容")
    if len(normalized) > MAX_PACKET_ITEMS:
        raise ValueError(f"一次最多发送 {MAX_PACKET_ITEMS} 条内容")
    return normalized


def _snapshot_fingerprint(
    recap,
    sender_display_name: str,
    recipient_display_name: str,
    language_code: str,
    items,
) -> str:
    snapshot = {
        "recap_title": recap.title,
        "session_date": recap.session_date.isoformat(),
        "sender": sender_display_name,
        "recipient": recipient_display_name,
        "language": language_code,
        "items": [
            {"id": item.id, "kind": item.kind, "content": item.content}
            for item in items
        ],
    }
    encoded = json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _find_exact_packet(
    sender_user_id: int,
    recipient_user_id: int,
    recap_id: int,
    fingerprint: str,
) -> PartnerPacket | None:
    return PartnerPacket.query.filter_by(
        sender_user_id=sender_user_id,
        recipient_user_id=recipient_user_id,
        recap_id=recap_id,
        content_fingerprint=fingerprint,
    ).first()
