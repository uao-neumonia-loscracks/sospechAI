# Archive Report: Contrato UI-Orquestador — Servidor multijugador (R2-1 / A9)

**Change**: `contrato-ui-orquestador` · **Store**: openspec (trail) + Engram mirror (obs #20)
**Archived on**: 2026-09-17 (repo date) → `openspec/changes/archive/2026-09-17-contrato-ui-orquestador/`
**Archiver**: sdd-archive executor · **Checkout at close**: `develop` @ `f5b2644`

> This report is the terminal record of the cycle and describes the state of the change AT CLOSE.
> Where `verify-report` (2026-09-17) or `apply-progress` (Engram #14) are intermediate snapshots,
> the final-state facts in the orchestrator's close handoff outrank them; any snapshot claim that
> conflicts is superseded here.

## Final State at Close

- **Delivery complete**: chained PRs #43/#44/#45 merged 2026-09-18; tracker `feature/r2-1-server-multijugador` accumulated full R2-1 (merge `54416dd`); tracker → `develop` merged via PR #49 (squash `4c9f19c`, "feat(r2): servidor multijugador UI-orquestador (R2-1/A9)"); the OpenSpec trail was committed via PR #50 (squash `f5b2644`). Proposal/design/tasks/specs are in git history on `develop`.
- **Branches**: chain branches deleted (remote + local); local checked out on `develop`.
- **Tests** (whole repo, `develop`): `uv run pytest -q` → **295 passed, 0 warnings** (259 contributed by this change + 36 from R3's merged UI tests #46/#47). `uv run ruff check` and `uv run black --check` clean.
- **Guard rails**: `game.py`, `storage.py`, `engine_client.py`, `demo.py`, `pyproject.toml` byte-identical vs baseline `94ed268`; stdlib-only server (zero new dependencies); no `impostor_engine` import in `src/orchestrator/`.
- **Verify outcome**: **0 CRITICAL, 0 BLOCKER**. Informational findings carried forward:
  - **W1** — apply-progress exists in Engram narrative form (obs #14; no formal per-task TDD table). Closed empirically: 3 test files exist, 69/69 change tests + 295/295 whole repo pass, `test:`-before-`feat:` commit ordering visible in `4c9f19c`. Format deviation, not evidence absence.
  - **W2** — changed-file coverage `server.py` 89% / `session.py` 98% (`rules.verify.coverage_threshold = 0`). Missed lines are the real-run CLI wiring and defensive branches, untested by design (tests never call Hugging Face).
  - **S1** — `test_session.py::test_room_exposes_identity_parts_and_lock` uses an attribute-presence assertion (implementation-surface; lock behavior proven by HTTP concurrency suites).
  - **S2 (R3 follow-up)** — `src/ui/sources/http.py::_raise_error` reuses code `malformed_request` for an unparseable error body; distinct fallback code would avoid the collision. Unreachable against the real orchestrator.
  - **S3 (informational)** — actual change size 2,121 added lines exceeded the tasks forecast (~1,100–1,400); the `ask-on-risk` chain strategy (PRs #43/#44/#45) satisfied the 400-line review guard by delivery structure.
- **R3 alignment note**: `HttpSospechAI` (`src/ui/sources/http.py`, R3 PR #47) implements **6 of 7** contract endpoints; the missing `cast_vote` verb belongs to **R3-2**, NOT this change (documented placeholder in `src/ui/screens/voting.py`; `SospechAI` protocol has no `cast_vote` member).

## Specs Synced (delta → main)

Both delta specs are full specs (no existing main spec; `openspec/specs/` was empty). Each was promoted mechanically (`cp` → `diff -r` → `mv`, verbatim bytes, empty readback diff):

| Domain | Action | Main spec | Requirements |
|--------|--------|-----------|--------------|
| `game-server` | Created (full spec promoted) | `openspec/specs/game-server/spec.md` | 10 requirements, 19 scenarios |
| `ui-orchestrator-contract` | Created (full spec promoted) | `openspec/specs/ui-orchestrator-contract/spec.md` | 13 requirements, 21 scenarios |

No MODIFIED/REMOVED/RENAMED requirements existed; no native composition (`sdd-archive-compose`) was required. The publishable contract remains the frozen, already-merged `docs/CONTRATO_UI_ORQUESTADOR.md` v1.0 (PR #36) — unmodified.

## Archive Contents (observed presence)

| Artifact | Status |
|----------|--------|
| `proposal.md` | present |
| `specs/game-server/spec.md` | present |
| `specs/ui-orchestrator-contract/spec.md` | present |
| `design.md` | present |
| `tasks.md` | present — **15/15 tasks `[x]`**, 0 unfinished (recorded as observed; not modified) |
| `verify-report.md` | present (uncommitted in the trail; added by the verify phase) |
| `apply-progress.md` | **missing from the trail** — apply phase persisted to Engram `sdd/contrato-ui-orquestador/apply-progress` (obs #14); not reconstructed here |
| `archive-report.md` | this file (additive-only) |

## Task Completion (per persisted `tasks.md`)

- 15/15 checkboxes observed `[x]` across Phases 1–4 (identity foundation / HTTP transport / timer+AI+concurrency / verification+cleanup). No checkbox was rewritten during archive.
- Phase 4.4 handed three items to the orchestrator (not resolved in the trail): `SOSPECHAI_MODEL_ID` provisioning, `demo.py` retention sign-off, `engine_timeout` vs `round_timeout` boundary nuance (now below).

## Open Items — Follow-ups (non-blocking; do NOT reopen this change)

1. **`SOSPECHAI_MODEL_ID` provisioning**: set the default `model_id` in `docker-compose.yml` for real runs (tests always inject it; no engine change).
2. **`demo.py` retention**: explicit sign-off that the console harness stays as the R2 demo path alongside the server (or a follow-up ticket to retire it).
3. **Confirm 3 contract §14 UI defaults with R3** (adopted by the design per contract v1.0 defaults, not resolved): display-name overlay → none in R2; AI lobby display → anonymous identical rendering; room close event → final-state fetch (`state == "REVELACION"`).
4. **ADR-003 must extend the domain clock path** for RONDA/DISCUSION/VOTACION durations: the server-owned **0.5 s tick** drives `round_timeout` via `check_expiration()` (zero client queries, ROUND only), while **`engine_timeout`** is the AI RPC's own `min(8 s, remaining)` budget with exactly **one** attempt. Future phase-duration work MUST NOT conflate the two clocks (verify-report Diagnostic #1).
5. **R3-2**: add the `cast_vote` client verb (6/7 endpoints today) before live multi-human voting is possible (verify-report Diagnostic #2); optional error-fallback code per S2.

## Traceability — Observation IDs

Artifacts read from the openspec trail (paths above). Engram observations consulted/confirmed for this archive:

| Obs ID | Topic | Role |
|--------|-------|------|
| #5 | `sdd/contrato-ui-orquestador/explore` | exploration source (cited in proposal) |
| #6 | `sdd/contrato-ui-orquestador/proposal` | materialization source of `proposal.md` |
| #8 | `sdd/contrato-ui-orquestador/spec` | materialization source of both delta specs |
| #9 | spec-level decisions (R2-1/A9) | provenance of the Spec-Level Decisions sections |
| #10 | R2-1 publish gate, PR #36 | contract publication evidence |
| #11 | `sdd/contrato-ui-orquestador/design` | mirror of `design.md` |
| #12 | `sdd/contrato-ui-orquestador/tasks` | mirror of `tasks.md` |
| #14 | `sdd/contrato-ui-orquestador/apply-progress` | apply progress — narrative TDD evidence (not in trail) |
| #16 | R2-1 delivered to develop (PRs #44/#45 + tracker #49) | delivery evidence |
| #19 | `sdd/contrato-ui-orquestador/verify-report` | Engram mirror of `verify-report.md` |

New observation persisted by this phase: `sdd/contrato-ui-orquestador/archive-report` (this report).

## Source of Truth Updated

- `openspec/specs/game-server/spec.md`
- `openspec/specs/ui-orchestrator-contract/spec.md`

## SDD Cycle Complete

Implementation: **complete and merged** (PRs #43/#44/#45 → tracker → `develop` via #49; trail #50). Verification: **passed with 0 CRITICAL / 0 BLOCKER** (295 tests, 0 warnings; informational W1/W2 + S1–S3 + R3 follow-ups recorded). Unfinished tasks: **none observed** (15/15). Unresolved findings: none inside this change; all open items are explicitly non-blocking follow-ups and must NOT reopen A9.