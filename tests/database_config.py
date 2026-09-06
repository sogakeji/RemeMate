"""Fail closed before test engines are constructed; never include URLs in errors."""
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


def database_urls(env):
    if any(key.startswith("PG") and value for key, value in env.items()):
        raise RuntimeError("libpq environment overrides are not allowed for tests")
    host = env.get("TEST_DATABASE_HOST")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("TEST_DATABASE_HOST: explicit loopback host required")
    try:
        port = int(env.get("TEST_DATABASE_PORT", ""))
        if not 1 <= port <= 65535:
            raise ValueError
    except (ValueError, TypeError):
        raise RuntimeError("TEST_DATABASE_PORT: explicit valid port required") from None
    urls = []
    for key, role in (("TEST_DATABASE_URL", "rememate"),
                      ("TEST_DISPATCH_DATABASE_URL", "rememate_dispatch")):
        raw = env.get(key)
        if not raw:
            raise RuntimeError(f"{key}: explicit test configuration required")
        try:
            url = make_url(raw)
        except (ArgumentError, ValueError, TypeError):
            raise RuntimeError(f"{key}: invalid database URL") from None
        if url.database != "rememate_test":
            raise RuntimeError(f"{key}: database must be exactly rememate_test")
        if (url.drivername not in {"postgresql", "postgresql+psycopg2"}
                or url.username != role):
            raise RuntimeError(f"{key}: PostgreSQL test role required")
        if url.host != host or url.port != port:
            raise RuntimeError(f"{key}: endpoint differs from explicit test target")
        if url.query or not url.password:
            raise RuntimeError(f"{key}: explicit password and no query options required")
        urls.append(raw)
    return tuple(urls)
