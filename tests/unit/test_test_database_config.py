"""Test startup contract, exercised in a subprocess without connecting to a DB."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "synthetic-secret-never-log"


def collect_with(**overrides):
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("TEST_DATABASE", "TEST_DISPATCH", "PG")):
            env.pop(key)
    env.update({
        "PYTHON_DOTENV_DISABLED": "1",
        "TEST_DATABASE_HOST": "127.0.0.1",
        "TEST_DATABASE_PORT": "55439",
        "TEST_DATABASE_URL": f"postgresql://rememate:{SENTINEL}@127.0.0.1:55439/rememate_test",
        "TEST_DISPATCH_DATABASE_URL": f"postgresql://rememate_dispatch:{SENTINEL}@127.0.0.1:55439/rememate_test",
    })
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "tests/integration/test_app_smoke.py", "-p", "no:cacheprovider"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=45,
    )


def test_collection_rejects_non_test_dispatch_database_without_logging_password():
    result = collect_with(TEST_DISPATCH_DATABASE_URL=(
        f"postgresql://rememate_dispatch:{SENTINEL}@127.0.0.1:55439/rememate_staging"
    ))
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "TEST_DISPATCH_DATABASE_URL" in output
    assert SENTINEL not in output


@pytest.mark.parametrize("url", [
    f"postgresql://rememate_dispatch:{SENTINEL}@127.0.0.1:55432/rememate_test",
    f"postgresql://rememate_dispatch:{SENTINEL}@example.com:55439/rememate_test",
    f"postgresql://rememate_owner:{SENTINEL}@127.0.0.1:55439/rememate_test",
    "sqlite:///rememate_test",
])
def test_collection_rejects_wrong_endpoint_driver_or_role(url):
    result = collect_with(TEST_DISPATCH_DATABASE_URL=url)
    assert result.returncode != 0
    assert SENTINEL not in result.stdout + result.stderr


def test_collection_rejects_query_overrides_and_libpq_environment():
    query = collect_with(TEST_DATABASE_URL=(
        f"postgresql://rememate:{SENTINEL}@127.0.0.1:55439/rememate_test?host=elsewhere"
    ))
    assert query.returncode != 0
    inherited = collect_with(PGSERVICE="shared-database")
    assert inherited.returncode != 0
    assert SENTINEL not in query.stdout + query.stderr + inherited.stdout + inherited.stderr


def test_python_dotenv_disable_flag_blocks_adjacent_env_file(tmp_path):
    shutil.copy2(ROOT / "config.py", tmp_path / "config.py")
    (tmp_path / ".env").write_text("D01_DOTENV_SENTINEL=loaded\n", encoding="utf-8")
    env = os.environ.copy()
    env.pop("D01_DOTENV_SENTINEL", None)
    env["PYTHON_DOTENV_DISABLED"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", (
            "import os, config; "
            "print(os.environ.get('D01_DOTENV_SENTINEL', 'not-loaded'))"
        )],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "not-loaded"


def test_valid_explicit_pair_collects_without_connecting():
    result = collect_with()
    assert result.returncode == 0
    assert "test_app_boots_and_healthz" in result.stdout


@pytest.mark.parametrize("overrides", [
    {"TEST_DATABASE_HOST": None},
    {"TEST_DATABASE_PORT": None},
    {"TEST_DATABASE_PORT": "not-a-port"},
    {"TEST_DATABASE_URL": None},
    {"TEST_DISPATCH_DATABASE_URL": None},
    {"TEST_DATABASE_URL": f"postgresql://rememate:{SENTINEL}@127.0.0.1:55439/rememate_test_backup"},
    {"TEST_DATABASE_URL": f"postgresql://rememate:{SENTINEL}@127.0.0.1:bad/rememate_test"},
    {"TEST_DATABASE_URL": f"not-a-url-{SENTINEL}"},
    {"TEST_DATABASE_URL": "postgresql://rememate@127.0.0.1:55439/rememate_test"},
], ids=["host-required", "port-required", "invalid-port", "app-required",
        "dispatch-required", "exact-name", "malformed-url-port", "malformed-url", "password-required"])
def test_invalid_configuration_fails_closed_without_secret_output(overrides):
    result = collect_with(**overrides)
    assert result.returncode != 0
    assert SENTINEL not in result.stdout + result.stderr
