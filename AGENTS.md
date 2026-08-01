# RemeMate Agent Guide
## Context Recovery

1. Start with `.reme/handoff.md`; it is the sole recovery entry point.
2. Compare its anchor with the current Git HEAD before trusting routed state.
3. Read `.reme/state.yaml` only when you need to locate checkpoint drift.
4. Follow `.reme/navigation.yaml` and `.reme/evidence.yaml` progressively; open only documents relevant to the task.
5. Do not preload `HANDOFF`, `BACKLOG`, `PROGRESS`, archives, or task-specific plans unless REME routes you there.

## Git And Safety Boundaries

- Run `git status --short --branch` before changing project files.
- Stay on `master` for closed-beta hotfixes unless the user requests another branch.
- Create a new branch before feature work or broad refactors.
- Never merge, deploy, push, rewrite history, or alter production without explicit user approval.
- Never stash, discard, overwrite, or absorb existing user changes without approval.
- Never touch `.env`, `.venv`, production data, or `/srv/rememate-data` unless explicitly requested.
- Production work must preserve users, databases, secrets, virtual environments, and dictionary data.
- Do not commit credentials, API keys, private exports, or sensitive logs.

## Closed-Beta Scope

- Fix hard bugs promptly: crashes, data loss, auth/RLS/security failures, core workflow failures, and deployment failures.
- Record soft bugs and low-risk UX requests instead of implementing each one immediately.
- For new features, create or update a short plan and wait for scope agreement before coding.
- Do not broaden a focused fix into a redesign or mix unrelated feature slices.

## Testing Scale

- Docs-only or tiny CSS/copy changes: run `git diff --check`; report that tests were not run.
- Single templates or routes: run targeted integration tests.
- Service, RLS, database, AI, quota, or migration logic: run targeted tests plus `pytest -q`.
- Deployment work: run `flask doctor --strict` in the target environment and verify service, HTTPS, logs, and data preservation.
- Match test cost to risk; batch low-risk UI checks rather than repeating the full suite.

## Architecture Guards

- Do not re-enable the disabled online dictionary API unless explicitly scoped.
- Do not introduce a heavy frontend framework for small UI work.
- Prefer the current routed architecture and task contract over historical documents or recovered artifacts.
