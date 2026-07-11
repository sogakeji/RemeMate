"""Service layer for user-owned language-partner records."""
from app.extensions import db
from app.models.partner import LanguagePartner
from app.services.words import _LANGUAGE_NAMES


def list_partners(user_id: int) -> list[LanguagePartner]:
    return (
        LanguagePartner.query
        .filter_by(user_id=user_id)
        .order_by(LanguagePartner.updated_at.desc(), LanguagePartner.id.desc())
        .all()
    )


def get_partner(user_id: int, partner_id: int) -> LanguagePartner | None:
    return LanguagePartner.query.filter_by(
        id=partner_id, user_id=user_id,
    ).first()


def create_partner(
    user_id: int,
    *,
    display_name: str,
    native_language_code: str | None = None,
    learning_language_code: str | None = None,
    private_note: str | None = None,
) -> LanguagePartner:
    values = _validated_values(
        display_name=display_name,
        native_language_code=native_language_code,
        learning_language_code=learning_language_code,
        private_note=private_note,
    )
    partner = LanguagePartner(user_id=user_id, **values)
    db.session.add(partner)
    db.session.commit()
    return partner


def update_partner(
    user_id: int,
    partner_id: int,
    *,
    display_name: str,
    native_language_code: str | None = None,
    learning_language_code: str | None = None,
    private_note: str | None = None,
) -> LanguagePartner | None:
    partner = get_partner(user_id, partner_id)
    if partner is None:
        return None
    values = _validated_values(
        display_name=display_name,
        native_language_code=native_language_code,
        learning_language_code=learning_language_code,
        private_note=private_note,
    )
    for key, value in values.items():
        setattr(partner, key, value)
    db.session.commit()
    return partner


def set_pending_invite(
    user_id: int,
    partner_id: int,
    token_hash: str,
) -> bool:
    """Make this token the only invitation that can claim the profile."""
    updated = (
        LanguagePartner.query
        .filter_by(id=partner_id, user_id=user_id, linked_user_id=None)
        .update({"invite_token_hash": token_hash}, synchronize_session=False)
    )
    db.session.commit()
    return updated == 1


def _validated_values(
    *,
    display_name: str,
    native_language_code: str | None,
    learning_language_code: str | None,
    private_note: str | None,
) -> dict:
    name = (display_name or "").strip()
    if not name or len(name) > 100:
        raise ValueError("伙伴昵称需为 1-100 个字符")
    native = _validate_language(native_language_code)
    learning = _validate_language(learning_language_code)
    note = (private_note or "").strip()
    if len(note) > 2000:
        raise ValueError("私人备注不能超过 2000 个字符")
    return {
        "display_name": name,
        "native_language_code": native,
        "learning_language_code": learning,
        "private_note": note or None,
    }


def _validate_language(code: str | None) -> str | None:
    normalized = (code or "").strip()
    if not normalized:
        return None
    if normalized not in _LANGUAGE_NAMES:
        raise ValueError("不支持该语言")
    return normalized
