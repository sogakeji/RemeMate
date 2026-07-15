"""Unit coverage for the cleanup fixture's FK retry path."""

from sqlalchemy.exc import IntegrityError

from tests.conftest import _wipe


class _Result:
    def __init__(self, rows=()):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Connection:
    def __init__(self, phase, statements):
        self.phase = phase
        self.statements = statements

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append((self.phase, sql, params))
        if self.phase == "bulk" and sql == "DELETE FROM users":
            raise IntegrityError(sql, params, Exception("user_quota_user_id_fkey"))
        if self.phase == "fallback" and sql == "SELECT id FROM users":
            return _Result([(41,)])
        return _Result()


class _Transaction:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc, traceback):
        return False


class _Engine:
    def __init__(self):
        self.statements = []
        self.begin_calls = 0

    def begin(self):
        phase = "bulk" if self.begin_calls == 0 else "fallback"
        self.begin_calls += 1
        return _Transaction(_Connection(phase, self.statements))


def test_wipe_retries_per_user_after_bulk_fk_failure():
    engine = _Engine()

    _wipe(engine)

    assert engine.begin_calls == 2
    fallback_sql = [sql for phase, sql, _ in engine.statements if phase == "fallback"]
    assert "DELETE FROM user_quota" in fallback_sql
    assert "DELETE FROM users" in fallback_sql
    assert any("set_config('app.current_user_id'" in sql for sql in fallback_sql)
