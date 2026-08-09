import requests
import pytest

from app.services.account_access import AuthMailDeliveryError
from app.services.resend_auth_mail import ResendAuthMailer


class FakeResponse:
    def __init__(self, response_id):
        self.status_code = 200
        self.response_id = response_id

    def json(self):
        return {"id": self.response_id}


class RecordingPost:
    def __init__(self):
        self.calls = []

    def __call__(self, url, *, headers, json, timeout, allow_redirects):
        self.calls.append({
            "url": url,
            "headers": headers,
            "json": json,
            "timeout": timeout,
            "allow_redirects": allow_redirects,
        })
        return FakeResponse(f"re_test_{len(self.calls)}")


def test_resend_auth_mail_sends_three_message_kinds_with_contract():
    post = RecordingPost()
    mailer = ResendAuthMailer(
        api_key="re_test_secret",
        from_address="RemeMate <no-reply@example.test>",
        post=post,
    )

    response_ids = [
        mailer.send_registration_verification(
            "alice@example.com",
            "https://example.test/verify-email/registration-token",
            "registration:41",
        ),
        mailer.send_account_guidance(
            "bob@example.com",
            "https://example.test/login",
            "https://example.test/forgot-password",
            "account-guidance:42",
        ),
        mailer.send_password_reset(
            "carol@example.com",
            "https://example.test/reset-password/reset-token",
            "password-reset:43",
        ),
    ]

    assert response_ids == ["re_test_1", "re_test_2", "re_test_3"]
    assert len(post.calls) == 3
    expected = [
        (
            "alice@example.com",
            "registration:41",
            "Verify your RemeMate account",
            ["https://example.test/verify-email/registration-token"],
        ),
        (
            "bob@example.com",
            "account-guidance:42",
            "RemeMate account access",
            [
                "https://example.test/login",
                "https://example.test/forgot-password",
            ],
        ),
        (
            "carol@example.com",
            "password-reset:43",
            "Reset your RemeMate password",
            ["https://example.test/reset-password/reset-token"],
        ),
    ]
    for call, (email, idempotency_key, subject, urls) in zip(
            post.calls, expected):
        assert call["url"] == "https://api.resend.com/emails"
        assert call["headers"] == {
            "Authorization": "Bearer re_test_secret",
            "User-Agent": "RemeMate/1.0",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
        }
        assert call["json"]["from"] == "RemeMate <no-reply@example.test>"
        assert call["json"]["to"] == [email]
        assert call["json"]["subject"] == subject
        assert all(url in call["json"]["text"] for url in urls)
        assert call["timeout"] == 5
        assert call["allow_redirects"] is False


def test_resend_auth_mail_normalizes_failures_without_leaking_secrets():
    secret_key = "re_test_secret"
    secret_body = "provider body secret"

    def raising_post(*args, **kwargs):
        raise requests.RequestException(secret_body)

    class ErrorResponse:
        def __init__(self, status_code, body, headers=None):
            self.status_code = status_code
            self.body = body
            self.headers = headers or {}

        def json(self):
            return self.body

    def response_post(response):
        def post(*args, **kwargs):
            return response

        return post

    cases = [
        (
            raising_post,
            "transport",
            None,
            "transport_error",
            None,
        ),
        (
            response_post(ErrorResponse(
                429,
                {"name": "rate_limit_exceeded", "message": secret_body},
                {"retry-after": "7"},
            )),
            "http",
            429,
            "rate_limit_exceeded",
            "7",
        ),
        (
            response_post(ErrorResponse(200, {"message": secret_body})),
            "invalid_response",
            200,
            "missing_id",
            None,
        ),
    ]

    for post, category, status_code, error_type, retry_after in cases:
        mailer = ResendAuthMailer(
            api_key=secret_key,
            from_address="RemeMate <no-reply@example.test>",
            post=post,
        )
        with pytest.raises(AuthMailDeliveryError) as raised:
            mailer.send_registration_verification(
                "alice@example.com",
                "https://example.test/verify-email/token",
                "registration:41",
            )

        error = raised.value
        assert error.category == category
        assert error.status_code == status_code
        assert error.error_type == error_type
        assert error.retry_after == retry_after
        assert "body" not in vars(error)
        assert "api_key" not in vars(error)
        assert secret_key not in str(error)
        assert secret_body not in str(error)
