# bark dispatch runner — tencent-new test report

- local HEAD: `f1b2f82`
- branch: `feat/bark-scheduled-push`
- remote: `tencent-new:/home/ubuntu/rememate-test`
- date: 2026-08-20

## 1. Sync to tencent-new

```bash
cd /d/home/Rememate
tar cf - --exclude=.git --exclude=.venv --exclude=.reme --exclude=.pi --exclude='*.pyc' --exclude=__pycache__ --exclude=.env app/ cli/ tests/ config.py migrations/ dispatch/ docs/ | timeout 300 ssh tencent-new "cd /home/ubuntu/rememate-test && tar xf -"
```

- **exit code**: `0`
- output: (empty; tar pipe silent on success)

### 1b. Extra sync: `deploy/systemd/` (required for step 4; not in original sync set)

```bash
tar cf - ... deploy/systemd/ | timeout 120 ssh tencent-new "cd /home/ubuntu/rememate-test && tar xf -"
```

- **exit code**: `0`
- verified present: `test_dispatch_runner.py`, `test_dispatch_systemd_units.py`, `tests/integration/test_dispatch_runner.py`, `rememate-bark.timer`, `rememate-bark.service`

## 2. Migration check (`flask db current`)

### 2a. Exact command as given (MIGRATE only)

```bash
ssh tencent-new "cd /home/ubuntu/rememate-test && . .venv/bin/activate && export FLASK_ENV=development SECRET_KEY=x DATA_ENCRYPTION_KEY=\$(...) MIGRATE_DATABASE_URL='postgresql://rememate_owner:<redacted>@127.0.0.1:55432/rememate_test' && flask db current | tail -1"
```

- **flask exit**: `1` (masked to overall `0` by `| tail -1` without `pipefail`)
- **error**: `RuntimeError: Either 'SQLALCHEMY_DATABASE_URI' or 'SQLALCHEMY_BINDS' must be set.`
- **cause**: development config needs `DATABASE_URL` for app boot; `MIGRATE_DATABASE_URL` alone is not enough.

### 2b. Corrected (added `DATABASE_URL` = owner URL)

```bash
export DATABASE_URL='postgresql://rememate_owner:<redacted>@127.0.0.1:55432/rememate_test'
export MIGRATE_DATABASE_URL='postgresql://rememate_owner:<redacted>@127.0.0.1:55432/rememate_test'
# + FLASK_ENV / SECRET_KEY / DATA_ENCRYPTION_KEY
flask db current
```

```
c1d2e3f4a5b6 (head)
```

- **exit code**: `0`
- **result**: head still `c1d2e3f4a5b6`; no new migration; no owner upgrade needed.

## 3. New dispatch tests

```bash
ssh tencent-new "cd /home/ubuntu/rememate-test && . .venv/bin/activate && export TEST_DATABASE_URL='postgresql://rememate:<redacted>@127.0.0.1:55432/rememate_test' TEST_DISPATCH_DATABASE_URL='postgresql://rememate_dispatch:<redacted>@127.0.0.1:55432/rememate_test' && pytest tests/unit/test_dispatch_runner.py tests/unit/test_dispatch_systemd_units.py tests/integration/test_dispatch_runner.py -q --no-header -p no:cacheprovider"
```

```
....                                                                     [100%]
4 passed in 3.99s
```

- **exit code**: `0`
- **passed/failed**: `4 passed`, `0 failed`

## 4. systemd unit verify

```bash
ssh tencent-new "systemd-analyze verify /home/ubuntu/rememate-test/deploy/systemd/rememate-bark.timer /home/ubuntu/rememate-test/deploy/systemd/rememate-bark.service 2>&1 | head -20"
```

```
/etc/systemd/system/tat_agent.service:7: PIDFile= references a path below legacy directory /var/run/, updating /var/run/tat_agent.pid → /run/tat_agent.pid; please update the unit file accordingly.
```

- **exit code**: `0`
- **note**: only unrelated host `tat_agent.service` warning; bark timer/service verify clean.

## 5. Full regression (`tests/unit/` + `tests/integration/test_write.py`)

```bash
pytest tests/unit/ tests/integration/test_write.py -q --no-header -p no:cacheprovider
```

```
2 failed, 282 passed, 1 warning in 32.85s
```

- **exit code**: `1`

### Write-only recheck

```
36 passed in 22.81s
```

- **exit code**: `0` (matches baseline 36 passed)

### FAILED list

| Test | Error summary | Classification |
|------|---------------|----------------|
| `tests/unit/test_public_content.py::test_repo_placeholders_load` | `assert date(2026, 8, 17) == date(2026, 8, 14)` on zh post `why-word-lists-fail` | **既有基线失败** (`public_content`) |
| `tests/unit/test_public_content.py::test_qa_block_answer_renders_markdown` | `PublicContentError: missing .../zh/qa.yaml` (tmp fixture incomplete) | **既有基线失败** (`public_content` fixture) |

### Classification

| Bucket | Result |
|--------|--------|
| **新增失败** | **无** — dispatch 新测 4/4 通过；write 36/36 通过；unit 无新红 |
| **既有基线失败** | `test_public_content.py` ×2（与 handoff 一致） |
| handoff 另提但本次未复现 | `test_review_story_handoff.py::test_story_handoff_rejects_expired_ready_run`、`test_review_stories.py::test_orchestrate_failed_attempt_requires_explicit_single_retry` |

## Verdict

bark dispatch runner 在 tencent-new 上：**同步成功 · migration head=`c1d2e3f4a5b6` · 新测 4 passed · systemd verify OK · 全量仅基线 public_content 2 failed，无新增失败。**
