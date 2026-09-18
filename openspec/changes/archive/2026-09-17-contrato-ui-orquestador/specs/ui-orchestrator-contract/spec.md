# Domain: ui-orchestrator-contract (NEW full spec)

> Materialized from Engram observation #8 (`sdd/contrato-ui-orquestador/spec`) when this change
> migrated from the engram store to the openspec trail mid-flight. Content preserved from the
> spec-phase source; the publishable contract document itself lives at
> `docs/CONTRATO_UI_ORQUESTADOR.md` (v1.0, already merged on `develop` via PR #36).

## Purpose

The published, self-contained HTTP+JSON contract between the UI role (R3) and the orchestrator: transport, identity model, room lifecycle, endpoint surface, wire shapes mirroring `public_state()`/`result()` verbatim, frozen Spanish state values, stable error-code catalog, privacy guarantees, reconnect policy, AI-turn timing, timer ownership, additive upgrade path, and explicitly surfaced pending UI decisions.

## Requirements

### Requirement: Contract document publication

The change MUST publish `docs/CONTRATO_UI_ORQUESTADOR.md` as a self-contained document consumable by the UI role without any other source. The document MUST contain: title/version/date; scope (in and explicitly out); transport; identity model; room lifecycle and close event; endpoints with method/path/headers/request/response JSON examples; error-code catalog; state machine overview with frozen Spanish wire values; privacy guarantees; reconnect policy; AI-turn timing; timer semantics; additive upgrade path (WebSocket/gRPC); and a section "Decisiones pendientes del rol UI (R3)". The document MUST be published BEFORE implementation (publish gate) and R3 MUST be notified.

#### Scenario: Publishable standalone document

- GIVEN the spec phase has completed and the contract file exists at `docs/CONTRATO_UI_ORQUESTADOR.md`
- WHEN a UI developer opens the document
- THEN every mandated section is present with concrete values (endpoint JSON examples, error table, frozen state strings)
- AND the document states its version (1.0) and freeze date (2026-09-16)

#### Scenario: Publish gate before apply

- GIVEN the contract document is the R2-1 deliverable
- WHEN the apply phase is about to start
- THEN the document exists in the repo and the UI role (R3) has been notified
- AND no server implementation is considered complete before the document is published

### Requirement: HTTP+JSON polling transport

The contract MUST specify HTTP/1.1 plus JSON bodies and a polling snapshot model as the only R2 transport. The server MUST NOT require a persistent connection. WebSocket/gRPC MUST be documented only as an additive upgrade path that never removes or breaks HTTP+JSON.

#### Scenario: Polling is the canonical read model

- GIVEN a room in RONDA
- WHEN the UI polls `GET /rooms/{room_code}/state` every tick
- THEN each response returns the current snapshot and the UI can render without push events

#### Scenario: Additive upgrade path documented

- GIVEN the contract v1.0 is frozen
- WHEN a future version adds WebSocket or gRPC
- THEN the upgrade section documents them as additive endpoints/services using the same token and wire values
- AND HTTP+JSON v1.0 remains valid and unmodified

### Requirement: Endpoint surface

The contract MUST define exactly these seven endpoints with method, path, headers and semantics: `POST /rooms` (create room, host joins as "Jugador 1"); `POST /rooms/{room_code}/join` (add human player, LOBBY only); `POST /rooms/{room_code}/start` (host only; registers the AI and calls `start()`); `POST /rooms/{room_code}/messages` (submit round message; server binds alias from token and current round); `POST /rooms/{room_code}/voting/open` (host only; DISCUSION to VOTACION); `POST /rooms/{room_code}/votes` (cast vote; voter bound from token, suspect by alias); `GET /rooms/{room_code}/state` (snapshot). Successful mutations MUST return minimal bodies (201 for create/join with issuance data; 204 otherwise); the state endpoint MUST return the verbatim `public_state()` body.

#### Scenario: One-to-one endpoint to domain mapping

- GIVEN the seven endpoints defined in the contract
- WHEN a client exercises each one
- THEN each maps to exactly one domain operation (create/join → `add_player`; start → `start()`; messages → `submit_message`; voting/open → `open_voting()`; votes → `cast_vote`; state → `public_state()`)

#### Scenario: Unknown path and method

- GIVEN a request to a path not defined in the contract
- WHEN the server receives it
- THEN it responds `not_found` (404)
- AND a known path with an unsupported verb responds `method_not_allowed` (405)

### Requirement: Mirrored response shapes

All state responses MUST mirror `public_state()` verbatim: keys `state`, `round_number`, `rounds`, `max_words`, `players` (aliases only), `messages` (`{round_number, alias, text}`), `votes_received` (count only), `remaining_seconds`, plus `result` embedded ONLY at REVELACION (`result()` keys: `state`, `impostor_alias`, `rounds`, `max_words`, `votes`, `vote_counts`, `scores`, `valid_game`, `interruption_reason`, `tasa_deteccion`, `transcript`). The server MUST NOT add, rename, reorder or remove any key inside these bodies, and MUST NOT derive new values.

#### Scenario: Snapshot before REVELACION has no result

- GIVEN a room in VOTACION
- WHEN the UI fetches `GET /rooms/{room_code}/state`
- THEN the response contains exactly the public_state keys with `result: null`
- AND it contains no `is_ai`, no vote detail, no `impostor_alias`

#### Scenario: Snapshot at REVELACION embeds the full result

- GIVEN a room that just reached REVELACION
- WHEN the UI fetches the state snapshot
- THEN `state` is `"REVELACION"` and `result` is embedded with all result keys
- AND `is_ai` appears only inside `result.transcript`

### Requirement: Session identity model

The contract MUST specify an opaque server-issued session token per player bound one-to-one to a server-assigned alias (`"Jugador N"`, N = insertion order). The client MUST NOT choose, propose or override the alias. The server MUST issue a room code at creation; the room creator is the host; `start` and `open_voting` are host-only. Tokens MUST be valid for the lifetime of the room.

#### Scenario: Create and join issue identity

- GIVEN a client calls `POST /rooms`
- WHEN the server creates the room
- THEN it returns `room_code`, `session_token` and `alias: "Jugador 1"`
- AND a second client joining receives a distinct token and `alias: "Jugador 2"`

#### Scenario: Client-chosen alias is refused

- GIVEN a client sends a join or message request containing a self-chosen alias field
- WHEN the server processes it
- THEN the field is ignored or rejected (never honored)
- AND the alias on the wire remains the server-assigned one

### Requirement: Frozen wire values

The contract MUST freeze the state value strings: `"LOBBY"`, `"RONDA"`, `"DISCUSION"`, `"VOTACION"`, `"REVELACION"`. The four Spanish values and all other wire strings MUST NOT change within R2. Interruption reasons (`round_timeout`, `engine_timeout`, `engine_unavailable`, `engine_protocol`, `engine_rejected`, `invalid_engine_response`) MUST be documented as `interruption_reason` payload values in `result()`, not as HTTP error codes.

#### Scenario: Wire values asserted exactly

- GIVEN the contract and the domain both describe the state machine
- WHEN a test asserts the state strings returned by the server
- THEN they equal `"LOBBY"`, `"RONDA"`, `"DISCUSION"`, `"VOTACION"`, `"REVELACION"` exactly (case-sensitive)

#### Scenario: Interruption codes are payload, not HTTP errors

- GIVEN a round expires
- WHEN the game reaches REVELACION via interruption
- THEN the client observes `interruption_reason: "round_timeout"` inside `result`
- AND the HTTP responses themselves use the standard error-catalog codes only

### Requirement: Stable error-code catalog

The contract MUST define a stable, frozen machine-readable error-code catalog mapping every domain `RuleViolation` and transport failure to a code plus an HTTP status. Catalog: `malformed_request` (400), `empty_message` (400), `too_many_words` (400), `self_vote` (400), `session_expired` (401), `not_a_player` (403), `ai_cannot_vote` (403), `forbidden_host_action` (403), `room_not_found` (404), `not_found` (404), `method_not_allowed` (405), `wrong_state` (409), `duplicate_message` (409), `duplicate_vote` (409), `invalid_roster` (409) — `invalid_roster` covers `start` with fewer than 2 humans — and `internal` (500). Every error body MUST carry the code and the Spanish human-readable message preserved from the domain `RuleViolation` when the failure is a domain rule.

#### Scenario: Domain rule violations map to codes

- GIVEN a player submits a second message in the same round
- WHEN the server returns the error
- THEN the body is `{"code": "duplicate_message", "message": "<Spanish domain message>"}` with HTTP 409
- AND the client can branch on `code` without parsing `message`

#### Scenario: Transport failures map to codes

- GIVEN a request with malformed JSON body and a request to an unknown route
- WHEN the server processes them
- THEN they return `malformed_request` (400) and `not_found` (404) respectively

### Requirement: Room lifecycle and close event

The contract MUST define the room lifecycle: created on `POST /rooms`; joins only while LOBBY; terminal after REVELACION (including interruptions); final REVELACION snapshot remains fetchable while the server process is alive; the close event is surfaced through the state snapshot (UI observes `state == "REVELACION"`). The surfaces for the four UI-pending items MUST be flagged, not silently resolved (see "Pending UI decisions" requirement).

#### Scenario: Lifecycle progression

- GIVEN a room in LOBBY
- WHEN joins, start, round messages, open_voting and votes complete normally
- THEN the room progresses LOBBY → RONDA → DISCUSION → VOTACION → REVELACION
- AND after REVELACION the final snapshot with embedded `result` is still fetchable with a valid token

#### Scenario: Join after LOBBY is refused

- GIVEN a room already past LOBBY (e.g. in RONDA)
- WHEN a new client calls join
- THEN the server returns `wrong_state` (409)

### Requirement: Reconnect policy

The contract MUST specify: session token valid for the room lifetime with no inactivity expiry; rejoin mid-round re-reads the current state with the same token (no special handshake); a disconnected human does not block the round; ROUND window expiry triggers auto-advance via `check_expiration()`; mark-and-continue is NOT in R2 (would require a domain change).

#### Scenario: Rejoin mid-round

- GIVEN a player's client reconnects during RONDA with the stored token
- WHEN the client calls `GET /rooms/{room_code}/state`
- THEN it receives the current snapshot (round, messages, count)
- AND no re-join or re-authentication flow is required

#### Scenario: Human disconnects during the round

- GIVEN one human stops polling while others continue
- WHEN the ROUND window expires without that human's message
- THEN the server timer calls `check_expiration()` and the room auto-advances to REVELACION with `interruption_reason: "round_timeout"`
- AND the other humans observe the transition in their next poll

### Requirement: AI-turn timing

The contract MUST specify: the server adds exactly one AI player at game start (always the last "Jugador N"); the AI turn is triggered when all humans have submitted their round message; AI budget is `min(8 s, remaining window)` within the 20 s ROUND window; exactly one RPC attempt, never retried; AI text passes the same `submit_message` validator; the AI never votes.

#### Scenario: AI turn after all humans submit

- GIVEN a RONDA where the last remaining human submits a message with 12 s of window left
- WHEN the server loop detects all humans have submitted
- THEN it triggers `apply_ai_turn` with an 8 s budget
- AND the round advances once the AI message lands

#### Scenario: Engine failure interrupts, never retries

- GIVEN the engine RPC fails during the AI turn
- WHEN the single attempt returns an error or exceeds the budget
- THEN the server interrupts with the corresponding `interruption_reason` code (`engine_unavailable`, `engine_timeout`, `engine_protocol`, `engine_rejected` or `invalid_engine_response`)
- AND no second attempt is made

### Requirement: Timer ownership and auto-advance

The contract MUST specify that the server owns the timer that calls `check_expiration()` and MUST call it even with zero client queries; auto-advance/auto-reveal on expiry is advertised through the state snapshot; only ROUND has a time window (default 20 s); VOTACION has no deadline in R2 (waits for all humans; last human vote auto-reveals).

#### Scenario: Expiration fires with zero client queries

- GIVEN a server with no client polling for the whole ROUND window
- WHEN the window elapses
- THEN the server-owned timer calls `check_expiration()` regardless of client activity
- AND a later poll returns REVELACION with `interruption_reason: "round_timeout"`

#### Scenario: Voting window waits for all humans

- GIVEN VOTACION is open with two humans and one vote cast
- WHEN no second vote arrives for an arbitrarily long time
- THEN the room remains in VOTACION (no countdown, no reveal)
- AND the second human's vote triggers the reveal

### Requirement: Privacy guarantees

The contract MUST guarantee that `is_ai`, vote detail and `impostor_alias` are never exposed before REVELACION: `public_state()` never contains them; `votes_received` is a count only; `is_ai` appears only in `result().transcript`; snapshots are defensive copies. The server MUST expose no debug route or field leaking these values early.

#### Scenario: Pre-REVELACION probing leaks nothing

- GIVEN a room in VOTACION under the server
- WHEN a client fetches the state snapshot
- THEN the response contains no `is_ai`, no votes object, no `impostor_alias`
- AND no other route returns them early

#### Scenario: Interrupted game still privacy-safe

- GIVEN a game interrupted to REVELACION (e.g. `engine_unavailable`)
- WHEN the final snapshot is fetched
- THEN `result` contains `valid_game: false`, `interruption_reason` set, `scores` empty and `tasa_deteccion` null
- AND `is_ai` is revealed only in `transcript`, exactly as in a valid game

### Requirement: Pending UI decisions surfaced

The contract MUST list the four pending UI (R3) decisions with a concrete default recommendation each, each flagged as a required R3 decision, and MUST NOT silently resolve them: (1) polling refresh fit (default: 1 s ticks in active states, 2–3 s in LOBBY/REVELACION); (2) client-chosen display-name overlay (default: none in R2; alias mandatory, server-assigned); (3) AI lobby display given the "Jugador N" last-position hint (default: anonymous identical rendering; never label the AI); (4) close-event surfacing (default: final-state fetch — UI detects `state == "REVELACION"`; explicit event flag additive only if R3 requires it).

#### Scenario: All four items present with defaults and flags

- GIVEN the contract document
- WHEN a reader inspects the pending-decisions section
- THEN exactly the four items are listed, each with a default recommendation and an explicit "decisión requerida de R3" flag, and none is presented as already resolved

---

## Spec-Level Decisions (recorded during the spec phase — Engram #9)

Recorded when the delta spec above was authored; preserved here for the trail:

1. **Error code `invalid_roster` (409)** added to the catalog — the proposal's seed catalog had no
   code for `start()`'s roster `RuleViolation`; the "all RuleViolations mapped" requirement forces it.
2. **AI player is registered at START time, not room creation**: `game.py` aliases follow insertion
   order, so adding the AI at creation would make it "Jugador 2" and break "AI joins last"; adding it
   immediately before `start()` under the single-writer lock is the only way to keep the AI last with
   `game.py` unchanged.
3. **Auth header chosen: `X-Session-Token`** on all endpoints except `POST /rooms` and join; mutations
   return 204; create/join return 201 with `{room_code, session_token, alias}`; GET state returns
   `public_state()` verbatim with no envelope.
4. **Contract doc written in Spanish** (project convention — `docs/` are Spanish: INICIO_R2.md,
   ACUERDOS_R2.md; UI-role audience); SDD spec artifact in English per the language domain contract.
5. **`LOBBY` stays the wire value** (English) — no Spanish value invented; only
   RONDA/DISCUSION/VOTACION/REVELACION are the frozen Spanish values.