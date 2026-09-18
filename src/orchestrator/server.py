"""Transporte HTTP+JSON del servidor multijugador (contrato UI-orquestador).

Envuelve el dominio sin candados de ``game.py`` con un servidor estándar:
rutas del contrato, identidad ligada al token (X-Session-Token), un candado
por sala alrededor de toda llamada al dominio y mapeo estable de errores.
La fase 3 añade el timer del servidor (expiración con cero consultas de
cliente) y el turno de la IA disparado al cerrar los humanos cada ronda.
"""

import argparse
import json
import logging
import os
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import grpc

from proto import impostor_pb2 as pb
from proto import impostor_pb2_grpc as rpc
from src.orchestrator.engine_client import EngineClient, apply_ai_turn
from src.orchestrator.game import (
    ABSTAIN_SENTINEL,
    Game,
    GameState,
    RuleViolation,
    normalize_text,
)
from src.orchestrator.session import IssuedIdentity, Room, SessionStore
from src.orchestrator.tracking import EngineUsage, RunParams, log_game_run

logger = logging.getLogger(__name__)

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

DEFAULT_PROMPTS = (
    "¿Qué harías si se va la luz justo antes de entregar un trabajo?",
    "¿Qué comida escogerías después de una clase larga?",
)


@dataclass(frozen=True)
class ServerConfig:
    """Configuración del motor para las peticiones del impostor (R1 hf-router).

    provider es el proveedor efectivo detrás del router (un hecho del
    despliegue, no del motor): el default coincide con la cuenta usada en
    el experimento y se reemplaza por entorno o línea de comandos.
    """

    temperature: float = 0.9
    top_p: float = 0.9
    system_prompt_version: str = "v2"
    model_id: str = field(
        default_factory=lambda: os.environ.get("SOSPECHAI_MODEL_ID", "")
    )
    provider: str = field(
        default_factory=lambda: os.environ.get("SOSPECHAI_PROVIDER", "featherless-ai")
    )


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
    """Clasificar un RuleViolation de cast_vote con el estado vigente.

    El sentinel de abstención no es un jugador, así que se considera primero:
    fuera de VOTACION manda ``wrong_state``; ya dentro, un segundo intento de
    abstención es ``duplicate_vote`` y nunca cae en ``not_a_player``.
    """
    snapshot = game.public_state()
    if snapshot["state"] != "VOTACION":
        return "wrong_state"
    if suspect_alias == ABSTAIN_SENTINEL:
        return "duplicate_vote"
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
    """Servidor multijugador con salas por token, candado por sala y timer."""

    daemon_threads = True

    def __init__(
        self,
        addr: tuple[str, int],
        store: SessionStore,
        client: EngineClient,
        *,
        prompts: Sequence[str] = DEFAULT_PROMPTS,
        config: ServerConfig = ServerConfig(),
        clock: Callable[[], float] = time.monotonic,
        game_factory: Callable[[], Game] | None = None,
        timer_tick: float = 0.5,
    ) -> None:
        """Guardar sesiones, motor, prompts/ajustes, fábrica de partidas y timer."""
        super().__init__(addr, ApiHandler)
        self.store = store
        self.client = client
        self.prompts = tuple(prompts)
        self.config = config
        self._clock = clock
        self._game_factory = game_factory or (lambda: Game(clock=clock))
        self._timer_tick = timer_tick
        self._token_rooms: dict[str, Room] = {}
        self._known_rooms: dict[str, Room] = {}
        self._timer_stop: threading.Event | None = None
        self._timer_thread: threading.Thread | None = None
        self._usage_by_room: dict[str, list[tuple[str, str]]] = {}
        self._tracked_rooms: set[str] = set()

    def new_game(self) -> Game:
        """Construir la partida con la fábrica inyectada (determinista en pruebas)."""
        return self._game_factory()

    def token_room(self, token: str) -> Room | None:
        """Resolver la sala ligada a un token emitido por este servidor."""
        return self._token_rooms.get(token)

    def record_token(self, identity: IssuedIdentity) -> None:
        """Asociar un token emitido a su sala y registrar la sala para el timer."""
        room = self.store.room(identity.room_code)
        self._token_rooms[identity.session_token] = room
        self._known_rooms[room.code] = room

    def start_timer(self) -> None:
        """Arrancar el hilo que expira las rondas vencidas del servidor."""
        if self._timer_thread is not None and self._timer_thread.is_alive():
            return
        self._timer_stop = threading.Event()
        self._timer_thread = threading.Thread(target=self._timer_loop, daemon=True)
        self._timer_thread.start()

    def stop_timer(self) -> None:
        """Detener el hilo de expiración y esperar a que termine."""
        if self._timer_stop is not None:
            self._timer_stop.set()
        if self._timer_thread is not None:
            self._timer_thread.join(timeout=5)
            self._timer_thread = None

    def record_usage(self, room: Room, pairs: Sequence[tuple[str, str]]) -> None:
        """Acumular la metadata de una respuesta publicada para el cierre."""
        self._usage_by_room.setdefault(room.code, []).extend(pairs)

    def log_finished_game(self, room: Room) -> None:
        """Registrar la partida terminal en MLflow, una única vez por sala.

        Se invoca bajo room.lock en los puntos que ya producen REVELACION
        (votos, turno de IA, timer o poll que expire la ronda); el guard de
        _tracked_rooms hace el registro idempotente. Sin metadata acumulada
        (partida interrumpida antes de cualquier respuesta exitosa) se
        registra usage=None: no se inventan ceros.
        """
        if room.code in self._tracked_rooms or room.game.state != GameState.REVEAL:
            return
        self._tracked_rooms.add(room.code)
        config = self.config
        params = RunParams(
            model_id=config.model_id,
            engine_backend="hf-router",
            provider=config.provider,
            temperature=config.temperature,
            top_p=config.top_p,
            system_prompt_version=config.system_prompt_version,
            max_words=room.game.max_words,
            n_players=len(room.players) + 1,
            n_rondas=room.game.rounds,
        )
        pairs = self._usage_by_room.get(room.code, [])
        try:
            usage = EngineUsage.from_trailing_metadata(pairs) if pairs else None
        except ValueError as error:
            logger.error(
                "Metadata de uso malformada en la sala %s: %s", room.code, error
            )
            usage = None
        try:
            log_game_run(params=params, result=room.game.result(), usage=usage)
        except Exception:
            logger.exception("No se pudo registrar la partida %s en MLflow", room.code)

    def _timer_loop(self) -> None:
        """Revisar cada sala conocida y expirar las rondas vencidas bajo su candado."""
        stop = self._timer_stop
        assert stop is not None
        while not stop.wait(self._timer_tick):
            for room in list(self._known_rooms.values()):
                with room.lock:
                    room.game.check_expiration()
                    self.log_finished_game(room)


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
        """Registrar el mensaje y disparar el turno de la IA al cerrar los humanos."""
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
            if self._humans_complete(room):
                self._run_ai_turn(room)
            self.server.log_finished_game(room)
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
        """Registrar el voto del humano ligado al token (sentinel → abstención)."""
        room, alias = self._resolve_player(code)
        suspect = self._read_suspect_body()
        with room.lock:
            try:
                room.game.cast_vote(
                    alias, None if suspect == ABSTAIN_SENTINEL else suspect
                )
            except RuleViolation as error:
                raise _HttpError(
                    classify_vote(room.game, alias, suspect), str(error)
                ) from error
            self.server.log_finished_game(room)
        self._send_204()

    def _handle_state(self, code: str) -> None:
        """Servir la instantánea literal del dominio bajo el candado de la sala."""
        room, _ = self._resolve_player(code)
        with room.lock:
            body = json.dumps(room.game.public_state(), ensure_ascii=False).encode()
            self.server.log_finished_game(room)
        self._send_bytes(200, body)

    # ------------------------------------------------------------------- ayuda

    def _identity_body(self, identity: IssuedIdentity) -> dict:
        """Construir la respuesta de creación/unión con las tres claves fijas."""
        return {
            "room_code": identity.room_code,
            "session_token": identity.session_token,
            "alias": identity.alias,
        }

    def _humans_complete(self, room: Room) -> bool:
        """Decidir si todos los humanos ya respondieron a la ronda vigente."""
        view = room.game.public_state()
        if view["state"] != "RONDA":
            return False
        submitters = {
            message["alias"]
            for message in view["messages"]
            if message["round_number"] == view["round_number"]
        }
        return all(alias in submitters for alias in room.players.values())

    def _run_ai_turn(self, room: Room) -> None:
        """Publicar una única respuesta del impostor y acumular su metadata."""
        game = room.game
        request = self._utterance_request(game, room.code)
        ai_alias = next(
            alias
            for alias in game.public_state()["players"]
            if alias not in room.players.values()
        )
        try:
            generated = apply_ai_turn(
                game, ai_alias, self.server.client, request, timeout=8.0
            )
        except Exception:
            raise _HttpError("internal", TRANSPORT_MESSAGES["internal"]) from None
        if generated is not None:
            self.server.record_usage(room, generated.trailing_metadata)

    def _utterance_request(self, game: Game, room_code: str) -> pb.UtteranceRequest:
        """Construir la petición del impostor con prompts y configuración inyectados."""
        prompt = self.server.prompts[game.round_number - 1]
        config = self.server.config
        return pb.UtteranceRequest(
            room_id=room_code,
            persona_id="p1",
            prompt=prompt,
            config=pb.GenerationConfig(
                temperature=config.temperature,
                top_p=config.top_p,
                max_words=game.max_words,
                system_prompt_version=config.system_prompt_version,
                engine_backend="hf-router",
                model_id=config.model_id,
            ),
        )

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


def _parse_args(arguments: list[str] | None = None) -> argparse.Namespace:
    """Definir las opciones de consola del servidor real."""
    parser = argparse.ArgumentParser(prog="sospechai-server", description=__doc__)
    parser.add_argument("--host", default="0.0.0.0", help="Interfaz de escucha.")
    parser.add_argument("--port", type=int, default=8080, help="Puerto de escucha.")
    parser.add_argument(
        "--model-id",
        default=os.environ.get("SOSPECHAI_MODEL_ID", ""),
        help="Modelo del engine hf-router.",
    )
    parser.add_argument(
        "--provider",
        default=os.environ.get("SOSPECHAI_PROVIDER", "featherless-ai"),
        help="Proveedor efectivo detrás del router (p. ej. featherless-ai).",
    )
    parser.add_argument("--rounds", type=int, default=2, help="Rondas por partida.")
    parser.add_argument(
        "--max-words", type=int, default=15, help="Máximo de palabras por respuesta."
    )
    parser.add_argument(
        "--round-timeout",
        type=float,
        default=20.0,
        help="Ventana de cada ronda en segundos.",
    )
    return parser.parse_args(arguments)


def _run_server(options: argparse.Namespace) -> None:
    """Wiring real: gRPC al engine R1, timer y servidor en primer plano."""
    address = os.environ.get("SOSPECHAI_ENGINE_ADDR", "impostor-engine:50051")
    channel = grpc.insecure_channel(address, options=[("grpc.enable_retries", 0)])
    config = ServerConfig(model_id=options.model_id, provider=options.provider)

    def factory() -> Game:
        """Construir partidas con la configuración pedida en consola."""
        return Game(
            rounds=options.rounds,
            max_words=options.max_words,
            round_timeout=options.round_timeout,
        )

    server = GameServer(
        (options.host, options.port),
        SessionStore(),
        EngineClient(rpc.ImpostorEngineStub(channel)),
        config=config,
        game_factory=factory,
    )
    server.start_timer()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop_timer()
        server.server_close()
        channel.close()


def main() -> int:
    """Ejecutar el servidor real hasta que se interrumpa la consola."""
    _run_server(_parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
