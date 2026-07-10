"""Create and read immutable SessionPad feedback packet snapshots."""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import or_, text
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
from app.services import words as words_svc
from app.services.timeutil import utc_now


MAX_PACKET_ITEMS = 20
ADOPTABLE_KINDS = {"expression", "natural_phrase", "correction"}


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


def add_received_item_to_candidates(
    recipient_user_id: int,
    packet_id: int,
    packet_item_id: int,
    term: str,
) -> dict | None:
    packet = PartnerPacket.query.filter_by(
        id=packet_id, recipient_user_id=recipient_user_id,
    ).first()
    item = PartnerPacketItem.query.filter_by(
        id=packet_item_id, packet_id=packet_id,
    ).first()
    if packet is None or item is None:
        return None
    if item.kind not in ADOPTABLE_KINDS:
        raise ValueError("这类反馈不能加入候选词")

    normalized_term = (term or "").strip()
    if not normalized_term or len(normalized_term) > 200:
        raise ValueError("候选词内容需为 1-200 个字符")
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

    existing_adoption = _adoption_result(
        recipient_user_id, packet_item_id,
    )
    if existing_adoption is not None:
        return existing_adoption

    existing_word = (
        Word.query
        .filter(
            Word.list_id == word_list.id,
            db.func.lower(Word.word) == normalized_term.lower(),
        )
        .first()
    )
    if existing_word is not None:
        return {"state": "existing-word", "word_id": existing_word.id}

    db.session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": 7_700_000_000 + packet_id},
    )
    existing_adoption = _adoption_result(
        recipient_user_id, packet_item_id,
    )
    if existing_adoption is not None:
        db.session.commit()
        return existing_adoption

    source = _source_for_received_packet(
        recipient_user_id, packet, word_list.id, language_code,
    )

    candidate = (
        WordCandidate.query
        .filter(
            WordCandidate.source_id == source.id,
            WordCandidate.user_id == recipient_user_id,
            WordCandidate.status.in_(["pending", "accepted"]),
            db.func.lower(WordCandidate.word) == normalized_term.lower(),
        )
        .first()
    )
    state = "already-candidate"
    if candidate is None:
        candidate = WordCandidate(
            source_id=source.id,
            user_id=recipient_user_id,
            word=normalized_term,
            source_example=item.content,
            status="pending",
        )
        db.session.add(candidate)
        db.session.flush()
        source.total_candidates = (source.total_candidates or 0) + 1
        state = "created"

    db.session.add(PartnerPacketItemAdoption(
        packet_item_id=packet_item_id,
        packet_id=packet_id,
        recipient_user_id=recipient_user_id,
        candidate_id=candidate.id,
    ))
    db.session.commit()
    return {
        "state": state,
        "candidate_id": candidate.id,
        "source_id": source.id,
    }


def _adoption_result(
    recipient_user_id: int,
    packet_item_id: int,
) -> dict | None:
    row = (
        db.session.query(
            PartnerPacketItemAdoption.candidate_id,
            WordCandidate.source_id,
        )
        .join(
            WordCandidate,
            WordCandidate.id == PartnerPacketItemAdoption.candidate_id,
        )
        .filter(
            PartnerPacketItemAdoption.packet_item_id == packet_item_id,
            PartnerPacketItemAdoption.recipient_user_id == recipient_user_id,
        )
        .first()
    )
    if row is None:
        return None
    return {
        "state": "already-candidate",
        "candidate_id": row.candidate_id,
        "source_id": row.source_id,
    }


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
