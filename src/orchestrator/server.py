"""Transporte HTTP+JSON del servidor multijugador (contrato UI-orquestador).

Envuelve el dominio sin candados de ``game.py`` con un servidor estándar:
rutas del contrato, identidad ligada al token (X-Session-Token), un candado
por sala alrededor de toda llamada al dominio y mapeo estable de errores.
El timer y el turno de la IA llegan en la fase 3; esta fase solo transporta.
"""

import json
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from src.orchestrator.engine_client import EngineClient
from src.orchestrator.game import Game, RuleViolation, normalize_text
from src.orchestrator.session import IssuedIdentity, Room, SessionStore

ROUTES = {
    "create": "POST",
    "join": "POST",
    "start": "POST",
    "messages": "POST",
    "open_voting": "POST",
    "votes": "POST",
    "state": "GET",
}

STATUS_BY_CODE = {
    "malformed_request": 400,
    "empty_message": 400,
    "too_many_words": 400,
    "self_vote": 400,
    "session_expired": 401,
    "not_a_player": 403,
    "ai_cannot_vote": 403,
    "forbidden_host_action": 403,
    "room_not_found": 404,
    "not_found": 404,
    "method_not_allowed": 405,
    "wrong_state": 409,
    "duplicate_message": 409,
    "duplicate_vote": 409,
    "invalid_roster": 409,
    "internal": 500,
}

TRANSPORT_MESSAGES = {
    "room_not_found": "Sala no encontrada.",
    "session_expired": "Token ausente, desconocido o de una sala reclamada.",
    "not_a_player": "El token no pertenece a un jugador de esta sala.",
    "forbidden_host_action": "Solo el anfitrión puede ejecutar esta acción.",
    "malformed_request": "Cuerpo JSON inválido o ausente.",
    "not_found": "Ruta desconocida.",
    "method_not_allowed": "Método no permitido para esta ruta.",
    "internal": "Error interno del servidor.",
}


def parse_route(path: str) -> tuple[str, str | None] | None:
    """Mapear ruta → (endpoint, room_code); None para rutas desconocidas.

    El conteo de segmentos se resuelve antes de comparar sufijos, evitando
    ambigüedad con ``/rooms/{code}/voting/open`` (doble segmento).
    """
    segments = [part for part in path.split("?", 1)[0].split("/") if part]
    if segments == ["rooms"]:
        return ("create", None)
    if len(segments) == 3 and segments[0] == "rooms":
        code = segments[1]
        suffix = segments[2]
        if suffix == "join":
            return ("join", code)
        if suffix == "start":
            return ("start", code)
        if suffix == "messages":
            return ("messages", code)
        if suffix == "votes":
            return ("votes", code)
        if suffix == "state":
            return ("state", code)
        return None
    if (
        len(segments) == 4
        and segments[0] == "rooms"
        and segments[2:4] == ["voting", "open"]
    ):
        return ("open_voting", segments[1])
    return None


def classify_start(game: Game) -> str:
    """Clasificar un RuleViolation de start según la etapa vigente."""
    if game.public_state()["state"] != "LOBBY":
        return "wrong_state"
    return "invalid_roster"


def classify_submit(game: Game, alias: str, text: str) -> str:
    """Clasificar un RuleViolation de submit_message con el estado vigente."""
    snapshot = game.public_state()
    if snapshot["state"] != "RONDA":
        return "wrong_state"
    normalized = normalize_text(text)
    if not normalized:
        return "empty_message"
    if len(normalized.split()) > game.max_words:
        return "too_many_words"
    return "duplicate_message"


def classify_vote(game: Game, voter_alias: str, suspect_alias: str) -> str:
    """Clasificar un RuleViolation de cast_vote con el estado vigente."""
    snapshot = game.public_state()
    if snapshot["state"] != "VOTACION":
        return "wrong_state"
    if suspect_alias not in snapshot["players"]:
        return "not_a_player"
    if voter_alias == suspect_alias:
        return "self_vote"
    # ai_cannot_vote es inalcanzable por HTTP: la IA nunca recibe token.
    return "duplicate_vote"


class _HttpError(Exception):
    """Error del contrato con código estable, status HTTP y mensaje humano."""

    def __init__(self, code: str, message: str) -> None:
        """Fijar el código, el mensaje y el status que dicta el catálogo."""
        self.code = code
        self.message = message
        self.status = STATUS_BY_CODE[code]
        super().__init__(f"{code}: {message}")


class GameServer(ThreadingHTTPServer):
    """Servidor multijugador con salas por token y candado por sala."""

    daemon_threads = True

    def __init__(
        self,
        addr: tuple[str, int],
        store: SessionStore,
        client: EngineClient,
        *,
        game_factory: Callable[[], Game] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Guardar el registro de sesiones, el cliente y la fábrica de partidas."""
        super().__init__(addr, ApiHandler)
        self.store = store
        self.client = client
        self._clock = clock
        self._game_factory = game_factory or (lambda: Game(clock=clock))
        self._token_rooms: dict[str, Room] = {}

    def new_game(self) -> Game:
        """Construir la partida con la fábrica inyectada (determinista en pruebas)."""
        return self._game_factory()

    def token_room(self, token: str) -> Room | None:
        """Resolver la sala ligada a un token emitido por este servidor."""
        return self._token_rooms.get(token)

    def record_token(self, identity: IssuedIdentity) -> None:
        """Asociar un token emitido a su sala para distinguir 401 de 403."""
        self._token_rooms[identity.session_token] = self.store.room(identity.room_code)


class ApiHandler(BaseHTTPRequestHandler):
    """Procesar peticiones JSON del contrato y delegar en el dominio."""

    protocol_version = "HTTP/1.0"
    server: GameServer

    def log_message(self, format: str, *args: object) -> None:
        """Silenciar el log de acceso del estándar; el contrato no lo expone."""

    def do_GET(self) -> None:
        """Atender la lectura de estado."""
        self._dispatch()

    def do_POST(self) -> None:
        """Atender las mutaciones y la creación de salas."""
        self._dispatch()

    # ------------------------------------------------------------------ ruteo

    def _dispatch(self) -> None:
        """Enrutar la petición y traducir cualquier fallo al catálogo."""
        try:
            self._route()
        except _HttpError as error:
            self._send_error(error)
        except Exception:
            self._send_error(_HttpError("internal", TRANSPORT_MESSAGES["internal"]))

    def _route(self) -> None:
        """Resolver ruta y verbo antes de delegar en el endpoint concreto."""
        parsed = parse_route(self.path)
        if parsed is None:
            raise _HttpError("not_found", TRANSPORT_MESSAGES["not_found"])
        endpoint, code = parsed
        if self.command != ROUTES[endpoint]:
            raise _HttpError(
                "method_not_allowed", TRANSPORT_MESSAGES["method_not_allowed"]
            )
        getattr(self, f"_handle_{endpoint}")(code)

    # ---------------------------------------------------------------- endpoints

    def _handle_create(self, _code: str | None) -> None:
        """Fundar una sala y emitir la identidad del anfitrión."""
        identity = self.server.store.create(game=self.server.new_game())
        self.server.record_token(identity)
        self._send_json(201, self._identity_body(identity))

    def _handle_join(self, code: str) -> None:
        """Unir un humano a la sala; el estado lo valida el dominio."""
        room = self.server.store.room(code)
        if room is None:
            raise _HttpError("room_not_found", TRANSPORT_MESSAGES["room_not_found"])
        try:
            identity = self.server.store.join(code, game=room.game)
        except RuleViolation as error:
            raise _HttpError("wrong_state", str(error)) from error
        self.server.record_token(identity)
        self._send_json(201, self._identity_body(identity))

    def _handle_start(self, code: str) -> None:
        """Registrar la IA y abrir la partida, solo para el anfitrión."""
        room, token = self._resolve_room_and_token(code)
        if not self.server.store.is_host(room, token):
            raise _HttpError(
                "forbidden_host_action", TRANSPORT_MESSAGES["forbidden_host_action"]
            )
        with room.lock:
            try:
                room.game.add_player(is_ai=True)
                room.game.start()
            except RuleViolation as error:
                raise _HttpError(classify_start(room.game), str(error)) from error
        self._send_204()

    def _handle_messages(self, code: str) -> None:
        """Registrar el mensaje de la ronda ligado al token (sin turno de IA aquí)."""
        room, alias = self._resolve_player(code)
        text = self._read_text_body()
        with room.lock:
            try:
                room.game.submit_message(
                    alias, text, expected_round=room.game.round_number
                )
            except RuleViolation as error:
                raise _HttpError(
                    classify_submit(room.game, alias, text), str(error)
                ) from error
        self._send_204()

    def _handle_open_voting(self, code: str) -> None:
        """Abrir la votación, solo para el anfitrión."""
        room, token = self._resolve_room_and_token(code)
        if not self.server.store.is_host(room, token):
            raise _HttpError(
                "forbidden_host_action", TRANSPORT_MESSAGES["forbidden_host_action"]
            )
        with room.lock:
            try:
                room.game.open_voting()
            except RuleViolation as error:
                raise _HttpError("wrong_state", str(error)) from error
        self._send_204()

    def _handle_votes(self, code: str) -> None:
        """Registrar el voto del humano ligado al token."""
        room, alias = self._resolve_player(code)
        suspect = self._read_suspect_body()
        with room.lock:
            try:
                room.game.cast_vote(alias, suspect)
            except RuleViolation as error:
                raise _HttpError(
                    classify_vote(room.game, alias, suspect), str(error)
                ) from error
        self._send_204()

    def _handle_state(self, code: str) -> None:
        """Servir la instantánea literal del dominio bajo el candado de la sala."""
        room, _ = self._resolve_player(code)
        with room.lock:
            body = json.dumps(room.game.public_state(), ensure_ascii=False).encode()
        self._send_bytes(200, body)

    # ------------------------------------------------------------------- ayuda

    def _identity_body(self, identity: IssuedIdentity) -> dict:
        """Construir la respuesta de creación/unión con las tres claves fijas."""
        return {
            "room_code": identity.room_code,
            "session_token": identity.session_token,
            "alias": identity.alias,
        }

    def _resolve_room_and_token(self, code: str) -> tuple[Room, str]:
        """Validar sala y token con la precedencia 404 → 401 → 403."""
        room = self.server.store.room(code)
        if room is None:
            raise _HttpError("room_not_found", TRANSPORT_MESSAGES["room_not_found"])
        token = self.headers.get("X-Session-Token", "")
        token_room = self.server.token_room(token)
        if token_room is None:
            raise _HttpError("session_expired", TRANSPORT_MESSAGES["session_expired"])
        if token_room is not room:
            raise _HttpError("not_a_player", TRANSPORT_MESSAGES["not_a_player"])
        return room, token

    def _resolve_player(self, code: str) -> tuple[Room, str]:
        """Resolver sala, token y el alias ligado al token."""
        room, token = self._resolve_room_and_token(code)
        alias = self.server.store.alias_for(room, token)
        if alias is None:
            raise _HttpError("not_a_player", TRANSPORT_MESSAGES["not_a_player"])
        return room, alias

    def _read_body(self) -> dict:
        """Leer y decodificar el cuerpo JSON exigido por una mutación."""
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise _HttpError(
                "malformed_request", TRANSPORT_MESSAGES["malformed_request"]
            ) from None
        if not isinstance(body, dict):
            raise _HttpError(
                "malformed_request", TRANSPORT_MESSAGES["malformed_request"]
            )
        return body

    def _read_text_body(self) -> str:
        """Extraer el campo text, exigido como cadena."""
        value = self._read_body().get("text")
        if not isinstance(value, str):
            raise _HttpError(
                "malformed_request", TRANSPORT_MESSAGES["malformed_request"]
            )
        return value

    def _read_suspect_body(self) -> str:
        """Extraer el campo suspect, exigido como cadena."""
        value = self._read_body().get("suspect")
        if not isinstance(value, str):
            raise _HttpError(
                "malformed_request", TRANSPORT_MESSAGES["malformed_request"]
            )
        return value

    # --------------------------------------------------------------- respuestas

    def _send_204(self) -> None:
        """Responder 204 sin cuerpo y sin Content-Type."""
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_json(self, status: int, payload: dict) -> None:
        """Responder JSON con las tildes conservadas y Content-Type explícito."""
        self._send_bytes(status, json.dumps(payload, ensure_ascii=False).encode())

    def _send_bytes(self, status: int, body: bytes) -> None:
        """Escribir una respuesta con cabeceras mínimas."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, error: _HttpError) -> None:
        """Serializar un error del contrato."""
        self._send_json(error.status, {"code": error.code, "message": error.message})
