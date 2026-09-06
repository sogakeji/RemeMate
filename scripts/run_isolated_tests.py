#!/usr/bin/env python3
"""Run tests against a PostgreSQL instance owned by this invocation."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "postgres:16"
LABEL = "com.rememate.isolated-tests"


class RunnerError(RuntimeError):
    """A safe operational error whose text never contains credentials."""


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run pytest or migration checks in a disposable PostgreSQL 16 container."
    )
    parser.add_argument("--migration-check", action="store_true")
    parser.add_argument(
        "--database-timezone",
        choices=("UTC", "Asia/Shanghai"),
        default="UTC",
        help="database session default used by the disposable test database",
    )
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.pytest_args[:1] == ["--"]:
        args.pytest_args = args.pytest_args[1:]
    if args.migration_check and args.pytest_args:
        parser.error("--migration-check does not accept pytest arguments")
    return args


def _docker(*args: str, input_text: str | None = None,
            check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["docker", *args], cwd=ROOT, input=input_text,
            capture_output=True, text=True, timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RunnerError("docker command failed") from exc
    if check and result.returncode:
        raise RunnerError("docker command failed")
    return result


def _clean_environment() -> dict[str, str]:
    allowed = {
        "HOME", "LANG", "LC_ALL", "PATH", "SYSTEMROOT", "TEMP", "TMP",
        "USER", "USERPROFILE", "SSL_CERT_DIR", "SSL_CERT_FILE",
    }
    env = {key: value for key, value in os.environ.items() if key in allowed}
    env["PYTHON_DOTENV_DISABLED"] = "1"
    return env


def _wait_until_ready(container_id: str) -> None:
    for _ in range(60):
        ready = _docker(
            "exec", container_id, "pg_isready", "-U", "postgres", "-d", "postgres",
            check=False,
        )
        if ready.returncode == 0:
            return
        time.sleep(1)
    raise RunnerError("isolated PostgreSQL did not become ready")


def _bootstrap(
    container_id: str, passwords: dict[str, str], database_timezone: str,
) -> None:
    statements = [
        f"CREATE ROLE rememate_owner LOGIN PASSWORD '{passwords['owner']}';",
        f"CREATE ROLE rememate LOGIN PASSWORD '{passwords['app']}';",
        ("CREATE ROLE rememate_dispatch LOGIN BYPASSRLS PASSWORD "
         f"'{passwords['dispatch']}';"),
        "CREATE DATABASE rememate_test OWNER rememate_owner;",
        r"\connect rememate_test",
        "ALTER SCHEMA public OWNER TO rememate_owner;",
        "GRANT USAGE ON SCHEMA public TO rememate, rememate_dispatch;",
        (
            "ALTER DEFAULT PRIVILEGES FOR ROLE rememate_owner IN SCHEMA public "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES "
            "TO rememate, rememate_dispatch;"
        ),
        ("ALTER DEFAULT PRIVILEGES FOR ROLE rememate_owner IN SCHEMA public "
         "GRANT USAGE, SELECT ON SEQUENCES TO rememate, rememate_dispatch;"),
        "REVOKE CREATE ON SCHEMA public FROM PUBLIC;",
        f"ALTER DATABASE rememate_test SET timezone TO '{database_timezone}';",
    ]
    _docker(
        "exec", "-i", container_id, "psql", "-v", "ON_ERROR_STOP=1",
        "-U", "postgres", "-d", "postgres", input_text="\n".join(statements) + "\n",
    )


def _published_port(container_id: str) -> int:
    output = _docker("port", container_id, "5432/tcp").stdout.strip()
    try:
        host, raw_port = output.rsplit(":", 1)
        port = int(raw_port)
    except (ValueError, TypeError) as exc:
        raise RunnerError("docker did not publish the PostgreSQL port") from exc
    if host not in {"127.0.0.1", "localhost"} or not 1 <= port <= 65535:
        raise RunnerError("docker published PostgreSQL on an unsafe endpoint")
    return port


def _database_environment(
    port: int, passwords: dict[str, str],
) -> tuple[dict[str, str], list[str]]:
    app_url = f"postgresql://rememate:{passwords['app']}@127.0.0.1:{port}/rememate_test"
    dispatch_url = (
        f"postgresql://rememate_dispatch:{passwords['dispatch']}"
        f"@127.0.0.1:{port}/rememate_test"
    )
    owner_url = (
        f"postgresql://rememate_owner:{passwords['owner']}"
        f"@127.0.0.1:{port}/rememate_test"
    )
    env = _clean_environment()
    env.update({
        "DATABASE_URL": app_url,
        "DISPATCH_DATABASE_URL": dispatch_url,
        "MIGRATE_DATABASE_URL": owner_url,
        "TEST_DATABASE_HOST": "127.0.0.1",
        "TEST_DATABASE_PORT": str(port),
        "TEST_DATABASE_URL": app_url,
        "TEST_DISPATCH_DATABASE_URL": dispatch_url,
        "FLASK_APP": "wsgi:app",
        "FLASK_ENV": "development",
    })
    return env, list(passwords.values())


def _verify_database_contract(env: dict[str, str]) -> None:
    expected = (
        (env["MIGRATE_DATABASE_URL"], "rememate_owner", False),
        (env["TEST_DATABASE_URL"], "rememate", False),
        (env["TEST_DISPATCH_DATABASE_URL"], "rememate_dispatch", True),
    )
    try:
        for url, role, bypass_rls in expected:
            engine = create_engine(url)
            try:
                with engine.connect() as connection:
                    row = connection.execute(text(
                        "SELECT current_database(), current_user, r.rolsuper, "
                        "r.rolbypassrls, "
                        "has_schema_privilege(current_user, 'public', 'CREATE') "
                        "FROM pg_roles AS r WHERE r.rolname = current_user"
                    )).one()
                if tuple(row) != (
                    "rememate_test", role, False, bypass_rls, role == "rememate_owner"
                ):
                    raise RunnerError("isolated database role contract failed")
            finally:
                engine.dispose()
    except RunnerError:
        raise
    except Exception as exc:
        raise RunnerError("isolated database role verification failed") from exc


def _run_visible(command: list[str], env: dict[str, str], secrets_to_hide: list[str]) -> int:
    try:
        result = subprocess.run(
            command, cwd=ROOT, env=env, capture_output=True, text=True,
        )
    except OSError as exc:
        raise RunnerError("test command could not start") from exc
    output = (result.stdout or "") + (result.stderr or "")
    for secret in secrets_to_hide:
        output = output.replace(secret, "[REDACTED]")
    if output:
        print(output, end="" if output.endswith("\n") else "\n")
    return result.returncode


def _migration_revisions() -> tuple[str, str]:
    try:
        config = Config(str(ROOT / "migrations" / "alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "migrations"))
        scripts = ScriptDirectory.from_config(config)
        heads = scripts.get_heads()
        if len(heads) != 1:
            raise RunnerError(
                f"migration graph must have one head; found {len(heads)}"
            )
        head = heads[0]
        parent = scripts.get_revision(head).down_revision
        if not isinstance(parent, str):
            raise RunnerError("migration head must have exactly one parent")
        return head, parent
    except RunnerError:
        raise
    except Exception as exc:
        raise RunnerError("invalid migration graph") from exc


def _run_migration_checks(env: dict[str, str], hidden: list[str]) -> int:
    head, parent = _migration_revisions()
    for command in (
        [sys.executable, "-m", "flask", "db", "downgrade", parent],
        [sys.executable, "-m", "flask", "db", "upgrade", head],
        [sys.executable, "scripts/check_migration_metadata.py"],
    ):
        returncode = _run_visible(command, env, hidden)
        if returncode:
            return returncode
    print(f"migration check: single head {head}; round trip {parent} -> {head}; metadata clean")
    return 0


def _run_in_container(args: argparse.Namespace) -> int:
    if args.migration_check:
        _migration_revisions()
    run_id = secrets.token_hex(8)
    name = f"rememate-tests-{run_id}"
    passwords = {key: secrets.token_hex(24) for key in ("postgres", "owner", "app", "dispatch")}
    container_id: str | None = None

    with tempfile.TemporaryDirectory(prefix="rememate-tests-") as temp_dir:
        env_file = Path(temp_dir, "postgres.env")
        env_file.write_text(
            f"POSTGRES_PASSWORD={passwords['postgres']}\nPOSTGRES_DB=postgres\n",
            encoding="utf-8",
        )
        os.chmod(env_file, 0o600)
        try:
            created = _docker(
                "run", "-d", "--name", name,
                "--label", f"{LABEL}={run_id}",
                "--publish", "127.0.0.1::5432",
                "--tmpfs", "/var/lib/postgresql/data:rw,noexec,nosuid,size=512m",
                "--env-file", str(env_file), IMAGE,
            )
            candidate = created.stdout.strip()
            if not candidate:
                raise RunnerError(f"docker did not return a container ID; inspect {name}")
            container_id = candidate
            _wait_until_ready(container_id)
            _bootstrap(container_id, passwords, args.database_timezone)
            port = _published_port(container_id)
            env, hidden = _database_environment(port, passwords)
            _verify_database_contract(env)

            migration_rc = _run_visible(
                [sys.executable, "-m", "flask", "db", "upgrade"], env, hidden,
            )
            if migration_rc:
                return migration_rc
            if args.migration_check:
                return _run_migration_checks(env, hidden)
            pytest_args = args.pytest_args or ["-q"]
            return _run_visible(
                [sys.executable, "-m", "pytest", *pytest_args], env, hidden,
            )
        finally:
            if container_id is not None:
                removed = _docker("rm", "-f", "-v", container_id, check=False)
                if removed.returncode:
                    print(
                        f"warning: failed to remove owned container {container_id}",
                        file=sys.stderr,
                    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if shutil.which("docker") is None:
        print("error: docker is required for isolated tests", file=sys.stderr)
        return 2
    try:
        return _run_in_container(args)
    except RunnerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
