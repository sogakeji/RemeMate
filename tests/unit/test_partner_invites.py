from app.services.partner_invites import (
    make_partner_invite_token,
    verify_partner_invite_token,
)


def test_partner_invite_token_is_email_bound_and_tamper_evident():
    token = make_partner_invite_token(
        "test-secret", 12, 34, "Partner@Example.com", now_ts=100,
    )

    parsed = verify_partner_invite_token(
        "test-secret", token, "partner@example.com", now_ts=101,
    )
    assert parsed is not None
    assert parsed.owner_user_id == 12
    assert parsed.partner_id == 34
    assert verify_partner_invite_token(
        "test-secret", token, "wrong@example.com", now_ts=101,
    ) is None
    assert verify_partner_invite_token(
        "test-secret", token + "x", "partner@example.com", now_ts=101,
    ) is None


def test_partner_invite_token_expires():
    token = make_partner_invite_token(
        "test-secret", 12, 34, "partner@example.com",
        ttl_seconds=5, now_ts=100,
    )

    assert verify_partner_invite_token(
        "test-secret", token, "partner@example.com", now_ts=106,
    ) is None
