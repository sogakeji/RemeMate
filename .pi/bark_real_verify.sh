#!/bin/bash
set -euo pipefail

: "${TEST_DISPATCH_DATABASE_PASSWORD:?Set TEST_DISPATCH_DATABASE_PASSWORD}"

ssh tencent-new 'bash -s' -- "$TEST_DISPATCH_DATABASE_PASSWORD" <<'REMOTE'
set -euo pipefail
export PGPASSWORD="$1"
echo "=== SCHEMA / EXISTING DATA ==="
psql -h 127.0.0.1 -p 55432 -U rememate_dispatch -d rememate_test -v ON_ERROR_STOP=1 <<'SQL'
SELECT rolname, rolbypassrls FROM pg_roles WHERE rolname='rememate_dispatch';
SELECT table_name, column_name, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema='public'
  AND table_name IN ('users','user_settings','word_lists','words','definitions','push_log')
ORDER BY table_name, ordinal_position;
SELECT id, email, is_active, timezone FROM users;
SELECT user_id, left(bark_url, 40) AS bark_url_prefix, notify_review_reminder FROM user_settings;
SELECT count(*) AS push_log_n FROM push_log;
SQL
REMOTE
