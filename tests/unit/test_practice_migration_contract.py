from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/e9f0a1b2c3d4_add_practice_voice_blocked_state.py"
)


def test_voice_blocked_downgrade_repairs_rows_before_legacy_check():
    source = MIGRATION.read_text(encoding="utf-8")
    downgrade = source[source.index("def downgrade():"):]

    repair = "UPDATE practice_sessions"
    legacy_check = "op.create_check_constraint"
    drop_column = 'op.drop_column("practice_sessions", "blocked_at")'
    no_force = "ALTER TABLE practice_sessions NO FORCE ROW LEVEL SECURITY;"
    force = "ALTER TABLE practice_sessions FORCE ROW LEVEL SECURITY;"

    assert "SET status = 'abandoned'" in downgrade
    assert "abandoned_at = COALESCE(abandoned_at, blocked_at)" in downgrade
    assert "WHERE status = 'blocked'" in downgrade
    assert "DISABLE ROW LEVEL SECURITY" not in downgrade
    assert downgrade.index("op.drop_constraint") < downgrade.index(repair)
    assert downgrade.index(no_force) < downgrade.index(repair)
    assert downgrade.index(repair) < downgrade.index(legacy_check)
    assert downgrade.index(legacy_check) < downgrade.index(force)
    assert downgrade.index(force) < downgrade.index(drop_column)
