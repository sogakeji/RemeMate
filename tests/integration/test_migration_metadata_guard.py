"""Migration metadata guard behavior against a real isolated PostgreSQL."""
import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]


def test_metadata_guard_rejects_real_schema_drift_without_credentials():
    owner_url = os.environ["MIGRATE_DATABASE_URL"]
    engine = create_engine(owner_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE users ADD COLUMN d01_unexpected text"))
        result = subprocess.run(
            [sys.executable, "scripts/check_migration_metadata.py"],
            cwd=ROOT,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=60,
        )
    finally:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE users DROP COLUMN d01_unexpected"))
        engine.dispose()

    output = result.stdout + result.stderr
    assert result.returncode == 1
    assert "metadata drift:" in output
    assert "remove_column" in output
    assert owner_url not in output
    assert "Traceback" not in output
