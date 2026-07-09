# RemeMate Docs Map

This directory is intentionally split into a small active layer and a historical archive. New agents should use this map to avoid rereading outdated process notes as current instructions.

## Recommended Read Order

1. `HANDOFF.md`
2. `BACKLOG.md`
3. `PROGRESS.md`
4. Task-specific docs only when the current request names that area.

The root `AGENTS.md` contains the shortest operating protocol.

## Active Docs

| File | Purpose |
| --- | --- |
| `HANDOFF.md` | Current project state, branch/deploy status, architecture rules, and active pitfalls. Read first. |
| `BACKLOG.md` | Single source of truth for deferred bugs, soft feedback, and future product work. |
| `PROGRESS.md` | Milestone history and pointers to archived process records. |
| `daily-task-card.md` | Daily task card v1/v2 design and implementation notes. |
| `THIRD_PARTY.md` | Third-party data and dependency notes, especially dictionary provenance. |
| `strategy/2026-07-09-three-month-focus.md` | Three-month product direction anchor and prioritization filter. |

## Plans And Specs

Use these only when the task touches that subsystem.

| Path | When to read |
| --- | --- |
| `plans/2026-07-07-daily-task-card.md` | Daily task card v2 / bingo card planning. |
| `plans/2026-07-09-closed-beta-dual-track.md` | Closed-beta dual-track plan: daily loop hardening plus SessionPad validation. |
| `superpowers/plans/2026-07-03-lute-reading-mvp.md` | Reading collection implementation plan context. |
| `superpowers/specs/2026-07-03-lute-reading-mvp-design.md` | Reading collection design context. |
| `arch/` | Architecture notes, if present and relevant to the task. |

## Archive

| Path | Purpose |
| --- | --- |
| `archive/HANDOFF.full-2026-07-08.md` | Full pre-compaction handoff. Read only when you need historical detail that is missing from active docs. |

## How To Add Documentation

- Keep `HANDOFF.md` short and current.
- Put milestone summaries in `PROGRESS.md`.
- Put soft bugs and deferred product work in `BACKLOG.md`.
- Put scoped feature plans under `plans/YYYY-MM-DD-topic.md`.
- Move long superseded process notes to `archive/`.
- Prefer links and concise decisions over narrative logs.
