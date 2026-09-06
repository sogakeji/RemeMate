"""CLI contract for the isolated PostgreSQL test runner."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "runner-secret-never-log"


def test_missing_docker_fails_safely_without_leaking_inherited_configuration(tmp_path):
    env = os.environ.copy()
    env["PATH"] = str(tmp_path)
    env["DATABASE_URL"] = f"postgresql://shared:{SENTINEL}@example.com/shared"

    result = subprocess.run(
        [sys.executable, "scripts/run_isolated_tests.py", "--", "-q"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "docker is required" in output.lower()
    assert SENTINEL not in output
    assert "Traceback" not in output


def _run_with_migration_graph(tmp_path, revisions):
    scripts = tmp_path / "scripts"
    migrations = tmp_path / "migrations"
    versions = migrations / "versions"
    bin_dir = tmp_path / "bin"
    scripts.mkdir()
    versions.mkdir(parents=True)
    bin_dir.mkdir()
    shutil.copy2(ROOT / "scripts" / "run_isolated_tests.py", scripts)
    (migrations / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")
    for revision, parent in revisions:
        (versions / f"{revision}.py").write_text(
            f"revision = {revision!r}\ndown_revision = {parent!r}\n"
            "branch_labels = None\ndepends_on = None\n"
            "def upgrade(): pass\ndef downgrade(): pass\n",
            encoding="utf-8",
        )
    if os.name == "nt":
        (bin_dir / "docker.bat").write_text("@exit /b 0\n", encoding="utf-8")
    else:
        docker = bin_dir / "docker"
        docker.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        docker.chmod(0o700)
    env = os.environ.copy()
    env["PATH"] = str(bin_dir)
    return subprocess.run(
        [sys.executable, scripts / "run_isolated_tests.py", "--migration-check"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )


def test_split_migration_graph_fails_before_starting_a_container(tmp_path):
    result = _run_with_migration_graph(tmp_path, [("one", None), ("two", None)])

    output = result.stdout + result.stderr
    assert result.returncode == 2
    assert "migration graph must have one head; found 2" in output
    assert "Traceback" not in output


def test_invalid_migration_parent_fails_without_traceback(tmp_path):
    result = _run_with_migration_graph(tmp_path, [("one", "missing")])

    output = result.stdout + result.stderr
    assert result.returncode == 2
    assert "invalid migration graph" in output
    assert "Traceback" not in output


def test_invalid_database_timezone_is_rejected_as_usage_error():
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_isolated_tests.py",
            "--database-timezone",
            "Europe/Paris",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 2
    assert "invalid choice" in output
    assert "Traceback" not in output


def test_unknown_option_fails_as_usage_error_before_touching_docker():
    result = subprocess.run(
        [sys.executable, "scripts/run_isolated_tests.py", "--unknown-option"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 2
    assert "unrecognized arguments" in output
    assert "Traceback" not in output
