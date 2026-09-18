# Domain: game-server (NEW full spec)

> Materialized from Engram observation #8 (`sdd/contrato-ui-orquestador/spec`) when this change
> migrated from the engram store to the openspec trail mid-flight. Content preserved from the
> spec-phase source.

## Purpose

The HTTP+JSON server wrapper (`src/orchestrator/server.py`) plus session store (`src/orchestrator/session.py`) that make the existing lock-free `game.py` domain playable by several real players over the published contract: stdlib-only transport, session-bound identity, single-writer serialization, server-owned timer, AI-turn trigger, host-only enforcement, and stable error-code mapping, with `game.py` and `storage.py` unchanged and zero new dependencies.

## Requirements

### Requirement: Stdlib-only HTTP+JSON server

The server MUST be implemented with the Python standard library `http.server` only. Runtime dependencies MUST remain exactly grpcio, protobuf and python-dotenv; no new dependency MAY be added. Responses MUST be JSON with HTTP statuses per the contract.

#### Scenario: No new dependencies

- GIVEN the apply phase implements the server
- WHEN the dependency set is checked
- THEN no new package is added to `pyproject.toml` or imported beyond stdlib plus the existing runtime deps
- AND the server runs without `uv sync` (disk-constrained environment)

#### Scenario: JSON contract responses

- GIVEN any endpoint responds
- WHEN the response is inspected
- THEN it carries `Content-Type: application/json` (or empty body for 204) and the contract's shapes

### Requirement: Endpoint-to-domain routing

The server MUST route the seven contract endpoints one-to-one onto the domain operations, binding identity server-side: `alias` always comes from the session token (never from the request body) and `expected_round` for `submit_message` comes from the current state (clients MUST NOT supply it). Unknown paths MUST return `not_found`; wrong verbs `method_not_allowed`; malformed bodies `malformed_request`.

#### Scenario: Alias and round bound server-side

- GIVEN a message submission request containing only `{"text": "..."}`
- WHEN the server routes it to `submit_message`
- THEN the alias is resolved from the token and the round from the current state
- AND any client-supplied alias or round field is ignored

#### Scenario: Routing fallbacks

- GIVEN a request with an unknown path and a request with a wrong verb on a known path
- WHEN the server routes them
- THEN they produce `not_found` (404) and `method_not_allowed` (405) respectively

### Requirement: Session store binding

The session store MUST issue an opaque token per joined player bound one-to-one to the server-assigned alias; it MUST be impossible to spoof another player's alias (a token always resolves to exactly one alias, and unknown/foreign tokens fail); tokens MUST remain valid for the room lifetime; expired/unknown tokens MUST yield `session_expired` (401) or `not_a_player` (403) per the catalog.

#### Scenario: Alias spoofing impossible

- GIVEN an attacker holds another player's known alias string
- WHEN the attacker submits a message or vote with their own valid token but a forged alias field
- THEN the server binds the alias from the token, ignoring the forged field
- AND the message/vote is attributed to the attacker's own alias

#### Scenario: Unknown token rejected

- GIVEN a request with a token the server never issued
- WHEN the request reaches an authenticated endpoint
- THEN the server responds `session_expired` (401)
- AND no alias is resolved

### Requirement: Single-writer serialization with no double-fire reveal

The server MUST serialize all mutations on the Game instance through a single-writer lock (the domain stays lock-free). The "last human vote triggers REVELACION" invariant MUST fire exactly once even under concurrent vote submission.

#### Scenario: Two concurrent votes, one reveal

- GIVEN VOTACION with two humans, one of whom has already voted
- WHEN both remaining humans submit their votes concurrently
- THEN the lock serializes the mutations, the domain transitions to REVELACION exactly once
- AND the resulting snapshot is the final REVELACION state with `result` embedded (no duplicate transition, no error)

#### Scenario: Mixed concurrent mutations serialize

- GIVEN concurrent message submissions and a state fetch racing with them
- WHEN they reach the server simultaneously
- THEN each mutation applies under the lock in some order and the state fetch returns a consistent snapshot
- AND no partial mutation is observable

### Requirement: Host-only action enforcement

The server MUST enforce that `start` (with AI registration) and `open_voting` are executable only by the room host, derived from the session token; non-host attempts MUST return `forbidden_host_action` (403); `start` with fewer than 2 humans MUST return `invalid_roster` (409).

#### Scenario: Non-host start refused

- GIVEN a joined non-host player with a valid token
- WHEN that player calls `POST /rooms/{room_code}/start`
- THEN the server returns `forbidden_host_action` (403)
- AND the domain `start()` is never invoked

#### Scenario: Host start with insufficient humans

- GIVEN a LOBBY room with only the host (1 human)
- WHEN the host calls `start`
- THEN the server returns `invalid_roster` (409)
- AND the game stays in LOBBY

#### Scenario: Host start with valid roster

- GIVEN a LOBBY room with at least 2 humans
- WHEN the host calls `start`
- THEN the server adds the AI as the last "Jugador N", calls `start()` under the lock, and the room enters RONDA round 1
- AND the AI is visible in `players` as the last alias

### Requirement: Timer-driven check_expiration with zero queries

The server MUST run its own timer (server-owned loop) calling `check_expiration()` periodically regardless of client activity; expiration MUST auto-advance the game exactly as the domain rules define (ROUND window expiry → `round_timeout` interruption → REVELACION), and the result MUST be observable in the next state fetch.

#### Scenario: Timer fires with no client queries

- GIVEN a RONDA whose window elapses while no client polls
- WHEN the server timer ticks past the deadline
- THEN `check_expiration()` executes without any client request
- AND a subsequent `GET /state` returns REVELACION with `interruption_reason: "round_timeout"`

#### Scenario: Only ROUND has a timer in R2

- GIVEN a room in VOTACION
- WHEN time passes without all humans voting
- THEN no timer fires and the room remains in VOTACION
- AND the expiry behavior applies only to the ROUND window

### Requirement: AI-turn trigger in the server loop

The server loop MUST trigger `apply_ai_turn` for the AI player once all humans have submitted their round message: validate turn, budget = `min(8 s, remaining window)`, exactly one RPC attempt, no retries; AI text MUST pass the same `submit_message` validator; engine/stream failures MUST map to the contract's interruption reasons; the AI MUST never be able to vote.

#### Scenario: AI turn fires after the last human message

- GIVEN a RONDA where all humans have submitted
- WHEN the server loop detects the completion
- THEN it triggers `apply_ai_turn` with `min(8, remaining)` seconds
- AND the round advances when the AI message is accepted

#### Scenario: Engine failure yields interruption, not retry

- GIVEN the engine RPC fails during the AI turn
- WHEN the single attempt exhausts its budget or errors
- THEN the server interrupts with the mapped `interruption_reason` code
- AND no retry is attempted and no AI-vote path exists

### Requirement: Error-code mapping

The server MUST map every domain `RuleViolation` and transport failure to the contract catalog's codes and HTTP statuses, preserving the Spanish domain message verbatim in the error body `message` field (`{"code": ..., "message": ...}`); clients branch on `code`.

#### Scenario: Full RuleViolation mapping

- GIVEN table-driven tests over each guarded domain operation
- WHEN each `RuleViolation` is provoked through the HTTP surface
- THEN the response code matches the catalog entry and the body message equals the domain's Spanish message

#### Scenario: Transport error mapping

- GIVEN malformed JSON, unknown route, wrong verb and an unexpected server exception
- WHEN the server handles each
- THEN the responses are `malformed_request` (400), `not_found` (404), `method_not_allowed` (405) and `internal` (500) respectively

### Requirement: Privacy boundary enforcement

The server MUST serve `public_state()` verbatim and MUST NOT expose `is_ai`, vote detail, or `impostor_alias` before REVELACION through any route, header, or debug field; the snapshot MUST be a defensive copy so later domain mutation cannot alter a serialized response.

#### Scenario: Probing leaks nothing pre-REVELACION

- GIVEN a server-side attempt to probe for hidden fields before REVELACION (state fetches, error bodies, headers)
- WHEN the responses are inspected
- THEN no `is_ai`, no votes object and no `impostor_alias` appear anywhere
- AND `votes_received` remains a bare count

#### Scenario: Serialized snapshot is a defensive copy

- GIVEN a state snapshot already serialized and delivered to a client
- WHEN the domain state later mutates (e.g. a vote arrives)
- THEN the previously delivered response bytes are unchanged

### Requirement: AI player registration is server-side

The server MUST register exactly one AI player (`add_player(is_ai=True)`) at game start as the last alias in "Jugador N" order, immediately before `start()`, under the same lock; clients MUST NOT be able to add AI players; the AI slot is never client-chosen.

#### Scenario: One AI always last at start

- GIVEN a LOBBY room with 2 humans
- WHEN the host starts the game
- THEN exactly one AI exists with alias `"Jugador 3"` (last)
- AND the roster requirement (`>=2 humans + exactly 1 AI`) is satisfied

#### Scenario: No client path to add an AI

- GIVEN the contract endpoint surface
- WHEN any client calls any documented endpoint with AI-related payloads or intentions
- THEN no endpoint adds an AI player
- AND attempts to influence `is_ai` are ignored or rejected

---

## Spec-Level Decisions (recorded during the spec phase — Engram #9)

Recorded when the delta spec above was authored; preserved here for the trail (shared with the
`ui-orchestrator-contract` domain — repeated here so each spec file is self-contained):

1. **Error code `invalid_roster` (409)** added to the catalog for `start()` with fewer than 2 humans.
2. **AI player is registered at START time** (immediately before `start()`, under the single-writer
   lock), so it is always the last "Jugador N" with `game.py` unchanged.
3. **Auth header chosen: `X-Session-Token`** on all endpoints except `POST /rooms` and join; mutations
   return 204; create/join return 201 with `{room_code, session_token, alias}`; GET state returns
   `public_state()` verbatim with no envelope.
4. **Contract doc written in Spanish**; SDD spec artifacts in English per the language domain contract.
5. **`LOBBY` stays the English wire value** — only RONDA/DISCUSION/VOTACION/REVELACION are the frozen
   Spanish values.