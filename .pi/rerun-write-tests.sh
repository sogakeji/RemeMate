#!/usr/bin/env bash
set -u
: "${TEST_DATABASE_PASSWORD:?Set TEST_DATABASE_PASSWORD}"
: "${TEST_DISPATCH_DATABASE_PASSWORD:?Set TEST_DISPATCH_DATABASE_PASSWORD}"
ssh tencent-new 'bash -s' -- "$TEST_DATABASE_PASSWORD" "$TEST_DISPATCH_DATABASE_PASSWORD" <<'REMOTE'
cd /home/ubuntu/rememate-test
. .venv/bin/activate
export TEST_DATABASE_URL="postgresql://rememate:${1}@127.0.0.1:55432/rememate_test"
export TEST_DISPATCH_DATABASE_URL="postgresql://rememate_dispatch:${2}@127.0.0.1:55432/rememate_test"
pytest tests/integration/test_write.py -q --no-header -p no:cacheprovider
echo EXIT:$?
REMOTE
