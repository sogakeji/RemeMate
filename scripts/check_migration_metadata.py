#!/usr/bin/env python3
"""Return non-zero when a migrated database differs from application metadata."""
from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from app import create_app
from app.extensions import db

# Expression/raw-SQL indexes intentionally maintained by migration code.
_HAND_MANAGED_INDEXES = {
    "ix_output_entries_writerecent",
    "uq_users_email_lower",
    "uq_words_list_normalized_word",
}


def _include_object(obj, name, type_, reflected, compare_to):
    return not (type_ == "index" and name in _HAND_MANAGED_INDEXES)


def main() -> int:
    url = os.environ.get("MIGRATE_DATABASE_URL")
    if not url:
        print("metadata check: missing owner connection")
        return 2
    app = create_app("development")
    engine = create_engine(url)
    try:
        with app.app_context(), engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={
                    "compare_type": True,
                    "compare_server_default": True,
                    "include_object": _include_object,
                },
            )
            differences = compare_metadata(context, db.metadata)
    except Exception:
        print("metadata check: database inspection failed")
        return 2
    finally:
        engine.dispose()

    if differences:
        print(f"metadata drift: {len(differences)} difference(s)")
        for difference in differences:
            print(f"- {difference!r}")
        return 1
    print("metadata check: no drift")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
