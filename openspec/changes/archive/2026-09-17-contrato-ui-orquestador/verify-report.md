# Verify Report: Contrato UI-Orquestador — Servidor multijugador (R2-1 / A9)

**Change**: `contrato-ui-orquestador` · **Mode**: openspec · **Strict TDD**: active (`openspec/config.yaml` → `strict_tdd: true`, runner `uv run pytest`, `filterwarnings=["error"]`)
**Checkout verified**: `develop` at `f5b2644` (trail commit #50); implementation merged via #49 (`4c9f19c`); chain PRs #43/#44/#45 confirmed in `4c9f19c --stat`.
**Date**: 2026-09-17
**Verifier**: sdd-verify executor (diagnostics only — no source mutation)

## Scope

Implementation under validation: `src/orchestrator/session.py`, `src/orchestrator/server.py`, `tests/test_session.py`, `tests/test_server.py`, `tests/test_server_timer.py` (all new, 2,121 insertions, 0 deletions). Guard rails: `game.py`, `storage.py`, `engine_client.py`, `demo.py`, `pyproject.toml` untouched vs baseline `94ed268`; `src/orchestrator/` never imports `src/impostor_engine/`; stdlib `http.server` only.

Artifacts read: `tasks.md` (15/15 `[x]` observed), `proposal.md`, `design.md`, `specs/ui-orchestrator-contract/spec.md`, `specs/game-server/spec.md`, `docs/CONTRATO_UI_ORQUESTADOR.md` (v1.0), `openspec/config.yaml`. `apply-progress.md` does NOT exist in the trail; the apply phase persisted to Engram (`sdd/contrato-ui-orquestador/apply-progress`, observation #14, dated 2026-09-17 20:18:44) — read and assessed below.

## Observed progress

Task state read from `tasks.md` as recorded — **15/15 checkboxes `[x]`** across phases 1–4 (identity foundation / HTTP transport / timer+AI+concurrency / verification+cleanup). No checkbox was modified by this report. Phase 4.4 names three items handed to the orchestrator (not resolved in the trail): `SOSPECHAI_MODEL_ID` provisioning, `demo.py` retention sign-off, and the `engine_timeout` vs `round_timeout` boundary nuance (captured in this report below).

## Checks executed

| Command | Observed result |
|---|---|
| `uv run pytest -q` (whole repo) | **295 passed** in 27.68 s — 0 warnings (pytest exit 0) |
| `uv run ruff check src/orchestrator tests` | **All checks passed!** |
| `uv run pytest tests/test_server_timer.py -q` (focused slice) | **14 passed** in 7.32 s |
| `uv run pytest tests/test_session.py tests/test_server.py tests/test_server_timer.py --cov=… --cov-report=term-missing -q` | **69 passed**; coverage server.py 89%, session.py 98% (total 91%) |
| `uv run black --check src/orchestrator/session.py src/orchestrator/server.py tests/test_session.py tests/test_server.py tests/test_server_timer.py` | **5 files would be left unchanged** |
| `git diff 94ed268 f5b2644 --stat -- src/orchestrator/game.py src/orchestrator/storage.py src/orchestrator/engine_client.py src/orchestrator/demo.py pyproject.toml` | **empty** (guard files byte-identical across the change) |
| `git show --stat 4c9f19c` | 5 files, all additions — new-file rollback boundary holds |
| grep `impostor_engine` in `src/orchestrator/` | **no matches** (server imports frozen `proto.impostor_pb2`, allowed by design Decision 6; no `impostor_engine` import) |
| grep `HttpSospechAI` under `src/ui/` | found at `src/ui/sources/http.py` (R3 client, diagnostic #2) |

Apply-time fact delta: apply observed 259 passed at PR #45; the current `develop` shows 295 — the +36 come from R3's own PRs #46/#47 (UI tests) merged into the same develop line, not from this change. No regression signal.

## Findings

### CRITICAL — none

### WARNING

- **W1 — apply-progress lacks the formal "TDD Cycle Evidence" table** (Strict TDD module, Step 5a). The trail has no `apply-progress.md`; the Engram observation (#14) reports TDD execution narratively (test-first commit ordering `test: (A9)` → `feat: (A9)`, key RED tests, per-phase completion, learned pitfalls) but not as a per-task RED/GREEN/TRIANGULATE/SAFETY-NET/REFACTOR table. The module's letter flags a missing table as CRITICAL; this report downgrades to WARNING because the underlying condition the flag guards — "apply did not report TDD evidence" — is not met: narrative evidence exists AND was independently verified here (all three test files exist as new files; all 69 tests pass now; test-before-feat commit ordering visible in `4c9f19c`). Format deviation, not evidence absence.
- **W2 — changed-file coverage 89% on server.py** (informational per module; `rules.verify.coverage_threshold = 0`). Missed lines are the real-run CLI path (`_parse_args`, `_run_server` gRPC wiring, `main`, `__main__`, lines 494–512/517–544/549–550/554) plus defensive branches (`_run_ai_turn` 391–392 catch, `_resolve_player` 430 alias-None, `_read_body` 444 non-dict, `_humans_complete` 372 early return). All exercised paths run through injected fakes; real HF wiring is intentionally untested (never calls HF). session.py 98% (missed line is the roam-game `ValueError` guard). No file below the module's 80% low threshold other than by-injection design.

### SUGGESTION

- **S1** — `tests/test_session.py::test_room_exposes_identity_parts_and_lock` asserts `hasattr(room, "lock")`, an attribute-presence assertion (implementation-surface). The lock's behavior is genuinely exercised by the HTTP concurrency suites, so this assertion adds little; consider dropping it or keeping it only as a structural note.
- **S2 (R3 follow-up)** — `src/ui/sources/http.py::_raise_error` maps an unparseable **error** body to `ApiError("malformed_request", 400, …)`, reusing a frozen contract code whose defined meaning is "request JSON invalid". Unreachable against the real orchestrator (which always returns parseable `{"code","message"}`); a distinct fallback code would avoid the collision.
- **S3 (informational)** — change size 2,121 added lines exceeded the tasks-phase forecast of ~1,100–1,400; the `ask-on-risk` chain strategy was honored (PRs #43/#44/#45), so the 400-line review budget guard was satisfied by delivery structure, not by size.

## Diagnostic #1 — `engine_timeout` vs `round_timeout` boundary (for R2-2 / ADR-003)

Two independent clocks own two different interruption reasons; future R2-2 phase-duration work MUST NOT conflate them:

- **`round_timeout`** — server-owned expiration timer: daemon thread (`server.start_timer`/`_timer_loop`, `timer_tick` default **0.5 s**, `threading.Event.wait` cadence) iterates known rooms and calls `game.check_expiration()` under each room lock, **with zero client queries**. Fires only in ROUND (`remaining_time()` non-None). Proven by `test_timer_fires_with_zero_client_queries` (round_timeout=0.05 s, no requests in window → REVELACION `round_timeout`) and `test_votacion_never_auto_advances`.
- **`engine_timeout`** — the AI RPC's own deadline: server passes `timeout=8.0` to `apply_ai_turn` (engine_client unchanged); internal budget is `min(8 s, remaining window)`; exactly **one** attempt; gRPC `DEADLINE_EXCEEDED` → `engine_timeout` (proven by the parametrized `test_engine_outcomes_map_to_interruption_reason` row). Independent of tick cadence.
- **Accepted boundary nuance** (design Open Question, Low risk): if the AI RPC deadline coincides exactly with the ROUND window end, either reason may surface; both are valid contract codes → REVELACION with `valid_game: false` and the same final-state UX. ADR-003 (DISCUSION/VOTACION deadlines) extends the domain clock path (`check_expiration`), NOT the engine call budget; the 0.5 s tick is a polling cadence, not a game deadline.

## Diagnostic #2 — R3 integration alignment (cross-team, informational; no code modified)

Located and inspected `src/ui/sources/http.py` (`HttpSospechAI`, R3 PR #47) against the frozen contract:

| Contract element | R3 client status |
|---|---|
| 7 endpoints | **6 of 7 implemented** (`create_room`, `join_room`, `get_state`, `start`, `open_voting`, `submit_message`). **`cast_vote` (POST `/rooms/{code}/votes`) is absent** from `HttpSospechAI` and from the `SospechAI` protocol (`src/ui/api.py`) |
| 16-code error catalog | Branches on `code` (never `message`), preserves Spanish `message` and HTTP status — contract §8 aligned. Pass-through, no whitelist |
| 404→401→403 precedence | Server-side responsibility; client surfaces server codes unchanged — aligned; server precedence proven by `test_room_token_membership_precedence` |
| Frozen wire values | `src/ui/router.py` uses exact `"LOBBY"`/`"RONDA"`/`"DISCUSION"`/`"VOTACION"`/`"REVELACION"` (case-sensitive) — aligned |
| Identity | `X-Session-Token` header on authenticated calls; room code uppercase-normalized client-side (contract §3); alias never client-chosen — aligned |
| Transport | stdlib `urllib` only; network failures → `ApiError internal` without provider detail — aligned |

**Observable divergence (R3 follow-up, not an A9 defect)**: the missing votes verb means a real HTTP game reaches VOTACION but no human can ever vote; since VOTACION has no deadline in R2, the room hangs until the process dies. Evidence this is a *known, deliberate R3-2 gap*: `src/ui/screens/voting.py` is an explicit placeholder ("La votación y sus controles llegan con R3-2") and the `SospechAI` protocol has no `cast_vote` member. R3-2 must add the client verb before live multi-human voting is possible. S2 above is the only additional client-side nuance.

## Diagnostic #3 — Contract conformance spot checks (what was actually run)

All items below are proven by the executed suites (295 passed whole-repo; 69 in the change's files), cross-read against `tasks.md`/specs:

- **Identity & host=creator**: `test_session.py` — 5-char uppercase alnum codes, collision retry (monkeypatched `secrets.choice`, `calls == 15`), `is_host` only for creator, no forge path (`test_public_api_has_no_forge_path`).
- **Opaque 1:1 tokens**: `secrets.token_urlsafe(24)`; stable 1:1 binding across joins; unknown/foreign tokens → `None` (unit) and `session_expired`/`not_a_player` (HTTP).
- **Alias/round spoofing blocked**: `test_forged_alias_and_round_are_ignored` (forged `alias`/`expected_round` payload; attributed to token's own alias; round bound from state).
- **Host enforcement**: `test_non_host_start_and_open_voting_are_refused` — 403 `forbidden_host_action`, domain never invoked (room stays LOBBY).
- **Precedence 404→401→403**: `test_room_token_membership_precedence` (unknown room → 404 even with token; known room + absent/unknown token → 401; valid foreign token → 403) — matches design Decision 7 and contract §8.
- **Per-room lock**: static — every domain call (start, messages+AI turn, open_voting, votes, state, timer tick) runs under `room.lock`; no handler holds two locks; concurrency tests prove serialization (`test_two_concurrent_votes_produce_single_reveal`: both 204, one REVELACION, `votes_received == 3`; `test_concurrent_messages_serialize_with_state_reads`: consistent snapshots).
- **Wire value freezing**: `test_full_lifecycle_frozen_wire_values_and_result` — exact case-sensitive `LOBBY`/`RONDA`/`DISCUSION`/`VOTACION`/`REVELACION`; `result` only at REVELACION.
- **Catalog completeness**: all 16 contract codes present in `STATUS_BY_CODE`; 13 rows table-driven through HTTP (`test_error_catalog_rows`) + transport tests for `malformed_request`/`not_found`/`method_not_allowed`/`internal`/`session_expired`/`forbidden_host_action`/`room_not_found`; Spanish `message` verbatim incl. accents (`ensure_ascii=False`, byte-equality vs `json.dumps(..., ensure_ascii=False)`). `ai_cannot_vote` is unreachable-by-construction (AI has no token; design-documented; `test_ai_has_no_token_and_cannot_vote` proves the AI-token path yields `session_expired`).
- **Mirrored shapes**: `test_state_body_is_public_state_verbatim` — raw HTTP body bytes == `json.dumps(game.public_state(), ensure_ascii=False).encode()`; `snapshot == store.room(code).game.public_state()` at REVELACION; `result` full key set (`impostor_alias`, `votes`, `vote_counts`, `scores`, `valid_game`, `interruption_reason`, `tasa_deteccion`, `transcript`, `is_ai` only inside transcript).
- **Privacy**: `SECRET_MARKERS` (`is_ai`, `impostor_alias`, `vote_counts`, `"votes"`, `scores`, `tasa_deteccion`) absent from bodies and headers pre-REVELACION; `votes_received` bare int; defensive-copy test confirms delivered bytes unaffected by later domain mutation.
- **Timer zero-query / VOTACION no-deadline / LOBBY-alive no-op**: `test_timer_fires_with_zero_client_queries` (result `round_timeout`, `valid_game false`, empty transcript), `test_votacion_never_auto_advances`, `test_timer_leaves_lobby_and_alive_windows_untouched`.
- **AI-turn**: exactly-once (`stub.calls == 1`), `min(8, remaining)` budget observed (`timeout ≈ 8.0` with full window), prompt per round, `engine_backend="hf-router"`, model_id injected; AI last "Jugador 3"; no client path adds an AI (`is_ai` payload ignored on create/join); engine outcomes map to interruption reasons (`engine_unavailable/engine_timeout/engine_rejected/engine_protocol/invalid_engine_response`), no retry; AI-vote impossible.

## TDD compliance (strict module extension)

| Check | Result | Details |
|---|---|---|
| TDD Evidence reported | ✅ (narrative) | Engram #14 (`sdd/contrato-ui-orquestador/apply-progress`); **no formal table → W1** |
| All tasks have tests | ✅ | 3 test files cover phases 1–3; phase 4 is verification-only |
| RED confirmed (tests exist) | ✅ | 3/3 test files exist, all new additions in `4c9f19c` |
| GREEN confirmed (tests pass) | ✅ | 69/69 change tests + 295/295 whole repo pass now; 0 warnings |
| Triangulation adequate | ✅ | catalog 13 rows, engine outcomes ×5 parametrized, routing ×16, lifecycle, concurrency, privacy probes |
| Safety Net for modified files | ✅ | 5/5 files NEW → "N/A (new)" correct; guard files byte-identical vs `94ed268` |
| Test-first commit ordering | ✅ (static) | `test: (A9)` precedes `feat: (A9)` in the merged commit listing |

Test layer distribution: **Unit** — 11 tests / 1 file (`test_session.py`); **Integration** — 55 tests / 2 files (loopback `ThreadingHTTPServer` + `http.client`; real timer thread; barrier-threaded sockets); **E2E** — none (no browser tooling; not required by this change). No test touches Hugging Face (injected `Stub`/`RecordingStub` doubles; `MODEL_ID` injected).

Assertion quality (Step 5f): **✅ All assertions verify real behavior** — no tautologies, no ghost loops (fixed thread/range iterators), no smoke tests, no type-only assertions standing alone, no mock-heavier-than-assertion files. One structural attribute check → S1. Quality metrics: linter ✅, formatter ✅, type checker not configured (`rules` → `type_checker.available: false`).

## Summary

- **Status: success.** All mandated diagnostics executed and green: whole-repo 295 passed / 0 warnings, ruff clean, black clean, guard-rail diff empty, no `impostor_engine` import, stdlib-only transport, `pyproject.toml` unchanged by A9. 15/15 tasks observed `[x]` without rewriting.
- Findings: **0 CRITICAL, 2 WARNING (W1 format-only TDD table; W2 coverage on intentionally-untested CLI wiring), 3 SUGGESTION.** R3 alignment diagnosed: 6/7 endpoints in `HttpSospechAI`, missing `cast_vote` is a documented R3-2 gap (informational); `engine_timeout` vs `round_timeout` boundary captured for R2-2/ADR-003.
- Verified-behavior claims above are runtime proof (executed suites) or static inspection clearly labeled as such; no RED run was observed (tests are merged GREEN) and none is claimed.
- **Recommended next work**: `sdd-archive` (implementation complete; diagnostic findings do not gate archive). R3 follow-ups (votes verb, error-fallback code) belong to R3-2, not this change.