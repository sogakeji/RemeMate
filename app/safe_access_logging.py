"""Redact authentication tokens from Gunicorn access-log atoms."""
import re

from gunicorn.glogging import Logger


def _encoded_character_pattern(character: str) -> str:
    encoded = f"{ord(character):02x}"
    encoded = "".join(
        f"[{part.lower()}{part.upper()}]" if part in "abcdef" else part
        for part in encoded
    )
    return rf"(?:{re.escape(character)}|%{encoded})"


def _encoded_route_pattern(route: str) -> str:
    return "".join(_encoded_character_pattern(character) for character in route)


_AUTH_TOKEN_PATTERN = re.compile(
    rf"/(?P<verify>{_encoded_route_pattern('verify-email')})(?:/|%2[fF])[^/?#\s]+"
    rf"|/(?P<reset>{_encoded_route_pattern('reset-password')})(?:/|%2[fF])[^/?#\s]+"
)


def _replace_auth_token(match: re.Match[str]) -> str:
    if match.group("verify") is not None:
        return "/verify-email/<redacted>"
    return "/reset-password/<redacted>"


def redact_sensitive_auth_tokens(value: str) -> str:
    """Replace sensitive auth-link path segments without changing other text."""
    return _AUTH_TOKEN_PATTERN.sub(_replace_auth_token, value)


class RedactingAccessLogger(Logger):
    """Gunicorn logger that redacts auth tokens from every string atom."""

    def atoms(self, resp, req, environ, request_time):
        atoms = super().atoms(resp, req, environ, request_time)
        return {
            key: redact_sensitive_auth_tokens(value)
            if isinstance(value, str)
            else value
            for key, value in atoms.items()
        }
