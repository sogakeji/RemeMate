#!/bin/bash
set -euo pipefail

: "${TEST_DISPATCH_DATABASE_PASSWORD:?Set TEST_DISPATCH_DATABASE_PASSWORD}"
: "${BARK_URL:?Set BARK_URL to the full Bark endpoint}"

ssh tencent-new 'bash -s' -- "$TEST_DISPATCH_DATABASE_PASSWORD" "$BARK_URL" <<'REMOTE'
set -euo pipefail
export PGPASSWORD="$1"
BARK_URL="$2"
PSQL=(psql -h 127.0.0.1 -p 55432 -U rememate_dispatch -d rememate_test -v ON_ERROR_STOP=1 -v bark_url="$BARK_URL")

echo "=== B1 INSERT DATA ==="
"${PSQL[@]}" <<'SQL'
BEGIN;
WITH u AS (
  INSERT INTO users(
    public_id, email, password_hash, display_name, role,
    is_active, password_setup_required, login_attempts, timezone, created_at
  ) VALUES (
    gen_random_uuid(), 'bark-real@t.com', 'x', 'Bark Real', 'user',
    true, false, 0, 'Asia/Shanghai', now()
  )
  RETURNING id
), s AS (
  INSERT INTO user_settings(
    user_id, bark_url, notify_review_reminder, notify_daily_summary,
    notify_intake_done, notify_partner_activity, feedback_language
  )
  SELECT id,
         :'bark_url',
         true, true, true, false, 'zh'
  FROM u
), wl AS (
  INSERT INTO word_lists(user_id, language_code, name, created_at)
  SELECT id, 'fr', '法语', now() FROM u
  RETURNING id
), w AS (
  INSERT INTO words(list_id, word, marked, due_date, interval, ease, reps, lapses)
  SELECT id, 'bonjour', false, now() - interval '1 day', 1, 2.5, 0, 0
  FROM wl
  RETURNING id
), d AS (
  INSERT INTO definitions(word_id, part_of_speech, meaning)
  SELECT id, '问候语', '你好' FROM w
)
SELECT u.id AS user_id, w.id AS word_id FROM u, w;
COMMIT;
SQL

echo "=== VERIFY INSERTED ROWS ==="
"${PSQL[@]}" <<'SQL'
SELECT u.id, u.email, u.is_active, u.timezone, s.bark_url, s.notify_review_reminder
FROM users u
JOIN user_settings s ON s.user_id = u.id
WHERE u.email = 'bark-real@t.com';
SELECT wl.id AS list_id, wl.language_code, wl.name, w.id AS word_id, w.word, w.marked, w.due_date, w.interval, w.ease, w.reps, w.lapses, d.part_of_speech, d.meaning
FROM users u
JOIN word_lists wl ON wl.user_id = u.id
JOIN words w ON w.list_id = wl.id
JOIN definitions d ON d.word_id = w.id
WHERE u.email = 'bark-real@t.com';
SQL

cd /home/ubuntu/rememate-test
# shellcheck disable=SC1091
. .venv/bin/activate
export DISPATCH_DATABASE_URL="postgresql://rememate_dispatch:${PGPASSWORD}@127.0.0.1:55432/rememate_test"
unset SECRET_KEY PUBLIC_BASE_URL
echo "SECRET_KEY set? ${SECRET_KEY+yes}${SECRET_KEY-no}"
echo "PUBLIC_BASE_URL set? ${PUBLIC_BASE_URL+yes}${PUBLIC_BASE_URL-no}"

echo "=== B2 RUN 1 (live send) ==="
set +e
python -m dispatch.runner bark
RUN1_EXIT=$?
set -e
echo "RUN1_EXIT=${RUN1_EXIT}"

echo "=== PUSH_LOG AFTER RUN 1 ==="
"${PSQL[@]}" <<'SQL'
SELECT pl.id, pl.user_id, pl.idempotency_key, pl.push_type, pl.created_at
FROM push_log pl
JOIN users u ON u.id = pl.user_id
WHERE u.email = 'bark-real@t.com'
ORDER BY pl.id;
SQL

echo "=== B2 RUN 2 (idempotent) ==="
set +e
python -m dispatch.runner bark
RUN2_EXIT=$?
set -e
echo "RUN2_EXIT=${RUN2_EXIT}"

echo "=== PUSH_LOG AFTER RUN 2 ==="
"${PSQL[@]}" <<'SQL'
SELECT pl.id, pl.user_id, pl.idempotency_key, pl.push_type, pl.created_at
FROM push_log pl
JOIN users u ON u.id = pl.user_id
WHERE u.email = 'bark-real@t.com'
ORDER BY pl.id;
SELECT count(*) AS push_log_n FROM push_log;
SQL

echo "=== BARK HOST REACHABILITY (no device token, no extra push) ==="
set +e
HTTP_CODE=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 https://api.day.app/)
CURL_EXIT=$?
set -e
echo "curl https://api.day.app/ http_code=${HTTP_CODE} curl_exit=${CURL_EXIT}"
REMOTE
