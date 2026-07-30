# RemeMate Agent Guide

This file is the fastest safe entry point for future agents. Keep it short.

## Start Here

Read these files in order before changing code:

1. `docs/HANDOFF.md` - current branch state, deployment state, architecture rules, pitfalls.
2. `docs/BACKLOG.md` - deferred bugs, soft feedback, and accepted future work.
3. `docs/PROGRESS.md` - milestone history and where older context was archived.
4. Task-specific docs only when relevant, such as `docs/daily-task-card.md` or files under `docs/plans/`.

Do not read `docs/archive/HANDOFF.full-2026-07-08.md` by default. It is historical context for archaeology, not the working handoff.

## Current Authority And Development State

- The WSL2 virtual disk was lost on 2026-07-22. The recovered authoritative local repository is now
  `D:\home\RemeMate`.
- Production was upgraded from `1b72128` on 2026-07-30. The six replayed safety/data-trust fixes and
  Review Story v1 are now deployed from local `master`.
- Review Story was merged by `a7fcf91`; the pre-deploy local documentation state was `ce79a74`.
- The active branch is `feature/sessionpad-context-candidates-v1`, based on deployed `master@1be9ddc`.
  Production remains at `1be9ddc` with migration head `f1a2b3c4d5e6`; this feature branch is not deployed.
- Review story progress:
  - RS1 data/RLS/daily-summary foundation: `222d7c0`, with PostgreSQL validation follow-ups `f0d90e8` and
    `c761902`.
  - RS2-A multilingual provider contract: `c07ff42`.
  - RS2-B transactional run state machine: `e6f926e`; GCP revalidation is green, including the corrected
    request-context concurrency path.
  - RS2-C provider orchestration, token accounting, and privacy-safe funnel events: `e800ef0`; GCP validation
    passed 52 targeted tests, both concurrency paths 5/5, and the 607-test full suite.
  - RS3 review receipt and explicit writing handoff: `4937253` and `132fca2`; GCP browser, RLS, idempotency,
    and full-suite validation passed.
  - RS4 retention cleanup and operations closeout: `bf1ee9b`; dry-run is the default, `--apply` is explicit,
    two-user dispatch/BYPASSRLS cleanup passed, and the final full suite is **620 passed, 16 warnings**.
  - Post-branch review fix: `4825336` keeps Review Story writing handoff language request-scoped instead of
    mutating `current_language` or `learning_languages`; GCP passed 63 targeted tests and the final
    **621-test** full suite. The review's summary-query and global-cleanup observations are deferred
    scalability notes, not merge-blocking correctness bugs.
  - Review Story v1 is merged and deployed to closed beta. Real use then exposed a hard reachability bug: the
    receipt incorrectly required the entire due queue to be empty. `fix/review-story-partial-queue` removes that
    dependency. Eligibility is now at least 10 distinct words reviewed today; more than 5 distinct fuzzy-or-forgotten
    words changes the receipt to strong, but never bypasses the 10-word floor. GCP full suite: **621 passed**.
  - Hotfix `2f09304` is merged into local `master` and deployed to closed beta. Production strict doctor, service,
    public HTTPS, logs, and pre/post data counts passed; real-account partial-queue verification also passed.
    SessionPad context-bearing candidate v1 is now the next feature. Do not add story history, publishing, images,
    or a second editor.
- SessionPad context-candidate SP1 is committed as `d2ec131`; SP2 is committed as `d40e30a` and unifies
  AI/manual `term + context`, source-text anchoring, packet/recap creation, same-source normalized reuse, and
  database concurrency fallback. SP3 focused review is implemented in the current worktree: SessionPad alone
  uses a one-candidate queue with lightweight source metadata, editable provenance-bearing context, explicit
  context-to-example adoption, existing-word linking, AI degraded feedback, and no legacy/bulk endpoint bypass.
  GCP browser validation passed at 1440px and 390px dark mode; the final suite is **658 passed, 16 warnings**. SP3 is committed as `4c84f46`, but remains unmerged and undeployed.
- Feature-branch migration head is `b3c4d5e6f7a8`; production remains `f1a2b3c4d5e6`.
- **GCP Ubuntu recovery validation (2026-07-22) is done**: PostgreSQL 16 + tri-role `rememate_test`,
  migration head `e0f1a2b3c4d5`, Gate4 full suite **`486 passed`**, targeted six-fix set **122 passed**.
  One test-only SQL fix: `tests/integration/test_words.py` (`w.word, w.id`). No business code changes for
  that fix. `flask doctor --strict` on the test box: DB/migration/admin OK; LLM/dictionary WARN only.
  Full write-up: `docs/recovery-validation-2026-07-22.md`.
- `origin` points directly at the production working repository. Never push as part of ordinary local recovery work.

## Recovered Next-Stage Plan

- The completed Wayfinder map was recovered to
  `docs/wayfinder/2026-07-19-next-stage-roadmap/MAP.md`; recovery provenance is in the adjacent `RECOVERY.md`.
- The serial order remains review story, SessionPad context candidates, then the private closed-beta observation
  panel. Keep their migrations serial to avoid Alembic forks.
- Review Story RS1 through RS4 and the partial-queue hard fix are merged and deployed.
- SessionPad context-candidate SP1, SP2, and SP3 are committed on
  `feature/sessionpad-context-candidates-v1`; proceed next to SP4. Do not mix in the observation dashboard or
  unrelated closed-beta polish.
- Historical UI artifacts under the Wayfinder `artifacts/` directory are audit evidence, not production templates.

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
