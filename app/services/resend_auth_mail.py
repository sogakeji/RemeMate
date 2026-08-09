"""Minimal requests adapter for authentication mail sent through Resend."""
from __future__ import annotations

import requests

from app.services.account_access import AuthMailDeliveryError


RESEND_EMAILS_URL = "https://api.resend.com/emails"
USER_AGENT = "RemeMate/1.0"


class ResendAuthMailer:
    def __init__(self, *, api_key, from_address, timeout=5, post=None):
        self.api_key = api_key
        self.from_address = from_address
        self.timeout = timeout
        self.post = post or requests.post

    def _send(self, email, subject, body, idempotency_key):
        try:
            response = self.post(
                RESEND_EMAILS_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "User-Agent": USER_AGENT,
                    "Content-Type": "application/json",
                    "Idempotency-Key": idempotency_key,
                },
                json={
                    "from": self.from_address,
                    "to": [email],
                    "subject": subject,
                    "text": body,
                },
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.RequestException:
            raise AuthMailDeliveryError(
                "transport",
                error_type="transport_error",
            ) from None

        if not 200 <= response.status_code < 300:
            try:
                error_body = response.json()
            except (TypeError, ValueError):
                error_body = {}
            error_type = (
                error_body.get("name") or error_body.get("type")
                if isinstance(error_body, dict)
                else None
            ) or "http_error"
            headers = response.headers or {}
            retry_after = (
                headers.get("retry-after")
                or headers.get("Retry-After")
            )
            raise AuthMailDeliveryError(
                "http",
                status_code=response.status_code,
                error_type=error_type,
                retry_after=retry_after,
            )

        try:
            response_body = response.json()
        except (TypeError, ValueError):
            response_body = {}
        response_id = (
            response_body.get("id")
            if isinstance(response_body, dict)
            else None
        )
        if not response_id:
            raise AuthMailDeliveryError(
                "invalid_response",
                status_code=response.status_code,
                error_type="missing_id",
            )
        return response_id

    def send_registration_verification(
            self, email, verification_url, idempotency_key):
        return self._send(
            email,
            "Verify your RemeMate account",
            f"Verify your RemeMate account: {verification_url}",
            idempotency_key,
        )

    def send_account_guidance(
            self, email, login_url, forgot_password_url, idempotency_key):
        return self._send(
            email,
            "RemeMate account access",
            f"Sign in: {login_url}\nForgot password: {forgot_password_url}",
            idempotency_key,
        )

    def send_password_reset(self, email, reset_url, idempotency_key):
        return self._send(
            email,
            "Reset your RemeMate password",
            f"Reset your RemeMate password: {reset_url}",
            idempotency_key,
        )
