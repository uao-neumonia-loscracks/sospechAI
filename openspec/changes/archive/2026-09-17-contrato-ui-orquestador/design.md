# Design: Contrato UI-Orquestador — Servidor multijugador (R2-1 / A9)

**Change**: `contrato-ui-orquestador`
**Specs**: capabilities `ui-orchestrator-contract` + `game-server` (see `openspec/changes/contrato-ui-orquestador/specs/`)
**Contract**: `docs/CONTRATO_UI_ORQUESTADOR.md` v1.0 — **already merged on `develop`** (PR #36) and notified to R3; the R2-1 publish gate is satisfied and needs no re-publication.
**Baseline**: `develop` tip `94ed268`; R3 UI skeleton merged (`src/ui/` — polling resolved at 1.0 s active / 2.5 s idle in `src/ui/router.py`).
**Soft constraint honored**: `game.py` and `storage.py` UNCHANGED; `engine_client.py` reused UNCHANGED; no new dependencies; stdlib-only server.

## Technical Approach

Wrap the existing lock-free domain (`src/orchestrator/game.py`) with a **contract-first HTTP+JSON polling server** built entirely on the Python standard library. Two new orchestrator modules:

- **`src/orchestrator/session.py`** — identity and room registry: opaque tokens bound 1:1 to server-assigned aliases, room codes, host binding, and the per-game single-writer lock.
- **`src/orchestrator/server.py`** — transport and orchestration: `ThreadingHTTPServer` handler, the seven contract endpoints, server-side identity binding, error-code mapping, the server-owned expiration timer, and the AI-turn trigger.

The AI turn reuses `src/orchestrator/engine_client.py` **as-is**: `apply_ai_turn(game, alias, client, request, *, timeout=8.0)` already implements contract §11 exactly — validate turn → budget `min(timeout, remaining)` → one RPC attempt → same `submit_message` validator → interruption codes on failure. No change is needed to `engine_client.py` (the proposal's provisional "Modified" entry is downgraded to "Unchanged/reused" — see Decision 5).

The publish gate status: the contract is merged and R3 (UI) was notified at PR #36; polling decision (pending item 1) is **resolved by R3** (`GAME_POLL_SECONDS = 1.0`, `IDLE_POLL_SECONDS = 2.5` in `src/ui/router.py`). The remaining three pending UI decisions are **adopted per the contract's defaults** (contract v1.0 §14.2 user name overlay → none; §14.3 AI lobby display → anonymous identical; §14.4 close event → final-state fetch) and carried into Open Questions as "to confirm with R3" — the design does **not** invent contract changes.

> Section numbering note: the runtime brief cited "§15 defaults", but in the merged v1.0 document the pending decisions live in **§14** (§15 is the version log). All references here follow the merged document (`docs/CONTRATO_UI_ORQUESTADOR.md`).

## Architecture Decisions

### Decision: Stdlib `http.server` + `ThreadingHTTPServer` as the only transport

**Choice**: `src/orchestrator/server.py` subclasses `http.server.ThreadingHTTPServer` with a `BaseHTTPRequestHandler`; JSON bodies; per-request threads; `daemon_threads = True`. Requests are short synchronous HTTP/1.1 exchanges — polling snapshots, no persistent connections.

**Alternatives considered**: gRPC orchestrator service (new proto) — rejected: browsers cannot speak gRPC natively (grpc-web/proxy needed) and the exploration already ruled it out; WebSocket push — rejected: new dependency (`websockets`/`aiohttp`) blocked by the disk-full `uv sync` constraint; FastAPI/uvicorn — rejected: new dependencies, violates the stdlib-only spec requirement.

**Rationale**: Spec requirement "Stdlib-only HTTP+JSON server" + AGENTS hard rules (zero new deps; runtime stays grpcio/protobuf/python-dotenv — streamlit was added by R3's own change and is not touched here). Polling is cheap for 20 s windows, and the contract freezes the transport for R2 with WS/gRPC documented as additive only.

### Decision: `session.py` owns identity + room registry; one opaque token ↔ one alias, host = creator

**Choice**: `SessionStore` in `src/orchestrator/session.py` keeps an in-memory registry: `room_code → Room` where `Room` holds the `Game`, the host token, `token → alias`, and the room's write lock. Tokens are `secrets.token_urlsafe(24)`; room codes are 5-char uppercase alphanumeric via `secrets.choice`, normalized to uppercase on input (case-insensitive join), collision-retried. Alias always comes from `add_player` insertion order ("Jugador N"); clients never send or override an alias or round.

**Alternatives considered**: client-chosen display names (rejected — contract §3 forbids; overlay with server storage deferred, R3 pending item 2); JWT/stateless signed tokens (rejected — no replay/expiry semantics needed, an in-memory map is simpler and opaque per contract); client-declared host role (rejected — host must be derived from the token, contract §3).

**Rationale**: Spec requirements "Session store binding" and "Host-only action enforcement"; the server must be able to prove alias binding (spoofing scenario). `secrets` gives cryptographically random opaque values without extra deps. No token expiry exists by contract (§3: valid for room lifetime).

### Decision: Per-room single-writer lock around **all** domain access (mutations, snapshots, timer, AI turn)

**Choice**: each `Room` owns one `threading.Lock`. Every handler acquires the room's lock around any `Game` call — mutations, `public_state()` serialization (so `GET /state` reads a consistent snapshot), the AI turn, and the timer's `check_expiration()`. No handler ever holds two room locks at once (no lock ordering problem; each request touches exactly one room). The domain stays lock-free, unchanged.

**Alternatives considered**: one global server-wide lock — rejected: unrelated rooms would block each other (an 8 s AI RPC in one room would stall every other room's polls); per-operation re-entrant queuing — rejected: the domain is not thread-safe and the "mixed concurrent mutations serialize" scenario demands serialization, not fine-grained locking; lock-free/CAS around votes — rejected: would require domain changes.

**Rationale**: Spec requirement "Single-writer serialization with no double-fire reveal". The last-human-vote reveal fires exactly once because two concurrent votes can never interleave inside `cast_vote`. Holding the lock during the AI RPC (≤ 8 s) is a deliberate trade-off: it blocks that room's polls during the AI turn, which is acceptable for a turn-based 20 s-window game and keeps the "AI turn then round advance" atomic; it also guarantees the timer can never interrupt mid-generation (see risks for the boundary case).

### Decision: Server-owned timer thread calling `check_expiration()` per room even with zero client queries

**Choice**: `GameServer.start_timer()` spawns a daemon thread looping `sleep(TIMER_TICK)` (0.5 s) → for each room, acquire its lock, call `game.check_expiration()`. A `threading.Event` supports clean stop for tests and shutdown. Only ROUND can expire (domain: `remaining_time()` is non-None only in ROUND), so VOTACION is untouched, matching the contract.

**Alternatives considered**: lazy expiration on the next poll — rejected: violates the spec scenario "Timer fires with no client queries"; a `sched`-based deadline scheduler — rejected: more moving parts, per-room deadlines invalidate on round advance anyway, and a periodic tick is simpler to test.

**Rationale**: Contract §12 + spec "Timer-driven check_expiration with zero queries". Tick 0.5 s is finer than the UI's 1.0 s active poll and coarse enough to be cheap. `public_state()` also calls `check_expiration()` internally (domain), so a poll after expiry returns REVELACION either way — the timer guarantees it happens with zero polls.

### Decision: AI turn triggered synchronously inside the last human's message request, via `apply_ai_turn` unchanged; `engine_client.py` NOT modified

**Choice**: after a successful `submit_message` in RONDA, the handler re-checks under the room lock whether all human players have a message for the current round; if so, it builds the `UtteranceRequest` (see Decision 6) and calls `apply_ai_turn(game, ai_alias, client, request, timeout=8.0)`. Exactly one AI turn per round, synchronous, under the lock.

**Alternatives considered**: AI turn in a background thread — rejected: complicates exactly-once ordering and races with the timer; AI turn driven by the timer — rejected: the contract ties the trigger to "all humans have submitted", which the request path detects naturally at the last human message; modifying `engine_client.py` to add a server-facing helper — rejected: `apply_ai_turn` already implements contract §11 verbatim (validate → budget `min(8, remaining)` → one attempt, no retries → same validator → interruption codes). The proposal's "engine_client.py Modified" entry was provisional; no spec requirement needs it, so the design downgrades it to **Unchanged/reused** — less diff, same behavior.

**Rationale**: Spec "AI-turn trigger in the server loop". The pre-check ("all humans submitted") makes the turn valid before calling `apply_ai_turn`, so its internal `validate_ai_turn` cannot fail in the normal path; a defensive catch maps any unexpected escape to `internal` (500) so an invariant break is loud in tests, never silent. The AI never votes: it has no token, no endpoint path, and the domain raises `ai_cannot_vote`.

### Decision: AI `UtteranceRequest` built locally in the server; prompts injected; model config from `ServerConfig`

**Choice**: `server.py` contains `DEFAULT_PROMPTS` (one prompt string per round, demo-style, like `demo.py`'s) and builds `pb.UtteranceRequest(room_id=room_code, persona_id="p1", prompt=prompts[round_number-1], config=pb.GenerationConfig(...))` with values from a small frozen `ServerConfig` dataclass (temperature, top_p, system_prompt_version, `engine_backend="hf-router"`, `model_id`). `model_id` comes from the `SOSPECHAI_MODEL_ID` env var by default and is overridable via the server constructor (required for fake-stub tests that never touch Hugging Face). `max_words` is taken from `game.max_words` (domain authority, required by `apply_ai_turn`'s check).

**Alternatives considered**: importing `src/impostor_engine/prompt_store.py` — **rejected, forbidden** by AGENTS ("`src/orchestrator/` NUNCA importa nada de `src/impostor_engine/`"); reading prompts from UI or clients — rejected (prompts are a server-orchestrator concern; clients never send prompts per contract).

**Rationale**: AGENTS neutral-zone/import rules + engine_client's validation (`engine_backend == "hf-router"`, non-empty `model_id`). The prompt source is injected (constructor/CLI), so tests pass explicit prompt lists and the real A13 prompt flow can replace `DEFAULT_PROMPTS` later without contract change. The server imports `proto.impostor_pb2` — the same frozen proto `engine_client.py` already imports; this is not an `impostor_engine` import.

### Decision: Error mapping by post-hoc rule disambiguation, never by message matching

**Choice**: handlers catch `RuleViolation` and classify the fired rule with a small **pure per-route predicate chain** that re-derives the condition from the current game state + the request payload (mirroring the domain's own check order), producing the contract code; the exception's Spanish message is preserved verbatim in the error body. Transport failures (malformed JSON, unknown path, wrong verb, unexpected exception) are handled by their own pre-checks.

**Alternatives considered**: regex/equality on the `RuleViolation` message string — rejected: brittle, breaks the moment a Spanish message is reworded; full pre-validation of every rule in the handler before calling the domain — rejected: duplicates and would drift from the domain's single source of truth; adding codes to domain exceptions — **rejected, forbidden**: `game.py` must not change.

**Rationale**: Spec "Error-code mapping" (clients branch on `code`, `message` stays Spanish verbatim). Example — for `submit_message`, the chain is `state != RONDA → wrong_state`, else normalized text empty → `empty_message`, else words > `max_words` → `too_many_words`, else → `duplicate_message`, mirroring the domain's raise order exactly. Each guarded operation has a bounded set of violations, so the chains are small, total, and table-testable over the full catalog.

### Decision: Session/room error precedence and token-membership semantics

**Choice**: resolution order inside authenticated handlers: (1) room lookup — unknown room → `room_not_found` (404); (2) token lookup — absent/unknown token → `session_expired` (401); (3) membership — token valid but bound to a *different* room than the path (or otherwise not a player of this room) → `not_a_player` (403). `start`/`open_voting` add (4) host check → `forbidden_host_action` (403) before any domain call.

**Alternatives considered**: validating the token before the room — rejected: on a nonexistent room there is no membership to evaluate, and join (`POST /rooms/{code}/join`, no token) must 404 before anything else; treating cross-room tokens as `session_expired` — rejected: catalog §8 defines `session_expired` as "ausente, desconocido o de sala reclamada" and `not_a_player` as "token válido pero no ligado a un jugador de la sala" — a valid foreign token is precisely the latter.

**Rationale**: Contract §8 catalog semantics + spec "Session store binding" scenarios. Deterministic, documented precedence keeps the error surface stable and testable.

### Decision: `demo.py` retained unchanged; JSON serialized with `ensure_ascii=False`; `Content-Type: application/json`

**Choice**: keep `src/orchestrator/demo.py` exactly as-is for the console practice flow (the proposal left removal/retention to apply; no spec requirement removes it, so removing it would be churn without a requirement). Responses serialize with `json.dumps(..., ensure_ascii=False)` so Spanish accents survive; every response carries `Content-Type: application/json` except 204 (empty body). Mutations return 204; create/join return 201 with (`room_code`, `session_token`, `alias`).

**Alternatives considered**: deleting demo.py (rejected — no requirement, it remains a useful offline harness and its tests... none exist; removal would shrink nothing meaningful); ASCII-escaped JSON (rejected — `ensure_ascii=False` matches domain behavior and the R3 fake's contract examples).

**Rationale**: Spec "Stdlib-only HTTP+JSON server" + contract §2/§6. Minimal diff surface on the merged baseline; rollback remains a clean file deletion.

## Data Flow

### Poll (read) cycle — the canonical R3 loop

```
R3 UI (1.0 s active / 2.5 s idle)          GameServer (ThreadingHTTPServer)
      │  GET /rooms/{code}/state                │
      │  X-Session-Token: <token>               │
      ├────────────────────────────────────────►│ resolve room (404?) → resolve token (401/403?)
      │                                         │ acquire room.lock
      │                                         │   game.public_state()   (domain calls check_expiration())
      │                                         │   json.dumps(snapshot)  → defensive copy (bytes)
      │                                         │ release room.lock
      │◄────────────────────────────────────────┤ 200 {"state":"RONDA", ..., "result": null}
```

### Create / join — identity issuance

```
POST /rooms            → Game(rounds, max_words, round_timeout, clock)  → add_player()          → alias "Jugador 1"
                          room_code = 5-char uppercase (secrets)        → host_token = token     → 201 {room_code, session_token, alias}
POST /rooms/{code}/join → room lookup → state==LOBBY? → add_player()    → token2, alias "Jugador 2" → 201 {session_token, alias}
                          (LOBBY check: domain raises → wrong_state 409; unknown room → room_not_found 404)
```

### Start — AI registration + domain start (atomic, under the lock)

```
host POST /rooms/{code}/start
  → host check (forbidden_host_action 403 if not host)
  → acquire room.lock
      game.add_player(is_ai=True)   # always last "Jugador N" (spec decision 2)
      game.start()                  # roster ≥2 humans + exactly 1 AI else RuleViolation → invalid_roster 409
  → release room.lock → 204
```

### Round message + AI turn (synchronous, in the human's request)

```
player POST /rooms/{code}/messages {"text": "..."}
  → alias = token→alias; expected_round = game.round_number (client fields ignored)
  → room.lock
      game.submit_message(alias, text, expected_round=...)
      if all humans have a message for the current round (re-check under lock):
          build pb.UtteranceRequest (prompt[round-1], game.max_words, ServerConfig)
          apply_ai_turn(game, ai_alias, client, request, timeout=8.0)
          # budget = min(8, remaining) inside; one RPC; failure → game.interrupt(code)
          # submit_message advances round or → DISCUSION
  → release room.lock → 204 (AI text lands before the response; next poll shows it)
```

### Vote — serialized reveal

```
player POST /rooms/{code}/votes {"suspect": "Jugador N"}
  → room.lock → game.cast_vote(voter_alias, suspect)   # last human vote → REVELACION exactly once
  → release room.lock → 204 (following poll returns REVELACION + result)
```

### Timer — zero-client expiry

```
TimerThread (daemon, tick 0.5 s) ── for each room: room.lock ──> game.check_expiration()
        │   ROUND expired?  remaining_time()==0 → game.interrupt("round_timeout") → REVELACION
        │   ROUND alive?            no-op
        │   VOTACION/other?         no-op (domain: remaining_time() None)
        └── next poll observes REVELACION + interruption_reason "round_timeout"
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/orchestrator/session.py` | Create | `SessionStore`, `Room` record (game, host_token, `token→alias`, per-room `Lock`), opaque token + room-code issuance `secrets`, host predicate, aliases from `add_player` only. |
| `src/orchestrator/server.py` | Create | `GameServer(ThreadingHTTPServer)` + `ApiHandler(BaseHTTPRequestHandler)`: 7-endpoint routing, server-side identity binding, JSON parsing, per-route RuleViolation disambiguation to catalog codes, per-room lock, timer thread, AI-turn trigger, `ServerConfig`, `DEFAULT_PROMPTS`, `main()` CLI (`--host/--port/--model-id/--rounds/--max-words/--round-timeout`). |
| `src/orchestrator/engine_client.py` | Unchanged | Reused as-is: `apply_ai_turn` implements contract §11 (budget, one attempt, interruption codes). Proposal's "Modified" entry downgraded (Decision 5). |
| `src/orchestrator/demo.py` | Unchanged | Retained as the console practice harness (Decision 9). |
| `src/orchestrator/game.py` | Unchanged | Hard constraint — domain lock-free and untouched. |
| `src/orchestrator/storage.py` | Unchanged | Not invoked by the server; active persistence is A8. |
| `tests/test_session.py` | Create | Identity issuance, spoofing, cross-room tokens, code generation. |
| `tests/test_server.py` | Create | Loopback HTTP: routing table (7 endpoints + fallbacks), error catalog table-driven, host enforcement, mirrored shapes, privacy probing, wire values. |
| `tests/test_server_timer.py` | Create | Timer zero-query expiry, VOTACION no-deadline, concurrent votes single reveal, mixed concurrency, AI-turn trigger + engine failure codes. |
| `docs/CONTRATO_UI_ORQUESTADOR.md` | Unchanged | Already merged at PR #36; publish gate satisfied. |
| `openspec/changes/contrato-ui-orquestador/…` | Create | Trail materialization: `proposal.md`, `specs/{ui-orchestrator-contract,game-server}/spec.md`, this `design.md`. |

## Interfaces / Contracts

### Session store (`src/orchestrator/session.py`)

```python
@dataclass
class Room:
    code: str
    game: Game
    host_token: str
    players: dict[str, str]      # session token -> alias (1:1, insertion order)
    lock: threading.Lock         # single-writer lock for this game

@dataclass(frozen=True)
class IssuedIdentity:
    room_code: str
    session_token: str
    alias: str

class SessionStore:
    def create(self, *, game: Game) -> IssuedIdentity: ...      # host, alias "Jugador 1"
    def join(self, room_code: str, *, game: Game) -> IssuedIdentity | None: ...  # None → room not found
    def room(self, room_code: str) -> Room | None: ...           # normalized upper-case lookup
    def alias_for(self, room: Room, token: str) -> str | None: ...   # None → unknown/foreign token
    def is_host(self, room: Room, token: str) -> bool: ...
```

### Server (`src/orchestrator/server.py`)

```python
@dataclass(frozen=True)
class ServerConfig:
    temperature: float = 0.9
    top_p: float = 0.9
    system_prompt_version: str = "v2"
    model_id: str = ""            # default: os.environ.get("SOSPECHAI_MODEL_ID", "")

class GameServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, addr, store: SessionStore, client: EngineClient, *,
                 prompts: Sequence[str] = DEFAULT_PROMPTS,
                 config: ServerConfig = ServerConfig(),
                 clock: Callable[[], float] = time.monotonic,
                 game_factory: Callable[[], Game] | None = None,
                 timer_tick: float = 0.5) -> None: ...
    def start_timer(self) -> None: ...
    def stop_timer(self) -> None: ...
```

### Error mapping (per-route RuleViolation disambiguation chains)

| Endpoint | RuleViolation source | Disambiguation chain (in domain raise order) | Code (HTTP) |
|---|---|---|---|
| join | `add_player` | room missing handled pre-call → `room_not_found`(404); else state ≠ LOBBY → `wrong_state` | `wrong_state` (409) |
| start | `start` | host pre-check → `forbidden_host_action`(403); state ≠ LOBBY → `wrong_state`; else → `invalid_roster` (409) | `wrong_state`/`invalid_roster` (409) |
| messages | `submit_message` | state ≠ RONDA → `wrong_state`; normalized empty → `empty_message`(400); words > `max_words` → `too_many_words`(400); else → `duplicate_message` (409) | per chain |
| voting/open | `open_voting` | host pre-check → `forbidden_host_action`(403); else → `wrong_state` (409) | `wrong_state` (409) |
| votes | `cast_vote` | state ≠ VOTACION → `wrong_state`; suspect ∉ players → `not_a_player`(403); voter == suspect → `self_vote`(400); voter already voted → `duplicate_vote`(409); else → `ai_cannot_vote`(403, unreachable via HTTP) | per chain |

Transport failures: malformed JSON / missing body → `malformed_request` (400); unknown path → `not_found` (404); wrong verb on known path → `method_not_allowed` (405); unexpected exception → `internal` (500). Error body: `{"code": "...", "message": "<Spanish domain message verbatim | transport text>"}`. Interruption reasons travel only inside `result().interruption_reason`, never as HTTP codes.

### AI request construction

```python
request = pb.UtteranceRequest(
    room_id=room.code,
    persona_id="p1",
    prompt=prompts[game.round_number - 1],      # one per round; injected
    config=pb.GenerationConfig(
        temperature=config.temperature, top_p=config.top_p,
        max_words=game.max_words,               # domain authority
        system_prompt_version=config.system_prompt_version,
        engine_backend="hf-router", model_id=config.model_id,
    ),
)
# apply_ai_turn(game, ai_alias, client, request, timeout=8.0)
# engine_client rejects empty model_id → surfaced as internal in tests unless configured
```

## Testing Strategy

Strict TDD (`uv run pytest`, `filterwarnings=["error"]`), AAA blocks, no real Hugging Face. Loopback HTTP uses `ThreadingHTTPServer` on port 0 + stdlib `http.client` (no new deps), mirroring the `serve()` contextmanager pattern of `tests/test_engine_integration.py`; fakes follow `FakeStub`/`Clock` patterns from `tests/test_api_boundary.py`.

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit — session | token/alias/room-code issuance; 1:1 binding; unknown/foreign tokens; spoofing impossible; normalized upper-case room codes; collision retry | `test_session.py` — arrange store with fresh `Game`; act; assert identities |
| Integration — routing | all 7 endpoints vs domain ops; unknown path 404; wrong verb 405; malformed JSON 400; client-supplied alias/round ignored; mirrored `public_state()` shapes verbatim (key-set equality, `result` only at REVELACION); frozen wire values exact (case-sensitive) | `test_server.py` — table-driven loopback over real sockets |
| Integration — errors | full catalog table: every provokable `RuleViolation` through HTTP → code + Spanish message verbatim; `internal` on injected handler crash | `test_server.py` — table-driven assertion of code/status/message |
| Integration — host & session | non-host `start`/`open_voting` → 403 and domain not invoked; invalid roster 409; `start` registers AI last + RONDA; join after LOBBY 409; unknown token 401 | `test_server.py` — end-to-end loops |
| Timer | zero-client expiry → REVELACION + `interruption_reason:"round_timeout"` on next poll; VOTACION never auto-advances; tick respects `stop_timer` | `test_server_timer.py` — real timer thread with tiny `round_timeout` (e.g. 0.05 s) and no polling; Clock injection where needed |
| Concurrency | two concurrent remaining votes → exactly one REVELACION, one embedded result; mixed concurrent mutations + state fetch → consistent snapshot; AI turn exactly-once | `test_server_timer.py` — threads + barrier, assert single transition |
| AI turn | last human message triggers AI message (round advances); budget recorded `min(8, remaining)`; engine failure → matching `interruption_reason` and `client.calls == 1`; AI text passes validator | `test_server_timer.py` — `FakeStub` success/error deltas |
| Privacy | pre-REVELACION probing (state, error bodies, headers) leaks no `is_ai`/`votes`/`impostor_alias`; interrupted game still privacy-safe; delivered snapshot bytes immutable after later mutation | `test_server.py` — probe + mutate + re-read |

**Key RED tests (written first, per requirement):** alias spoofing (forged alias field); two concurrent votes single reveal; timer fires with zero client queries; wire values asserted exactly; full RuleViolation→code table; AI turn exactly one RPC attempt; pre-REVELACION probing leaks nothing; non-host start refused.

## Threat Matrix

Not applicable — **no routing/shell/subprocess/VCS/PR/executable-classification boundary** exists in this change. The design adds no shell commands, subprocesses, git/PR automation, or executable-file classification; "routing" here is HTTP path/method dispatch inside application code, which is covered by the table-driven routing tests in the Testing Strategy above, not by the process-integration matrix.

| Boundary | Applicability | Reason |
|---|---|---|
| Documentation-like paths (`requirements.txt`, executable MD/MDX, `README.sh`) | N/A | No documentation files are executed or classified; only `docs/CONTRATO_UI_ORQUESTADOR.md` (already merged) is referenced as a spec |
| Git repository selection (`git -C`, relative/absolute paths) | N/A | No git invocation in server code or tests |
| Commit state (staged, `commit -a`, empty index) | N/A | No commit/index manipulation |
| Push state (tracking branch, first push, explicit refspec) | N/A | No push logic |
| PR commands (`--head`, environment prefix, composed commands) | N/A | No PR automation |

## Migration / Rollout

No data migration, no schema change, no dependency change, no feature flags.

**Rollout**: this is a **server implemented after its contract is already merged** — the R2-1 publish gate (doc + R3 notification) completed at PR #36 on `develop`. Branch `feature/a9-contrato-ui-orquestador` from `develop`; commits `feat:`/`test:`/`fix:`/`chore:` with ticket A9; delivery strategy **ask-on-risk** (single PR unless forecast says otherwise).

**400-line budget note for sdd-tasks**: the contract doc (≈407 lines) is **already merged** and does NOT count toward this change's authored lines; remaining authored text = `session.py` + `server.py` + 3 test files. Reused patterns (`Clock`, `FakeStub`, `serve()` loopback) keep tests compact. Forecast is expected **Low–Medium**; tasks phase must confirm and recommend chaining if High.

**Rollback**: delete `server.py`, `session.py` and the 3 test files — `game.py`, `storage.py`, `engine_client.py`, `demo.py` untouched, so revert is a clean file removal with zero data impact.

## Open Questions

Sections referenced follow the merged contract v1.0 (`docs/CONTRATO_UI_ORQUESTADOR.md`).

- [ ] **R3 confirmation — pending UI decisions adopted by default** (design does NOT resolve them; the contract flags each as "decisión requerida de R3"):
  1. Polling refresh fit — **resolved by R3** (`router.py`: 1.0 s active / 2.5 s idle). No server impact.
  2. Client-chosen display-name overlay — adopted default: **none** in R2 (contract §14.2). Local-only overlay is a client concern; server stores aliases only.
  3. AI display in the lobby — adopted default: **anonymous identical rendering**; never label the AI (contract §14.3). The server already exposes the AI's alias in `players` from RONDA; presentation is R3's.
  4. Close-event surfacing — adopted default: **final-state fetch** (`state == "REVELACION"`); no explicit event flag in v1.0 (contract §14.4). Server behavior already final-state fetchable.
- [ ] **`SOSPECHAI_MODEL_ID` provisioning**: default `model_id` for real runs must be set in the environment at deployment; tests always override it (fake stubs never call HF). Owner: R2-1 apply + docker-compose entry (no engine change).
- [ ] **demo.py retention**: design keeps it unchanged; explicit sign-off that the console harness stays the R2 demo path alongside the server (or a follow-up ticket to retire it).
- [ ] **`engine_timeout` vs `round_timeout` at the window boundary** (Low risk): if the AI RPC's deadline coincides exactly with the ROUND window end, the interruption reason may surface as `engine_timeout` (grpc `DEADLINE_EXCEEDED` maps to it) rather than `round_timeout`. Both are valid contract codes that lead to REVELACION with `valid_game: false`; the UI renders the same final state. Accepted; documented for verify.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Blocking polls during an AI turn (≤ 8 s, room-scoped only) | Low | Accepted trade-off (Decision 5); turn-based game; unrelated rooms unaffected (per-room locks) |
| `engine_timeout` vs `round_timeout` at boundary (see Open Questions) | Low | Both valid codes; same terminal UX; captured in verify-report |
| RuleViolation disambiguation chains drift from domain raise order | Med | Chains mirror each operation's parenthetical order; table-driven catalog tests exercise every violation through HTTP; any new domain rule forces a test addition |
| Spanish wire values drift (RONDA/DISCUSION/VOTACION/REVELACION) | Med | Contract froze them; tests assert exact strings case-sensitive |
| Disk-full blocking `uv run pytest` at apply | Med | Stdlib-only server, zero new deps; re-verify once disk freed (baseline ~134 MiB free) |
| Wrong-verb handling nuance (`/rooms/{code}/voting/open` double segment) | Low | Single routing parser maps path→(endpoint, room_code); segment-count checked before regex match; table-tested |