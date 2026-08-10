"""Access-log redaction for authentication links."""
from types import SimpleNamespace

import pytest
from gunicorn.glogging import Logger

from app.safe_access_logging import (
    RedactingAccessLogger,
    redact_sensitive_auth_tokens,
)


class FakeResponse:
    status = "200 OK"
    sent = 42
    headers = {"X-Response": "ok"}


class FakeRequest:
    headers = {"X-Request-ID": "request-1"}


def _logger(logger_class):
    logger = logger_class.__new__(logger_class)
    logger.now = lambda: "[time]"
    return logger


def _atoms(logger_class, environ):
    request = FakeRequest()
    request.headers = dict(request.headers)
    if "HTTP_X_AUTH_LINK" in environ:
        request.headers["X-Auth-Link"] = environ["HTTP_X_AUTH_LINK"]
    return logger_class.atoms(
        _logger(logger_class),
        FakeResponse(),
        request,
        environ,
        SimpleNamespace(seconds=1, microseconds=234),
    )


def test_ordinary_url_atoms_are_unchanged():
    environ = {
        "REMOTE_ADDR": "127.0.0.1",
        "REQUEST_METHOD": "GET",
        "RAW_URI": "/healthz?probe=1",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "PATH_INFO": "/healthz",
        "QUERY_STRING": "probe=1",
        "HTTP_REFERER": "https://staging.rememate.com/login",
    }

    assert _atoms(RedactingAccessLogger, environ) == _atoms(Logger, environ)


@pytest.mark.parametrize("route", ["verify-email", "reset-password"])
def test_auth_token_atoms_are_redacted(route):
    raw_token = "raw-token-for-access-log-test"
    encoded_route = (
        f"/%76erify-email%2F{raw_token}"
        if route == "verify-email"
        else f"/%72eset-password%2F{raw_token}"
    )
    nested_encoded_route = (
        f"/%72eset-password%2F{raw_token}"
        if route == "verify-email"
        else f"/%76erify-email%2F{raw_token}"
    )
    environ = {
        "REMOTE_ADDR": "127.0.0.1",
        "REQUEST_METHOD": "GET",
        "RAW_URI": f"{encoded_route}?next={nested_encoded_route}",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "PATH_INFO": f"/{route}/{raw_token}",
        "QUERY_STRING": f"next={nested_encoded_route}",
        "HTTP_REFERER": (
            f"https://staging.rememate.com{encoded_route}"
        ),
        "HTTP_X_AUTH_LINK": f"https://staging.rememate.com{encoded_route}",
        "AUTH_CONTEXT": f"callback={encoded_route}",
    }

    atoms = _atoms(RedactingAccessLogger, environ)
    string_values = [value for value in atoms.values() if isinstance(value, str)]
    nested_route = (
        "reset-password" if route == "verify-email" else "verify-email"
    )

    assert all(raw_token not in value for value in string_values)
    assert atoms["m"] == "GET"
    assert atoms["H"] == "HTTP/1.1"
    assert atoms["s"] == "200"
    assert atoms["{raw_uri}e"] == (
        f"/{route}/<redacted>?next=/{nested_route}/<redacted>"
    )
    assert atoms["{path_info}e"] == f"/{route}/<redacted>"
    assert atoms["{query_string}e"] == f"next=/{nested_route}/<redacted>"
    assert atoms["{http_referer}e"] == (
        f"https://staging.rememate.com/{route}/<redacted>"
    )
    assert atoms["{x-auth-link}i"] == (
        f"https://staging.rememate.com/{route}/<redacted>"
    )
    assert atoms["{auth_context}e"] == f"callback=/{route}/<redacted>"


def test_similar_non_auth_path_is_unchanged():
    environ = {
        "REMOTE_ADDR": "127.0.0.1",
        "REQUEST_METHOD": "GET",
        "RAW_URI": "/verify-emailing/token?probe=1",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "PATH_INFO": "/verify-emailing/token",
        "QUERY_STRING": "probe=1",
        "HTTP_REFERER": "https://staging.rememate.com/verify-emailing/token",
    }

    assert _atoms(RedactingAccessLogger, environ) == _atoms(Logger, environ)


@pytest.mark.parametrize(
    ("encoded_path", "canonical_path"),
    [
        (
            "/%76%65%72%69%66%79%2D%65%6d%61%69%6C%2fTOKEN",
            "/verify-email/<redacted>",
        ),
        (
            "/%72%65%73%65%74%2D%70%61%73%73%77%6F%72%64%2FTOKEN",
            "/reset-password/<redacted>",
        ),
    ],
)
def test_each_route_character_may_be_percent_encoded(
    encoded_path, canonical_path
):
    assert redact_sensitive_auth_tokens(encoded_path) == canonical_path
