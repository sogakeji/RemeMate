#!/usr/bin/env bash
set -u
: "${TEST_OWNER_DATABASE_PASSWORD:?Set TEST_OWNER_DATABASE_PASSWORD}"
: "${TEST_DATABASE_PASSWORD:?Set TEST_DATABASE_PASSWORD}"
: "${TEST_DISPATCH_DATABASE_PASSWORD:?Set TEST_DISPATCH_DATABASE_PASSWORD}"

ROOT="/d/home/Rememate"
REMOTE="tencent-new"
REMOTE_DIR="/home/ubuntu/rememate-test"
REPORT="$ROOT/.pi/tencent-dispatch-report.md"
mkdir -p "$ROOT/.pi"
: > "$REPORT"

section() {
  echo "" | tee -a "$REPORT"
  echo "## $1" | tee -a "$REPORT"
  echo "" | tee -a "$REPORT"
}

run_step() {
  local title="$1"
  local cmd="$2"
  section "$title"
  local safe_cmd="$cmd"
  safe_cmd="${safe_cmd//"$TEST_OWNER_DATABASE_PASSWORD"/<redacted>}"
  safe_cmd="${safe_cmd//"$TEST_DATABASE_PASSWORD"/<redacted>}"
  safe_cmd="${safe_cmd//"$TEST_DISPATCH_DATABASE_PASSWORD"/<redacted>}"
  echo '```bash' | tee -a "$REPORT"
  echo "$safe_cmd" | tee -a "$REPORT"
  echo '```' | tee -a "$REPORT"
  echo "" | tee -a "$REPORT"
  echo '```' | tee -a "$REPORT"
  set +e
  local out
  out=$(eval "$cmd" 2>&1)
  local ec=$?
  set -e
  out="${out//"$TEST_OWNER_DATABASE_PASSWORD"/<redacted>}"
  out="${out//"$TEST_DATABASE_PASSWORD"/<redacted>}"
  out="${out//"$TEST_DISPATCH_DATABASE_PASSWORD"/<redacted>}"
  printf '%s\n' "$out" | tee -a "$REPORT"
  echo "EXIT:$ec" | tee -a "$REPORT"
  echo '```' | tee -a "$REPORT"
  echo "" | tee -a "$REPORT"
  echo "- **exit code**: \`$ec\`" | tee -a "$REPORT"
  return 0
}

echo "# bark dispatch runner — tencent-new test report" | tee -a "$REPORT"
echo "" | tee -a "$REPORT"
echo "- local HEAD: \`$(cd "$ROOT" && git rev-parse --short HEAD)\`" | tee -a "$REPORT"
echo "- branch: \`$(cd "$ROOT" && git rev-parse --abbrev-ref HEAD)\`" | tee -a "$REPORT"
echo "- remote: \`$REMOTE:$REMOTE_DIR\`" | tee -a "$REPORT"
echo "- date: $(date -Iseconds)" | tee -a "$REPORT"

# Step 1: sync
STEP1="cd \"$ROOT\" && tar cf - --exclude=.git --exclude=.venv --exclude=.reme --exclude=.pi --exclude='*.pyc' --exclude=__pycache__ --exclude=.env app/ cli/ tests/ config.py migrations/ dispatch/ docs/ | timeout 300 ssh $REMOTE \"cd $REMOTE_DIR && tar xf -\""
run_step "1. Sync to tencent-new" "$STEP1"

# Also ensure deploy/systemd units are present for step 4 (not in original sync set, but needed)
STEP1B="cd \"$ROOT\" && tar cf - --exclude=.git --exclude=.venv --exclude=.reme --exclude=.pi --exclude='*.pyc' --exclude=__pycache__ --exclude=.env deploy/systemd/ | timeout 120 ssh $REMOTE \"cd $REMOTE_DIR && tar xf -\""
run_step "1b. Sync deploy/systemd (needed for unit verify)" "$STEP1B"

# Verify key files landed
STEP1C="ssh $REMOTE \"ls -la $REMOTE_DIR/tests/unit/test_dispatch_runner.py $REMOTE_DIR/tests/unit/test_dispatch_systemd_units.py $REMOTE_DIR/tests/integration/test_dispatch_runner.py $REMOTE_DIR/deploy/systemd/rememate-bark.timer $REMOTE_DIR/deploy/systemd/rememate-bark.service 2>&1\""
run_step "1c. Verify synced artifacts" "$STEP1C"

# Step 2: migration
STEP2="ssh $REMOTE \"cd $REMOTE_DIR && . .venv/bin/activate && export FLASK_ENV=development SECRET_KEY=x DATA_ENCRYPTION_KEY=\\\$(.venv/bin/python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())') MIGRATE_DATABASE_URL='postgresql://rememate_owner:${TEST_OWNER_DATABASE_PASSWORD}@127.0.0.1:55432/rememate_test' && flask db current | tail -1\""
run_step "2. Migration check (flask db current)" "$STEP2"

# Step 3: new tests
STEP3="ssh $REMOTE \"cd $REMOTE_DIR && . .venv/bin/activate && export TEST_DATABASE_URL='postgresql://rememate:${TEST_DATABASE_PASSWORD}@127.0.0.1:55432/rememate_test' TEST_DISPATCH_DATABASE_URL='postgresql://rememate_dispatch:${TEST_DISPATCH_DATABASE_PASSWORD}@127.0.0.1:55432/rememate_test' && pytest tests/unit/test_dispatch_runner.py tests/unit/test_dispatch_systemd_units.py tests/integration/test_dispatch_runner.py -q --no-header -p no:cacheprovider\""
run_step "3. New dispatch tests" "$STEP3"

# Step 4: systemd
STEP4="ssh $REMOTE \"systemd-analyze verify $REMOTE_DIR/deploy/systemd/rememate-bark.timer $REMOTE_DIR/deploy/systemd/rememate-bark.service 2>&1 | head -20\""
run_step "4. systemd unit verify" "$STEP4"

# Step 5: full regression
STEP5="ssh $REMOTE \"cd $REMOTE_DIR && . .venv/bin/activate && export TEST_DATABASE_URL='postgresql://rememate:${TEST_DATABASE_PASSWORD}@127.0.0.1:55432/rememate_test' TEST_DISPATCH_DATABASE_URL='postgresql://rememate_dispatch:${TEST_DISPATCH_DATABASE_PASSWORD}@127.0.0.1:55432/rememate_test' && pytest tests/unit/ tests/integration/test_write.py -q --no-header -p no:cacheprovider\""
run_step "5. Full regression (unit + test_write.py)" "$STEP5"

echo "" | tee -a "$REPORT"
echo "## Classification notes" | tee -a "$REPORT"
echo "" | tee -a "$REPORT"
echo "- Baseline known failures (handoff): \`test_public_content.py\` 2 (fixture missing zh/qa.yaml); also mentioned \`test_review_story_handoff.py::test_story_handoff_rejects_expired_ready_run\`, \`test_review_stories.py::test_orchestrate_failed_attempt_requires_explicit_single_retry\`." | tee -a "$REPORT"
echo "- Baseline write: 36 passed." | tee -a "$REPORT"
echo "- New failures = anything outside the baseline set above." | tee -a "$REPORT"
echo "" | tee -a "$REPORT"
echo "Report written to: $REPORT"
