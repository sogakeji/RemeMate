#!/usr/bin/env bash
set -u
: "${TEST_OWNER_DATABASE_PASSWORD:?Set TEST_OWNER_DATABASE_PASSWORD}"

ssh tencent-new 'bash -s' -- "$TEST_OWNER_DATABASE_PASSWORD" <<'REMOTE'
cd /home/ubuntu/rememate-test
. .venv/bin/activate
export FLASK_ENV=development SECRET_KEY=x
export DATABASE_URL="postgresql://rememate_owner:${1}@127.0.0.1:55432/rememate_test"
export MIGRATE_DATABASE_URL="$DATABASE_URL"
export DATA_ENCRYPTION_KEY="$(.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
echo "=== corrected command (DATABASE_URL and MIGRATE_DATABASE_URL) ==="
flask db current
echo EXIT:$?
REMOTE

echo "----"
# Run the MIGRATE_DATABASE_URL-only command for comparison.
ssh tencent-new 'bash -s' -- "$TEST_OWNER_DATABASE_PASSWORD" <<'REMOTE'
cd /home/ubuntu/rememate-test
. .venv/bin/activate
export FLASK_ENV=development SECRET_KEY=x
export DATA_ENCRYPTION_KEY="$(.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
export MIGRATE_DATABASE_URL="postgresql://rememate_owner:${1}@127.0.0.1:55432/rememate_test"
set -o pipefail
flask db current | tail -1
echo PIPE_EXIT:${PIPESTATUS[0]}/${PIPESTATUS[1]}/overall:$?
REMOTE
