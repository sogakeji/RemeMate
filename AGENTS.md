# RemeMate Agent Guide

This file is the fastest safe entry point for future agents. Keep it short.

## Start Here

Read these files in order before changing code:

1. `docs/HANDOFF.md` - current branch state, deployment state, architecture rules, pitfalls.
2. `docs/BACKLOG.md` - deferred bugs, soft feedback, and accepted future work.
3. `docs/PROGRESS.md` - milestone history and where older context was archived.
4. Task-specific docs only when relevant, such as `docs/daily-task-card.md` or files under `docs/plans/`.

Do not read `docs/archive/HANDOFF.full-2026-07-08.md` by default. It is historical context for archaeology, not the working handoff.

## Current Recovery Gate

- The WSL2 virtual disk was lost on 2026-07-22. The recovered authoritative local repository is now
  `D:\home\RemeMate`.
- Production remains at `1b72128`; do not push the local recovery commits to production until PostgreSQL
  migrations and the full integration suite have run in a rebuilt test environment.
- Branch `recovery/replay-six-fixes` contains six local safety/data-trust fixes after production:
  output-entry word ownership RLS, dedicated NSFW moderation, recoverable reciprocal partner confirmation,
  normalized word idempotency and uniqueness, and Web/Bark review-grade idempotency.
- Local migration head is `e0f1a2b3c4d5`. The Windows recovery environment has no PostgreSQL, so database
  integration tests are restored but not yet executed.
- `origin` points directly at the production working repository. Never push as part of ordinary local recovery work.

## Closed Beta Rule

During closed beta, do not immediately implement every small request.

- Fix hard bugs now: crashes, data loss, auth/RLS/security problems, core workflow failures, deployment failures.
- Record soft bugs in `docs/BACKLOG.md`: wording, minor layout polish, low-risk UX preference, future product ideas.
- For new features, write or update a short plan first, then wait for scope agreement before coding.

## Before Work

- Run `git status --short --branch`.
- Stay on `master` for closed-beta hotfixes unless the user asks for a feature branch.
- Create a new branch before feature work or broad refactors.
- Never touch `.env`, `.venv`, production data, or `/srv/rememate-data` unless the user explicitly asks.
- Do not commit secrets or API keys.

## Testing Scale

Match tests to risk:

- Docs-only or tiny CSS copy: `git diff --check`; say that tests were not run.
- Single template or route: targeted integration tests.
- Service, RLS, database, AI, or quota logic: targeted tests plus `pytest -q`.
- Deployment: run `flask doctor --strict` on the target environment.

Do not run expensive full-test loops after every soft UI note. Batch work when possible.

## Production Pointers

- Server: `ubuntu@43.156.210.229`
- App path: `/srv/rememate`
- Service: `rememate.service`
- Dictionary data: `/srv/rememate-data/dictionaries`
- Production deploys must preserve existing users, database data, `.env`, `.venv`, and dictionary data.

## Avoid

- Do not merge old branches or branch from stale history without checking `docs/HANDOFF.md`.
- Do not re-enable the disabled online dictionary API unless explicitly scoped.
- Do not introduce heavy frontend frameworks for small UI changes.
- Do not broaden a hard-bug fix into a product redesign during closed beta.
