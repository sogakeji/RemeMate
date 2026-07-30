"""Service layer for user-owned SessionPad recap papers."""
from datetime import date

from app.extensions import db
from app.models.intake import IntakeSource, WordCandidate
from app.models.recap import PartnerRecap, PartnerRecapItem
from app.models.word import WordList
from app.services import partners as partners_svc, words as words_svc
from app.services import sessionpad_candidates as candidate_svc
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
ITEM_CHOICE_LABELS = {
    side: dict(choices) for side, choices in ITEM_CHOICES.items()
}
ITEM_LABELS = {
    "expression": "词语 / 表达",
    "natural_phrase": "自然说法",
    "correction": "错误修正",
    "private_note": "私人伙伴笔记",
    "next_time": "下次",
}
ITEM_PROMPTS = {
    "for_me": {
        "expression": "记下一个想掌握的词语或表达",
        "natural_phrase": "记下对方教你的自然说法",
        "private_note": "写下只给自己看的伙伴笔记",
        "next_time": "记下下次想聊或想复习的内容",
    },
    "for_partner": {
        "expression": "记下一个值得对方掌握的词语或表达",
        "correction": "写下对方的原句和你的修正",
        "natural_phrase": "写下更自然的说法或例句",
        "next_time": "写下给对方的下次练习建议",
    },
}
CANDIDATE_KINDS = {"expression", "natural_phrase"}


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
) -> tuple[str, str] | None:
    recap = get_recap(user_id, partner_id, recap_id)
    if recap is None:
        return None
    item = PartnerRecapItem.query.filter_by(
        id=item_id, user_id=user_id, recap_id=recap_id,
    ).first()
    if item is None:
        return None
    location = (item.side, item.kind)
    db.session.delete(item)
    recap.updated_at = utc_now()
    db.session.commit()
    return location


def candidate_source_ids(
    user_id: int,
    grouped_items: dict[str, list[PartnerRecapItem]],
) -> dict[int, int]:
    items = [
        item for side_items in grouped_items.values() for item in side_items
        if item.candidate_id is not None
    ]
    candidate_ids = {item.candidate_id for item in items}
    if not candidate_ids:
        return {}
    rows = (
        WordCandidate.query
        .with_entities(WordCandidate.id, WordCandidate.source_id)
        .filter(
            WordCandidate.user_id == user_id,
            WordCandidate.id.in_(candidate_ids),
        )
        .all()
    )
    source_by_candidate = {candidate_id: source_id
                           for candidate_id, source_id in rows}
    return {
        item.id: source_by_candidate[item.candidate_id]
        for item in items if item.candidate_id in source_by_candidate
    }


def add_item_to_candidates(
    user_id: int,
    partner_id: int,
    recap_id: int,
    item_id: int,
) -> dict | None:
    partner = partners_svc.get_partner(user_id, partner_id)
    recap = get_recap(user_id, partner_id, recap_id)
    if partner is None or recap is None:
        return None

    source = None
    if recap.intake_source_id:
        source = IntakeSource.query.filter_by(
            id=recap.intake_source_id,
            user_id=user_id,
            source_type="sessionpad",
        ).first()
    language_code = (
        source.language_code if source is not None
        else partner.native_language_code
    )
    if not language_code:
        raise ValueError("请先为伙伴设置母语")
    if language_code not in words_svc.get_learning_languages(user_id):
        language_name = words_svc._language_name(language_code)
        raise ValueError(f"请先在设置中把{language_name}加入正在学")

    word_list = WordList.query.filter_by(
        user_id=user_id,
        language_code=language_code,
    ).first()
    if word_list is None:
        word_list = words_svc.get_or_create_language_list(
            user_id,
            language_code,
        )

    recap = (
        PartnerRecap.query
        .filter_by(id=recap_id, user_id=user_id, partner_id=partner_id)
        .with_for_update()
        .first()
    )
    item = (
        PartnerRecapItem.query
        .filter_by(id=item_id, user_id=user_id, recap_id=recap_id)
        .with_for_update()
        .first()
    )
    if recap is None or item is None:
        return None
    if item.side != "for_me" or item.kind not in CANDIDATE_KINDS:
        raise ValueError("这类记录不能加入候选词")

    if item.candidate_id is not None:
        candidate = WordCandidate.query.filter_by(
            id=item.candidate_id,
            user_id=user_id,
        ).first()
        if candidate is not None:
            return {
                "state": "already-candidate",
                "candidate_id": candidate.id,
                "source_id": candidate.source_id,
            }

    drafts = candidate_svc.normalize_manual_candidates([{
        "term": item.content,
        "context": None,
    }])
    source = _source_for_recap(
        user_id,
        recap,
        partner,
        word_list.id,
        language_code,
    )
    creation = candidate_svc.create_sessionpad_candidates(
        user_id,
        source.id,
        drafts,
    )
    if creation is None:
        return None
    if not creation.candidate_ids:
        db.session.commit()
        return {"state": "existing-word"}

    item.candidate_id = creation.candidate_ids[0]
    db.session.commit()
    return {
        "state": "created" if creation.created_count else "already-candidate",
        "candidate_id": item.candidate_id,
        "source_id": source.id,
    }


def _source_for_recap(
    user_id: int,
    recap: PartnerRecap,
    partner,
    word_list_id: int,
    language_code: str,
) -> IntakeSource:
    if recap.intake_source_id:
        source = (
            IntakeSource.query
            .filter_by(
                id=recap.intake_source_id,
                user_id=user_id,
                source_type="sessionpad",
            )
            .with_for_update()
            .first()
        )
        if source is not None:
            return source

    source_name = recap.title or (
        f"{recap.session_date.isoformat()} · {partner.display_name}"
    )
    source = IntakeSource(
        user_id=user_id,
        source_type="sessionpad",
        language_code=language_code,
        word_list_id=word_list_id,
        original_name=source_name[:200],
        status="done",
        total_segments=0,
        total_candidates=0,
        completed_at=utc_now(),
    )
    db.session.add(source)
    db.session.flush()
    recap.intake_source_id = source.id
    return source


def _validate_item(side: str, kind: str, content: str) -> tuple[str, str, str]:
    normalized_side = (side or "").strip()
    allowed = ITEM_CHOICE_LABELS.get(normalized_side, {})
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
