"""Service layer for user-owned SessionPad recap papers."""
from datetime import date

from app.extensions import db
from app.models.recap import PartnerRecap, PartnerRecapItem
from app.services import partners as partners_svc
from app.services.timeutil import utc_now


ITEM_CHOICES = {
    "for_me": (
        ("expression", "词语 / 表达"),
        ("natural_phrase", "句子 / 自然说法"),
        ("private_note", "私人伙伴笔记"),
        ("next_time", "下次想聊 / 想复习"),
    ),
    "for_partner": (
        ("expression", "词语 / 表达"),
        ("correction", "错误修正"),
        ("natural_phrase", "自然说法 / 例句"),
        ("next_time", "下次建议"),
    ),
}
ITEM_LABELS = {
    "expression": "词语 / 表达",
    "natural_phrase": "自然说法",
    "correction": "错误修正",
    "private_note": "私人伙伴笔记",
    "next_time": "下次",
}


def list_recaps(user_id: int, partner_id: int) -> list[PartnerRecap]:
    return (
        PartnerRecap.query
        .filter_by(user_id=user_id, partner_id=partner_id)
        .order_by(
            PartnerRecap.session_date.desc(),
            PartnerRecap.created_at.desc(),
            PartnerRecap.id.desc(),
        )
        .all()
    )


def get_recap(
    user_id: int, partner_id: int, recap_id: int,
) -> PartnerRecap | None:
    return PartnerRecap.query.filter_by(
        id=recap_id, user_id=user_id, partner_id=partner_id,
    ).first()


def create_recap(
    user_id: int,
    partner_id: int,
    *,
    session_date: str | date,
    title: str | None = None,
) -> PartnerRecap | None:
    if partners_svc.get_partner(user_id, partner_id) is None:
        return None
    parsed_date = _parse_date(session_date)
    normalized_title = (title or "").strip()
    if len(normalized_title) > 120:
        raise ValueError("复盘标题不能超过 120 个字符")
    recap = PartnerRecap(
        user_id=user_id,
        partner_id=partner_id,
        session_date=parsed_date,
        title=normalized_title or None,
    )
    db.session.add(recap)
    db.session.commit()
    return recap


def list_items(
    user_id: int, partner_id: int, recap_id: int,
) -> dict[str, list[PartnerRecapItem]] | None:
    recap = get_recap(user_id, partner_id, recap_id)
    if recap is None:
        return None
    rows = (
        PartnerRecapItem.query
        .filter_by(user_id=user_id, recap_id=recap_id)
        .order_by(PartnerRecapItem.created_at.asc(),
                  PartnerRecapItem.id.asc())
        .all()
    )
    grouped = {"for_me": [], "for_partner": []}
    for item in rows:
        grouped[item.side].append(item)
    return grouped


def add_item(
    user_id: int,
    partner_id: int,
    recap_id: int,
    *,
    side: str,
    kind: str,
    content: str,
) -> PartnerRecapItem | None:
    recap = get_recap(user_id, partner_id, recap_id)
    if recap is None:
        return None
    normalized_side, normalized_kind, normalized_content = _validate_item(
        side, kind, content,
    )
    item = PartnerRecapItem(
        user_id=user_id,
        recap_id=recap_id,
        side=normalized_side,
        kind=normalized_kind,
        content=normalized_content,
    )
    recap.updated_at = utc_now()
    db.session.add(item)
    db.session.commit()
    return item


def update_item(
    user_id: int,
    partner_id: int,
    recap_id: int,
    item_id: int,
    *,
    kind: str,
    content: str,
) -> PartnerRecapItem | None:
    recap = get_recap(user_id, partner_id, recap_id)
    if recap is None:
        return None
    item = PartnerRecapItem.query.filter_by(
        id=item_id, user_id=user_id, recap_id=recap_id,
    ).first()
    if item is None:
        return None
    _, normalized_kind, normalized_content = _validate_item(
        item.side, kind, content,
    )
    item.kind = normalized_kind
    item.content = normalized_content
    recap.updated_at = utc_now()
    db.session.commit()
    return item


def delete_item(
    user_id: int, partner_id: int, recap_id: int, item_id: int,
) -> bool:
    recap = get_recap(user_id, partner_id, recap_id)
    if recap is None:
        return False
    item = PartnerRecapItem.query.filter_by(
        id=item_id, user_id=user_id, recap_id=recap_id,
    ).first()
    if item is None:
        return False
    db.session.delete(item)
    recap.updated_at = utc_now()
    db.session.commit()
    return True


def _validate_item(side: str, kind: str, content: str) -> tuple[str, str, str]:
    normalized_side = (side or "").strip()
    allowed = dict(ITEM_CHOICES.get(normalized_side, ()))
    normalized_kind = (kind or "").strip()
    if not allowed or normalized_kind not in allowed:
        raise ValueError("记录类型不正确")
    normalized_content = (content or "").strip()
    if not normalized_content or len(normalized_content) > 2000:
        raise ValueError("记录内容需为 1-2000 个字符")
    return normalized_side, normalized_kind, normalized_content


def _parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat((value or "").strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("请选择有效的交换日期") from exc
