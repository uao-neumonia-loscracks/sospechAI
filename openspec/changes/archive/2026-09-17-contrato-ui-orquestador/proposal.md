# Proposal: Contrato UI-orquestador y servidor multijugador (R2-1 / ticket A9)

> Materialized from Engram observation #6 (`sdd/contrato-ui-orquestador/proposal`) when this
> change migrated from the engram store to the openspec trail mid-flight. Content preserved
> verbatim from the spec-phase source.

Source: exploration `sdd/contrato-ui-orquestador/explore` (R2-1 / A9). Baseline: single-process, in-memory game domain (`src/orchestrator/game.py`, 276 lines) plus console demo. NO server, NO UI, NO multiplayer contract exists. Deliberately NOT re-explored; the proposal builds directly on the prior gap analysis, approaches, and 8 open questions.

## Intent

**Problem**: The game today is single-process with a console demo — there is no server, no multiplayer contract, and no UI. The R3 UI role cannot start building because no stable interface exists between UI and orchestrator.

**Why now**: Multiplayer is the R2 milestone. The domain is already multiplayer-ready (auto-assigned aliases "Jugador N", per-round messages, voting with AI guard rails, injectable clock) and needs only a server wrapper; the UI role needs a stable document NOW so UI and server can be built independently against one source of truth.

**Intended outcome**: Publish `docs/CONTRATO_UI_ORQUESTADOR.md` FIRST — the contract that defines how several real players share one game through the orchestrator — and notify R3 BEFORE implementation starts. Contract freezes transport, identity model, endpoints, wire values, and error codes. Response bodies mirror `public_state()`/`result()` verbatim so the domain stays the single source of truth.

**Success**: R3 builds against the published contract without renegotiation; the server wrapper passes contract/session/timer tests under strict TDD with `game.py` UNCHANGED and zero new dependencies.

## Scope

### In Scope
- `docs/CONTRATO_UI_ORQUESTADOR.md` — the R2-1 deliverable: HTTP+JSON polling API contract; opaque session-token identity model; endpoint list (create room, join, start [host], submit message, open voting [host], cast vote, GET state snapshot); request/response shapes mirroring `public_state()`/`result()` verbatim (incl. `result` embedded only at REVELACION); frozen Spanish wire values (RONDA, DISCUSION, VOTACION, REVELACION); stable error-code catalog; room lifecycle + close event; reconnect policy; AI-turn timing; timer ownership and auto-advance semantics.
- Publish + notify R3 (UI role) — a gate BEFORE apply.
- Server wrapper (new `src/orchestrator/server.py`): stdlib `http.server` only, HTTP+JSON polling, no new dependencies.
- Session store (new `src/orchestrator/session.py`): opaque server-issued token per player, bound 1:1 to the server-assigned alias; alias never client-chosen.
- Single-writer serialization: lock around the Game instance for ALL mutations (domain stays lock-free).
- Timer-driven `check_expiration()`: server-owned timer calls it even with zero client queries; expiry auto-advances/auto-reveals per domain rules.
- Stable error-code catalog mapping every `RuleViolation` + transport failure to a machine-readable code (Spanish domain messages preserved).
- Tests under strict TDD: session binding (alias cannot be spoofed), serialized votes (last-human-vote reveal must NOT double-fire), timer behavior with no queries, endpoint ↔ domain mapping, frozen wire values.

### Out of Scope
- Active persistence / game recovery (ticket A8).
- Discussion/voting deadlines beyond ROUND (ADR-003 pending) — VOTACION keeps current wait-for-all-humans behavior.
- Transport upgrades beyond HTTP+JSON (WebSocket/gRPC documented as an additive upgrade path only).
- The UI client itself (R3's deliverable; `src/ui/` does not exist; UI talks ONLY to the orchestrator, never to the engine).
- Any new Python dependency (disk-full blocks `uv sync`; runtime deps stay grpcio, protobuf, python-dotenv).
- Changes to `src/orchestrator/game.py` — domain reused UNCHANGED.
- `src/orchestrator/storage.py` — unchanged (finished practice games only; active persistence is A8).

## Capabilities

Contract between proposal and spec phases — sdd-spec reads this to know which spec files to create.

### New Capabilities
- `ui-orchestrator-contract`: the published contract — transport + documented upgrade path, endpoint list, request/response shapes (mirroring `public_state()`/`result()` verbatim), session identity model, frozen Spanish wire values, error-code catalog, room lifecycle + close event, reconnect policy, AI-turn timing, timer ownership.
- `game-server`: the HTTP+JSON server wrapper — routing, session store, single-writer lock, timer-driven `check_expiration()`, AI-turn trigger, host-only action enforcement, error-code mapping.

### Modified Capabilities
- None. `game.py` domain behavior is spec-level unchanged; `engine_client.py` gains an invocation path (server loop) but no requirement change at spec level.

## Approach

**Contract-first HTTP+JSON polling** (exploration Approach 1 — recommended; zero new deps; browser-native; 1:1 mapping to domain methods; polling cheap for 20s windows).

1. Spec phase writes `docs/CONTRATO_UI_ORQUESTADOR.md`; contract published and R3 notified BEFORE apply.
2. Response bodies ARE `public_state()` / `result()` verbatim — the server never reshapes; domain is the single source of truth.
3. Identity: opaque session token per player, server-issued at join, bound to auto-generated alias "Jugador N"; alias is display-only and never client-chosen; room code groups players; host = room creator with host-only `start`/`open_voting`.
4. AI turn: server loop triggers `apply_ai_turn` (validate → budget = min(8s, remaining) → ONE RPC attempt → same validator); the AI never votes.
5. Timer: server owns a timer calling `check_expiration()` regardless of client activity; auto-reveal on expiry advertised through the state snapshot.
6. Errors: stable machine-readable catalog (codes frozen in the contract); domain Spanish messages preserved underneath.
7. AI joins last (lobby lists all aliases incl. AI); ordering policy documented to mitigate impostor-hint.

## Open Questions (from exploration) — Resolution Status

| # | Question | Status in this proposal |
|---|----------|--------------------------|
| 1 | Transport: HTTP+JSON polling vs WS push vs gRPC | **RESOLVED (recommendation)**: HTTP+JSON polling; WS/gRPC documented as additive upgrade path. **Decision needed from UI role**: confirm polling fits R3's refresh model. |
| 2 | Identity: opaque token, room code, display names?, host = creator?, host-only start/open_voting? | **RESOLVED**: opaque server token per player bound to server-assigned alias; room code; host = room creator; host-only start/open_voting; alias never client-chosen. **Decision needed from UI role**: allow client-chosen display name overlay? (storage implications). |
| 3 | AI player: who adds AI, when is AI turn triggered, alias hints impostor | **RESOLVED**: AI added by server at room setup (domain `add_player(is_ai=` is server-side); AI turn triggered by server loop at 8s budget within 20s window. **Decision needed from UI role**: lobby display of AI slot (separate slot vs anonymous) given "Jugador N" order hint. |
| 4 | Reconnect: token expiry; rejoin mid-round; disconnect behavior | **RESOLVED (proposal)**: token valid for room lifetime; rejoin mid-round re-reads state; human disconnect → current behavior (round continues; window expiry → auto-advance via `check_expiration()`). **Decision needed from UI role**: mark-and-continue would be a DOMAIN change — deferred unless R3 requires it. |
| 5 | Error codes: stable catalog | **RESOLVED**: catalog seeds — room_not_found, not_a_player, wrong_state, duplicate_message, empty_message, too_many_words, duplicate_vote, self_vote, ai_cannot_vote, session_expired, forbidden_host_action + transport-level codes (malformed_request, method_not_allowed, not_found, internal); all `RuleViolation` messages mapped. |
| 6 | Room lifecycle: cleanup, max size, close event | **RESOLVED (proposal)**: room created on join, terminal after REVELACION; close event surfaced in the state snapshot ("R2 aportará el evento de cierre"); max size = game rules (>=2 humans + 1 AI to start). **Decision needed from UI role**: close-event surfacing (final-state fetch vs explicit event flag). |
| 7 | Voting window: wait-for-all vs deadline | **RESOLVED (proposal)**: VOTACION waits for all humans (domain behavior unchanged; last human vote auto-reveals). Deadline DEFERRED to ADR-003. **Decision needed from UI role**: acceptable UX with no voting countdown. |
| 8 | Timer ownership: who drives `check_expiration()` | **RESOLVED**: server-own timer; MUST call `check_expiration()` with zero client queries; auto-reveal advertised via state snapshot. No UI decision needed. |

Status: 8/8 addressed — 4 fully resolved, 4 resolved-with-recommendation pending UI sign-off. Spec MUST NOT silently choose pending items; they are returned to the orchestrator/UI role.

## Delivery / Flow

1. **sdd-spec** (this change): requirements + scenarios for `ui-orchestrator-contract` and `game-server` capabilities, turning the open-question resolutions into requirements.
2. **Publish gate**: `docs/CONTRATO_UI_ORQUESTADOR.md` written and R3 notified BEFORE apply starts.
3. **apply**: server wrapper + sessions + lock + timer + error mapping, strict TDD (red-green-refactor).
4. Branch `feature/a9-contrato-ui-orquestador` from `develop`; commits `feat:` / `test:` / `fix:` / `chore:` prefixed with ticket A9; delivery strategy **single-pr** (400-line review policy; sdd-tasks must forecast budget, doc + wrapper counted as authored text).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `docs/CONTRATO_UI_ORQUESTADOR.md` | New | R2-1 deliverable: the UI-orchestrator contract |
| `src/orchestrator/server.py` | New | HTTP+JSON wrapper (stdlib `http.server`; no new deps) |
| `src/orchestrator/session.py` | New | Session-token store bound 1:1 to aliases |
| `src/orchestrator/engine_client.py` | Modified | AI turn now triggered from the server loop (validate → budget → one RPC; unchanged internals) |
| `src/orchestrator/demo.py` | Modified | Console reference flow superseded by the server (removal/retention decided at apply) |
| `src/orchestrator/game.py` | Unchanged | Domain reused UNCHANGED |
| `src/orchestrator/storage.py` | Unchanged | Active persistence deferred to A8 |
| `tests/` | New | Contract, session, serialization, timer, wire-value tests (strict TDD) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Disk 99-100% (~134 MiB free): ENOSPC blocks `uv sync`/installs at apply | High (until disk freed) | Stdlib-only server; zero new deps; re-verify `uv run pytest` once disk freed |
| Spanish wire values (RONDA, DISCUSION, VOTACION, REVELACION) drift from English enum names | Med | Contract freezes VALUE strings; spec locks them; tests assert exact values |
| AI alias "Jugador N" insertion-order hints impostor | Med | Contract documents policy; optional shuffle; UI sign-off on lobby display |
| Vote race: last-human-vote reveal can double-fire (domain lock-free) | Med | Single-writer lock in wrapper; strict TDD regression (two concurrent votes) |
| Pending UI decisions (transport fit, display names, lobby AI display, close-event) stall R3 | Med | Proposal resolves all 8 with explicit pending items; notification gate before apply |
| Single-PR 400-line budget (contract doc + wrapper) | Med | sdd-tasks forecasts budget; commits as reviewable work units; dense doc authoring |

## Rollback Plan

- **Contract doc**: revert the `docs/CONTRATO_UI_ORQUESTADOR.md` commit(s); R3 notified of the change alongside the revert; no code impact. Contract published + R3 notified BEFORE apply, so a contract design error is caught before server code exists.
- **Server wrapper**: delete new modules (`server.py`, `session.py`) and their tests — `game.py` unchanged, `storage.py` untouched, no schema/migrations, so rollback is a clean file removal.
- No data migrations, no schema changes, no dependency changes at any point — full revert is low-risk.

## Dependencies

- UI role (R3) sign-off on the 4 pending open-question items (notification gate before apply).
- No new Python dependencies (grpcio, protobuf, python-dotenv only).
- Disk space for `uv run pytest` at apply (re-verify once freed).
- ADR-003 outcome for any future deadline changes (VOTACION window deferred).

## Success Criteria

- [ ] `docs/CONTRATO_UI_ORQUESTADOR.md` written by spec phase, merged on `feature/a9-contrato-ui-orquestador` (from `develop`), R3 notified BEFORE implementation.
- [ ] Contract freezes Spanish wire values + error-code catalog; spec adopts them verbatim.
- [ ] Server wrapper passes contract tests: alias spoofing impossible; single-writer serialization (no double-fire reveal); timer-driven `check_expiration()` fires with zero client queries.
- [ ] `game.py` UNCHANGED; `storage.py` UNCHANGED; no new dependencies.
- [ ] All 8 open questions resolved or explicitly assigned to UI role for sign-off (held in this proposal for the spec phase).