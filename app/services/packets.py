"""Create and read immutable SessionPad feedback packet snapshots."""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from app.extensions import db
from app.models.packet import PartnerPacket, PartnerPacketItem, PartnerPacketThank
from app.models.partner import LanguagePartner
from app.models.recap import PartnerRecap, PartnerRecapItem
from app.models.user import User


MAX_PACKET_ITEMS = 20


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
        recap, sender.display_name, partner.display_name, ordered_items,
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
    items,
) -> str:
    snapshot = {
        "recap_title": recap.title,
        "session_date": recap.session_date.isoformat(),
        "sender": sender_display_name,
        "recipient": recipient_display_name,
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
