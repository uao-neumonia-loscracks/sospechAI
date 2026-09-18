"""Servidor HTTP de loopback: enrutado, identidad, catálogo y formas espejo.

Levanta el GameServer real en un puerto efímero (mismo patrón que
``tests/test_engine_integration.py``) y consume el contrato con
``http.client`` sobre sockets locales: sin red externa, sin timer y sin
invocar al motor de inferencia en esta fase (el FakeStub falla si se usa).
"""

import http.client
import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import pytest

from proto import impostor_pb2 as pb
from src.orchestrator.engine_client import EngineClient
from src.orchestrator.game import Game
from src.orchestrator.server import GameServer, ServerConfig, parse_route
from src.orchestrator.session import SessionStore
from src.orchestrator.tracking import EngineUsage

SECRET_MARKERS = (
    b"is_ai",
    b"impostor_alias",
    b"vote_counts",
    b'"votes"',
    b"scores",
    b"tasa_deteccion",
)


class Stub:
    """Doble benigno del engine: responde una frase corta y cuenta llamadas."""

    id = "test-model"

    def __init__(self) -> None:
        """Comenzar sin llamadas registradas."""
        self.calls = 0

    def GenerateUtterance(self, request: Any, *, timeout: float) -> Iterator:
        """Devolver un stream local válido para el turno del impostor."""
        self.calls += 1
        yield pb.UtteranceChunk(text_delta="Un café.")
        yield pb.UtteranceChunk(is_final=True)


MODEL_ID = "test/model:provider"

USAGE_METADATA = [
    ("x-usage-prompt-tokens", "120"),
    ("x-usage-completion-tokens", "45"),
    ("x-latency-total-ms", "123.4"),
    ("x-attempts", "1"),
    ("x-character-break", "0"),
    ("x-model-id", MODEL_ID),
]


class MetadataCall:
    """Llamada gRPC simulada con trailing metadata del contrato de uso."""

    def __init__(self, metadata: list[tuple[str, str]]) -> None:
        """Guardar los pares que el engine reportaría al cerrar el stream."""
        self.metadata = metadata

    def __iter__(self) -> Iterator[pb.UtteranceChunk]:
        """Entregar una respuesta válida y su cierre final explícito."""
        yield pb.UtteranceChunk(text_delta="Un café.")
        yield pb.UtteranceChunk(is_final=True)

    def trailing_metadata(self) -> list[tuple[str, str]]:
        """Devolver la metadata configurada para esta llamada."""
        return self.metadata

    def cancel(self) -> None:
        """No hay recursos que liberar en este doble."""


class MetadataStub:
    """Doble del engine que reporta trailing metadata en cada turno de IA."""

    def __init__(self, metadata: list[tuple[str, str]] = USAGE_METADATA) -> None:
        """Guardar la metadata que devolverá cada llamada de generación."""
        self.metadata = metadata
        self.calls = 0

    def GenerateUtterance(self, request: Any, *, timeout: float) -> MetadataCall:
        """Registrar la llamada y devolver un stream con metadata."""
        self.calls += 1
        return MetadataCall(self.metadata)


@dataclass
class Api:
    """Cliente mínimo sobre http.client para las pruebas del contrato."""

    conn: http.client.HTTPConnection

    def send(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        token: str | None = None,
    ) -> tuple[int, dict[str, str], Any]:
        """Enviar una petición y devolver (status, cabeceras, cuerpo JSON o None)."""
        headers: dict[str, str] = {}
        body = None
        if token is not None:
            headers["X-Session-Token"] = token
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            headers["Content-Type"] = "application/json"
        self.conn.request(method, path, body=body, headers=headers)
        response = self.conn.getresponse()
        raw = response.read()
        parsed = json.loads(raw) if raw else None
        return response.status, dict(response.getheaders()), parsed

    def raw(
        self, method: str, path: str, *, token: str | None = None
    ) -> tuple[int, dict[str, str], bytes]:
        """Enviar una petición y devolver el cuerpo sin interpretar."""
        headers = {}
        if token is not None:
            headers["X-Session-Token"] = token
        self.conn.request(method, path, headers=headers)
        response = self.conn.getresponse()
        return response.status, dict(response.getheaders()), response.read()

    def send_raw(
        self,
        method: str,
        path: str,
        *,
        raw_body: bytes,
        token: str | None = None,
    ) -> tuple[int, dict[str, str], Any]:
        """Enviar un cuerpo crudo (p. ej. JSON malformado) y devolver la respuesta."""
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["X-Session-Token"] = token
        self.conn.request(method, path, body=raw_body, headers=headers)
        response = self.conn.getresponse()
        raw = response.read()
        parsed = json.loads(raw) if raw else None
        return response.status, dict(response.getheaders()), parsed


@contextmanager
def serve(
    store: SessionStore | None = None,
    *,
    game_factory: Any = None,
    client: Any = None,
    clock: Any = time.monotonic,
    config: ServerConfig | None = None,
) -> Iterator[tuple[Api, SessionStore]]:
    """Abrir un GameServer real en loopback con puerto efímero y cerrarlo."""
    store = store or SessionStore()
    factory = game_factory or (lambda: Game(rounds=1, round_timeout=None, clock=clock))
    server = GameServer(
        ("127.0.0.1", 0),
        store,
        client or EngineClient(Stub()),
        config=config or ServerConfig(model_id=MODEL_ID),
        game_factory=factory,
        clock=clock,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    try:
        yield Api(conn), store
    finally:
        conn.close()
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()


def open_room(api: Api) -> tuple[str, str, str]:
    """Crear una sala: (room_code, token_host, alias_host)."""
    status, headers, body = api.send("POST", "/rooms")
    assert status == 201
    assert headers.get("Content-Type") == "application/json"
    return body["room_code"], body["session_token"], body["alias"]


def join_room(api: Api, code: str) -> tuple[str, str]:
    """Unirse a una sala: (token, alias)."""
    status, _, body = api.send("POST", f"/rooms/{code}/join")
    assert status == 201
    return body["session_token"], body["alias"]


def start_room(api: Api, code: str, host_token: str) -> None:
    """Iniciar la partida como anfitrión y exigir 204."""
    assert api.send("POST", f"/rooms/{code}/start", token=host_token)[0] == 204


def submit(
    api: Api, code: str, token: str, text: str
) -> tuple[int, dict[str, str], Any]:
    """Enviar un mensaje de ronda."""
    return api.send(
        "POST", f"/rooms/{code}/messages", payload={"text": text}, token=token
    )


def state(api: Api, code: str, token: str) -> dict[str, Any]:
    """Leer la instantánea del contrato y exigir 200."""
    status, _, body = api.send("GET", f"/rooms/{code}/state", token=token)
    assert status == 200
    return body


def assert_secrets_absent(headers: dict[str, str], raw: bytes) -> None:
    """Verificar que cabeceras y cuerpo no revelan campos ocultos."""
    joined = " ".join(f"{key} {value}".lower() for key, value in headers.items())
    for marker in SECRET_MARKERS:
        assert marker not in raw
        assert marker.decode() not in joined


def _reach_discusion(api: Api, code: str, host: str, token2: str) -> None:
    """Completar la única ronda: humanos por HTTP y turno de IA del servidor."""
    assert submit(api, code, host, "primera respuesta")[0] == 204
    assert submit(api, code, token2, "segunda respuesta")[0] == 204
    assert state(api, code, host)["state"] == "DISCUSION"


def _reach_votacion(api: Api, code: str, host: str, token2: str) -> None:
    """Alcanzar VOTACION abriendo la votación tras la discusión."""
    _reach_discusion(api, code, host, token2)
    assert api.send("POST", f"/rooms/{code}/voting/open", token=host)[0] == 204
    assert state(api, code, host)["state"] == "VOTACION"


# ---------------------------------------------------------------------------
# Enrutado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/rooms", ("create", None)),
        ("/rooms/K7Q2P/join", ("join", "K7Q2P")),
        ("/rooms/K7Q2P/start", ("start", "K7Q2P")),
        ("/rooms/K7Q2P/messages", ("messages", "K7Q2P")),
        ("/rooms/K7Q2P/voting/open", ("open_voting", "K7Q2P")),
        ("/rooms/K7Q2P/votes", ("votes", "K7Q2P")),
        ("/rooms/K7Q2P/state", ("state", "K7Q2P")),
        ("/rooms/K7Q2P/state?poll=1", ("state", "K7Q2P")),
        ("/rooms/abc12/join", ("join", "abc12")),
        ("/rooms/K7Q2P", None),
        ("/rooms/K7Q2P/foo", None),
        ("/rooms/K7Q2P/voting/close", None),
        ("/rooms/K7Q2P/votes/extra", None),
        ("/rooms/K7Q2P/voting/open/extra", None),
        ("/", None),
        ("/health", None),
    ],
)
def test_parse_route_table(path: str, expected: tuple[str, str | None] | None) -> None:
    """El parser de rutas cubre los siete endpoints y los fallbacks."""
    assert parse_route(path) == expected


def test_unknown_path_is_404_and_wrong_verb_is_405() -> None:
    """Ruta desconocida → not_found; verbo incorrecto en ruta conocida → 405."""
    with serve() as (api, store):
        code, host, _ = open_room(api)
        status, _, body = api.send("POST", "/rooms/nope-state")  # forma fuera de rutas
        assert (status, body["code"]) == (404, "not_found")
        assert body["message"] == "Ruta desconocida."
        status, _, body = api.send("POST", f"/rooms/{code}/foo")
        assert (status, body["code"]) == (404, "not_found")
        status, _, body = api.send("GET", "/rooms")
        assert (status, body["code"]) == (405, "method_not_allowed")
        assert body["message"] == "Método no permitido para esta ruta."
        status, _, body = api.send("POST", f"/rooms/{code}/state")
        assert (status, body["code"]) == (405, "method_not_allowed")
        status, _, body = api.send("GET", f"/rooms/{code}/votes")
        assert (status, body["code"]) == (405, "method_not_allowed")


# ---------------------------------------------------------------------------
# Creación, unión y estatus de mutación
# ---------------------------------------------------------------------------


def test_create_and_join_issue_identity_with_room_code() -> None:
    """Crear y unirse emiten 201 con room_code, session_token y alias."""
    with serve() as (api, store):
        code, host, alias = open_room(api)
        assert alias == "Jugador 1"
        assert len(code) == 5
        status, headers, body = api.send("POST", f"/rooms/{code}/join")
        assert status == 201
        assert headers.get("Content-Type") == "application/json"
        assert body["alias"] == "Jugador 2"
        assert body["room_code"] == code
        assert body["session_token"] != host


def test_join_accepts_lowercase_room_code() -> None:
    """La unión ignora mayúsculas y el código emitido permanece en mayúsculas."""
    with serve() as (api, store):
        code, host, _ = open_room(api)
        status, _, body = api.send("POST", f"/rooms/{code.lower()}/join")
        assert status == 201
        assert body["room_code"] == code
        assert body["session_token"] != host


def assert_204(result: tuple[int, dict[str, str], Any]) -> None:
    """Exigir 204, sin Content-Type y sin cuerpo interpretado."""
    status, headers, body = result
    assert (status, headers.get("Content-Type"), body) == (204, None, None)


def test_mutations_return_204_without_content_type() -> None:
    """Las mutaciones responden 204 con cuerpo vacío y sin Content-Type."""
    with serve() as (api, store):
        code, host, _ = open_room(api)
        token2, _ = join_room(api, code)
        assert_204(api.send("POST", f"/rooms/{code}/start", token=host))
        assert_204(submit(api, code, host, "hola"))
        assert_204(submit(api, code, token2, "mundo"))
        assert_204(api.send("POST", f"/rooms/{code}/voting/open", token=host))
        assert_204(
            api.send(
                "POST",
                f"/rooms/{code}/votes",
                payload={"suspect": "Jugador 3"},
                token=host,
            )
        )


def test_malformed_body_is_400_malformed_request() -> None:
    """JSON inválido, ausente o con tipos incorrectos → malformed_request."""
    with serve() as (api, store):
        code, host, _ = open_room(api)
        expected = (400, "malformed_request", "Cuerpo JSON inválido o ausente.")
        status, _, body = api.send_raw(
            "POST", f"/rooms/{code}/messages", raw_body=b"no json", token=host
        )
        assert (status, body["code"], body["message"]) == expected
        status, _, body = api.send("POST", f"/rooms/{code}/messages", token=host)
        assert (status, body["code"], body["message"]) == expected
        status, _, body = api.send(
            "POST", f"/rooms/{code}/messages", payload={"text": 42}, token=host
        )
        assert (status, body["code"], body["message"]) == expected
        status, _, body = api.send(
            "POST", f"/rooms/{code}/votes", payload={"suspect": 42}, token=host
        )
        assert (status, body["code"], body["message"]) == expected


# ---------------------------------------------------------------------------
# Identidad y precedencia
# ---------------------------------------------------------------------------


def test_room_token_membership_precedence() -> None:
    """Precedencia 404 → 401 → 403 sobre el mismo endpoint autenticado."""
    with serve() as (api, store):
        code_a, host_a, _ = open_room(api)
        code_b, host_b, _ = open_room(api)
        # sala inexistente: 404 incluso con token
        status, _, body = api.send("GET", "/rooms/NOPE1/state", token=host_a)
        assert body["code"] == "room_not_found" and status == 404
        assert body["message"] == "Sala no encontrada."
        # sala conocida, token ausente: 401
        status, _, body = api.send("GET", f"/rooms/{code_a}/state")
        assert body["code"] == "session_expired" and status == 401
        assert body["message"] == "Token ausente, desconocido o de una sala reclamada."
        # sala conocida, token desconocido: 401
        status, _, body = api.send(
            "GET", f"/rooms/{code_a}/state", token="token-inexistente"
        )
        assert body["code"] == "session_expired" and status == 401
        # token válido de otra sala: 403
        status, _, body = api.send("GET", f"/rooms/{code_a}/state", token=host_b)
        assert body["code"] == "not_a_player" and status == 403
        assert body["message"] == "El token no pertenece a un jugador de esta sala."
        # la misma precedencia aplica en una mutación
        status, _, body = api.send("POST", f"/rooms/{code_a}/start", token=host_b)
        assert body["code"] == "not_a_player" and status == 403


def test_forged_alias_and_round_are_ignored() -> None:
    """Alias y round falsificados se ignoran: el servidor enlaza desde el token."""
    with serve() as (api, store):
        code, host, _ = open_room(api)
        join_room(api, code)
        start_room(api, code, host)
        status, _, body = api.send(
            "POST",
            f"/rooms/{code}/messages",
            payload={"text": "hola", "alias": "Jugador 2", "expected_round": 99},
            token=host,
        )
        assert status == 204
        snapshot = state(api, code, host)
        assert snapshot["messages"] == [
            {"round_number": 1, "alias": "Jugador 1", "text": "hola"}
        ]
        assert snapshot["round_number"] == 1


def test_non_host_start_and_open_voting_are_refused() -> None:
    """Acciones de anfitrión: 403 forbidden_host_action sin invocar el dominio."""
    with serve() as (api, store):
        code, host, _ = open_room(api)
        token2, _ = join_room(api, code)
        status, _, body = api.send("POST", f"/rooms/{code}/start", token=token2)
        assert (status, body["code"]) == (403, "forbidden_host_action")
        assert body["message"] == "Solo el anfitrión puede ejecutar esta acción."
        snapshot = state(api, code, host)
        assert snapshot["state"] == "LOBBY"
        assert snapshot["players"] == ["Jugador 1", "Jugador 2"]
        status, _, body = api.send("POST", f"/rooms/{code}/voting/open", token=token2)
        assert (status, body["code"]) == (403, "forbidden_host_action")
        assert state(api, code, host)["state"] == "LOBBY"


def test_join_after_lobby_is_refused() -> None:
    """Unirse fuera de LOBBY → 409 wrong_state con el mensaje del dominio."""
    with serve() as (api, store):
        code, host, _ = open_room(api)
        join_room(api, code)
        start_room(api, code, host)
        status, _, body = api.send("POST", f"/rooms/{code}/join")
        assert status == 409
        assert body["code"] == "wrong_state"
        assert (
            body["message"] == "Esta acción requiere LOBBY; la partida está en RONDA."
        )


def test_server_adds_one_ai_and_no_client_path_adds_another() -> None:
    """La IA se registra solo en start, siempre última; is_ai del cliente se ignora."""
    with serve() as (api, store):
        status, _, body = api.send("POST", "/rooms", payload={"is_ai": True})
        assert status == 201 and body["alias"] == "Jugador 1"
        code, host = body["room_code"], body["session_token"]
        status, _, body = api.send(
            "POST", f"/rooms/{code}/join", payload={"is_ai": True}
        )
        assert status == 201 and body["alias"] == "Jugador 2"
        token2 = body["session_token"]
        start_room(api, code, host)
        snapshot = state(api, code, host)
        assert snapshot["state"] == "RONDA"
        assert snapshot["players"] == ["Jugador 1", "Jugador 2", "Jugador 3"]
        assert submit(api, code, host, "hola")[0] == 204
        assert submit(api, code, token2, "mundo")[0] == 204
        assert api.send("POST", f"/rooms/{code}/voting/open", token=host)[0] == 204
        api.send(
            "POST", f"/rooms/{code}/votes", payload={"suspect": "Jugador 3"}, token=host
        )
        api.send(
            "POST",
            f"/rooms/{code}/votes",
            payload={"suspect": "Jugador 3"},
            token=token2,
        )
        snapshot = state(api, code, host)
        flags = [item["is_ai"] for item in snapshot["result"]["transcript"]]
        assert flags.count(True) == 1
        assert snapshot["result"]["impostor_alias"] == "Jugador 3"


# ---------------------------------------------------------------------------
# Formas espejo, valores congelados y privacidad
# ---------------------------------------------------------------------------


def test_full_lifecycle_frozen_wire_values_and_result() -> None:
    """LOBBY→RONDA→DISCUSION→VOTACION→REVELACION con valores congelados."""
    with serve() as (api, store):
        code, host, _ = open_room(api)
        token2, _ = join_room(api, code)
        assert state(api, code, host)["state"] == "LOBBY"
        start_room(api, code, host)
        snapshot = state(api, code, host)
        assert snapshot["state"] == "RONDA"
        assert snapshot["round_number"] == 1
        assert snapshot["players"] == ["Jugador 1", "Jugador 2", "Jugador 3"]
        assert snapshot["votes_received"] == 0
        assert "result" not in snapshot
        assert submit(api, code, host, "sospecho del tres")[0] == 204
        assert submit(api, code, token2, "yo tambien")[0] == 204
        snapshot = state(api, code, host)
        assert snapshot["state"] == "DISCUSION"
        assert "result" not in snapshot
        assert len(snapshot["messages"]) == 3
        assert api.send("POST", f"/rooms/{code}/voting/open", token=host)[0] == 204
        snapshot = state(api, code, host)
        assert snapshot["state"] == "VOTACION"
        assert snapshot["votes_received"] == 0
        assert "result" not in snapshot
        api.send(
            "POST", f"/rooms/{code}/votes", payload={"suspect": "Jugador 3"}, token=host
        )
        snapshot = state(api, code, host)
        assert snapshot["state"] == "VOTACION"
        assert snapshot["votes_received"] == 1
        assert "result" not in snapshot
        api.send(
            "POST",
            f"/rooms/{code}/votes",
            payload={"suspect": "Jugador 3"},
            token=token2,
        )
        snapshot = state(api, code, host)
        assert snapshot["state"] == "REVELACION"
        result = snapshot["result"]
        assert result["impostor_alias"] == "Jugador 3"
        assert result["valid_game"] is True
        assert result["votes"] == {"Jugador 1": "Jugador 3", "Jugador 2": "Jugador 3"}
        assert result["vote_counts"] == {"Jugador 3": 2}
        assert result["scores"] == {"Jugador 1": 1, "Jugador 2": 1}
        assert result["tasa_deteccion"] == 1.0
        assert snapshot == store.room(code).game.public_state()


def test_state_body_is_public_state_verbatim() -> None:
    """GET /state serializa public_state() sin remodelar, sin result previo."""
    with serve() as (api, store):
        code, host, _ = open_room(api)
        join_room(api, code)
        start_room(api, code, host)
        submit(api, code, host, "hola")
        game = store.room(code).game
        status, headers, raw = api.raw("GET", f"/rooms/{code}/state", token=host)
        assert status == 200
        assert headers.get("Content-Type") == "application/json"
        assert raw == json.dumps(game.public_state(), ensure_ascii=False).encode()
        parsed = json.loads(raw)
        assert parsed == game.public_state()
        assert "result" not in parsed


def test_privacy_probing_leaks_nothing_before_revelacion() -> None:
    """Ningún cuerpo ni cabecera revela is_ai/impostor/votos antes de REVELACION."""
    with serve() as (api, store):
        code, host, _ = open_room(api)
        token2, _ = join_room(api, code)
        start_room(api, code, host)
        status, headers, raw = api.raw("GET", f"/rooms/{code}/state", token=host)
        assert status == 200
        assert_secrets_absent(headers, raw)
        status, headers, raw = api.raw("GET", "/rooms")
        assert status == 405
        assert_secrets_absent(headers, raw)
        assert submit(api, code, host, "hola")[0] == 204
        assert submit(api, code, token2, "mundo")[0] == 204
        assert api.send("POST", f"/rooms/{code}/voting/open", token=host)[0] == 204
        assert (
            api.send(
                "POST",
                f"/rooms/{code}/votes",
                payload={"suspect": "Jugador 3"},
                token=host,
            )[0]
            == 204
        )
        status, headers, raw = api.raw("GET", f"/rooms/{code}/state", token=host)
        assert status == 200
        assert_secrets_absent(headers, raw)
        snapshot = json.loads(raw)
        assert snapshot["votes_received"] == 1
        assert isinstance(snapshot["votes_received"], int)
        assert "votes" not in snapshot
        assert "result" not in snapshot


def test_delivered_snapshot_is_immutable_to_later_mutations() -> None:
    """La copia defensiva entregada no cambia cuando el dominio muta después."""
    with serve() as (api, store):
        code, host, _ = open_room(api)
        token2, _ = join_room(api, code)
        start_room(api, code, host)
        submit(api, code, host, "hola")
        status, _, raw_before = api.raw("GET", f"/rooms/{code}/state", token=host)
        assert status == 200
        submit(api, code, token2, "mundo")
        status, _, raw_after = api.raw("GET", f"/rooms/{code}/state", token=token2)
        assert status == 200
        before = json.loads(raw_before)
        after = json.loads(raw_after)
        assert len(before["messages"]) == 1
        assert len(after["messages"]) == 3  # humanos + turno de IA
        assert raw_before != raw_after


def test_rejoin_mid_round_reads_current_snapshot() -> None:
    """Reconexión a mitad de ronda: mismo token relee la instantánea vigente."""
    with serve() as (api, store):
        code, host, _ = open_room(api)
        token2, _ = join_room(api, code)
        start_room(api, code, host)
        submit(api, code, host, "hola")
        first = state(api, code, host)
        assert first["state"] == "RONDA"
        assert len(first["messages"]) == 1
        submit(api, code, token2, "mundo")
        second = state(api, code, host)
        assert second["state"] == "DISCUSION"  # el turno de IA cierra la ronda
        assert len(second["messages"]) == 3
        assert first["messages"] != second["messages"]


# ---------------------------------------------------------------------------
# Catálogo de errores (tabla completa)
# ---------------------------------------------------------------------------


def _catalog_room(api: Api) -> tuple[str, str, str]:
    """Abrir una sala con dos humanos: (code, token_host, token2)."""
    code, host, _ = open_room(api)
    token2, _ = join_room(api, code)
    return code, host, token2


def _catalog_game(api: Api, code: str, host: str) -> None:
    """Iniciar la partida: RONDA con los dos humanos ya registrados."""
    start_room(api, code, host)


def catalog_empty_message(api: Api, store: SessionStore) -> tuple[int, str, str]:
    """Texto vacío tras normalización → 400 empty_message."""
    code, host, _ = _catalog_room(api)
    _catalog_game(api, code, host)
    status, _, body = submit(api, code, host, "   ")
    return status, body["code"], body["message"]


def catalog_too_many_words(api: Api, store: SessionStore) -> tuple[int, str, str]:
    """Más de max_words → 400 too_many_words."""
    code, host, _ = _catalog_room(api)
    _catalog_game(api, code, host)
    status, _, body = submit(
        api, code, host, " ".join(f"palabra{index}" for index in range(16))
    )
    return status, body["code"], body["message"]


def catalog_duplicate_message(api: Api, store: SessionStore) -> tuple[int, str, str]:
    """Segundo mensaje del mismo jugador en la misma ronda → 409."""
    code, host, _ = _catalog_room(api)
    _catalog_game(api, code, host)
    assert submit(api, code, host, "hola")[0] == 204
    status, _, body = submit(api, code, host, "otra vez")
    return status, body["code"], body["message"]


def catalog_self_vote(api: Api, store: SessionStore) -> tuple[int, str, str]:
    """Voto a uno mismo → 400 self_vote."""
    code, host, token2 = _catalog_room(api)
    _catalog_game(api, code, host)
    _reach_votacion(api, code, host, token2)
    status, _, body = api.send(
        "POST", f"/rooms/{code}/votes", payload={"suspect": "Jugador 1"}, token=host
    )
    return status, body["code"], body["message"]


def catalog_duplicate_vote(api: Api, store: SessionStore) -> tuple[int, str, str]:
    """Segundo voto del mismo humano → 409 duplicate_vote."""
    code, host, token2 = _catalog_room(api)
    _catalog_game(api, code, host)
    _reach_votacion(api, code, host, token2)
    assert (
        api.send(
            "POST", f"/rooms/{code}/votes", payload={"suspect": "Jugador 2"}, token=host
        )[0]
        == 204
    )
    status, _, body = api.send(
        "POST", f"/rooms/{code}/votes", payload={"suspect": "Jugador 3"}, token=host
    )
    return status, body["code"], body["message"]


def catalog_not_a_player_suspect(api: Api, store: SessionStore) -> tuple[int, str, str]:
    """Suspect fuera de la partida → 403 not_a_player."""
    code, host, token2 = _catalog_room(api)
    _catalog_game(api, code, host)
    _reach_votacion(api, code, host, token2)
    status, _, body = api.send(
        "POST",
        f"/rooms/{code}/votes",
        payload={"suspect": "Jugador Fantasma"},
        token=host,
    )
    return status, body["code"], body["message"]


def catalog_wrong_state_join(api: Api, store: SessionStore) -> tuple[int, str, str]:
    """Unirse fuera de LOBBY → 409 wrong_state."""
    code, host, _ = _catalog_room(api)
    _catalog_game(api, code, host)
    status, _, body = api.send("POST", f"/rooms/{code}/join")
    return status, body["code"], body["message"]


def catalog_wrong_state_start(api: Api, store: SessionStore) -> tuple[int, str, str]:
    """Iniciar fuera de LOBBY → 409 wrong_state."""
    code, host, _ = _catalog_room(api)
    _catalog_game(api, code, host)
    status, _, body = api.send("POST", f"/rooms/{code}/start", token=host)
    return status, body["code"], body["message"]


def catalog_wrong_state_messages(api: Api, store: SessionStore) -> tuple[int, str, str]:
    """Mensaje fuera de RONDA → 409 wrong_state."""
    code, host, _ = _catalog_room(api)
    status, _, body = submit(api, code, host, "hola")
    return status, body["code"], body["message"]


def catalog_wrong_state_open_voting(
    api: Api, store: SessionStore
) -> tuple[int, str, str]:
    """Voting/open fuera de DISCUSION → 409 wrong_state."""
    code, host, _ = _catalog_room(api)
    status, _, body = api.send("POST", f"/rooms/{code}/voting/open", token=host)
    return status, body["code"], body["message"]


def catalog_wrong_state_votes(api: Api, store: SessionStore) -> tuple[int, str, str]:
    """Voto fuera de VOTACION → 409 wrong_state."""
    code, host, token2 = _catalog_room(api)
    _catalog_game(api, code, host)
    _reach_discusion(api, code, host, token2)
    status, _, body = api.send(
        "POST", f"/rooms/{code}/votes", payload={"suspect": "Jugador 3"}, token=host
    )
    return status, body["code"], body["message"]


def catalog_invalid_roster(api: Api, store: SessionStore) -> tuple[int, str, str]:
    """start con un solo humano → 409 invalid_roster y la sala sigue en LOBBY."""
    code, host, _ = open_room(api)
    status, _, body = api.send("POST", f"/rooms/{code}/start", token=host)
    assert state(api, code, host)["state"] == "LOBBY"
    return status, body["code"], body["message"]


def _boom(*, game: Game) -> None:
    """Sustituir create() para provocar un fallo interno del servidor."""
    raise RuntimeError("fallo interno provocado")


def catalog_internal(api: Api, store: SessionStore) -> tuple[int, str, str]:
    """Excepción inesperada del servidor → 500 internal."""
    store.create = _boom
    status, _, body = api.send("POST", "/rooms")
    return status, body["code"], body["message"]


CATALOG = [
    (
        "empty_message",
        (400, "empty_message", "Escribe una respuesta que contenga texto."),
        catalog_empty_message,
    ),
    (
        "too_many_words",
        (400, "too_many_words", "La respuesta admite máximo 15 palabras."),
        catalog_too_many_words,
    ),
    (
        "duplicate_message",
        (409, "duplicate_message", "Ya enviaste una respuesta en esta ronda."),
        catalog_duplicate_message,
    ),
    (
        "self_vote",
        (400, "self_vote", "En estas reglas provisionales, no puedes votarte."),
        catalog_self_vote,
    ),
    (
        "duplicate_vote",
        (409, "duplicate_vote", "Ya registraste tu voto."),
        catalog_duplicate_vote,
    ),
    (
        "not_a_player_suspect",
        (403, "not_a_player", "Ese jugador no pertenece a la partida."),
        catalog_not_a_player_suspect,
    ),
    (
        "wrong_state_join",
        (409, "wrong_state", "Esta acción requiere LOBBY; la partida está en RONDA."),
        catalog_wrong_state_join,
    ),
    (
        "wrong_state_start",
        (409, "wrong_state", "Esta acción requiere LOBBY; la partida está en RONDA."),
        catalog_wrong_state_start,
    ),
    (
        "wrong_state_messages",
        (409, "wrong_state", "Esta acción requiere RONDA; la partida está en LOBBY."),
        catalog_wrong_state_messages,
    ),
    (
        "wrong_state_open_voting",
        (
            409,
            "wrong_state",
            "Esta acción requiere DISCUSION; la partida está en LOBBY.",
        ),
        catalog_wrong_state_open_voting,
    ),
    (
        "wrong_state_votes",
        (
            409,
            "wrong_state",
            "Esta acción requiere VOTACION; la partida está en DISCUSION.",
        ),
        catalog_wrong_state_votes,
    ),
    (
        "invalid_roster",
        (
            409,
            "invalid_roster",
            "Se necesitan al menos dos humanos y exactamente una IA.",
        ),
        catalog_invalid_roster,
    ),
    (
        "internal",
        (500, "internal", "Error interno del servidor."),
        catalog_internal,
    ),
]


@pytest.mark.parametrize("name,expected,act", CATALOG)
def test_error_catalog_rows(
    name: str, expected: tuple[int, str, str], act: Any
) -> None:
    """Cada fila del catálogo se provoca por HTTP: status, code y mensaje exactos."""
    with serve() as (api, store):
        assert act(api, store) == expected


# ---------------------------------------------------------------------------
# Cierre de partida y tracking (A13): log_game_run exactamente una vez
# ---------------------------------------------------------------------------


def _reveal(api: Api, code: str, host: str, token2: str) -> None:
    """Cerrar la votación con dos votos para llegar a REVELACION."""
    assert (
        api.send(
            "POST",
            f"/rooms/{code}/votes",
            payload={"suspect": "Jugador 3"},
            token=host,
        )[0]
        == 204
    )
    assert (
        api.send(
            "POST",
            f"/rooms/{code}/votes",
            payload={"suspect": "Jugador 3"},
            token=token2,
        )[0]
        == 204
    )


def test_revelacion_logs_game_run_once_with_accumulated_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La partida terminal genera un único run con el uso acumulado del engine."""
    calls: list[dict[str, object]] = []

    def fake_log_game_run(**kwargs: object) -> None:
        calls.append(kwargs)

    monkeypatch.setattr("src.orchestrator.server.log_game_run", fake_log_game_run)
    with serve(client=EngineClient(MetadataStub())) as (api, _):
        code, host, _ = open_room(api)
        token2, _ = join_room(api, code)
        start_room(api, code, host)
        _reach_votacion(api, code, host, token2)
        _reveal(api, code, host, token2)
        assert state(api, code, host)["state"] == "REVELACION"
        assert state(api, code, host)["state"] == "REVELACION"  # poll repetido
    assert len(calls) == 1
    params, result, usage = calls[0]["params"], calls[0]["result"], calls[0]["usage"]
    assert params.model_id == MODEL_ID
    assert params.engine_backend == "hf-router"
    assert params.provider == "featherless-ai"
    assert params.temperature == pytest.approx(0.9)
    assert params.top_p == pytest.approx(0.9)
    assert params.system_prompt_version == "v2"
    assert params.max_words == 15
    assert params.n_players == 3
    assert params.n_rondas == 1
    assert result["state"] == "REVELACION"
    assert result["valid_game"] is True
    assert usage == EngineUsage(
        prompt_tokens=120,
        completion_tokens=45,
        cached_tokens=0,
        latencies_ms=(123.4,),
        attempts=1,
        character_breaks=0,
        calls=1,
        model_id=MODEL_ID,
    )


def test_malformed_usage_metadata_logs_error_and_skips_usage(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Metadata malformada no contamina el run: log claro y usage omitido."""
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "src.orchestrator.server.log_game_run",
        lambda **kwargs: calls.append(kwargs),
    )
    malformed = [("x-usage-prompt-tokens", "no-entero"), ("x-model-id", MODEL_ID)]
    with serve(client=EngineClient(MetadataStub(metadata=malformed))) as (api, _):
        code, host, _ = open_room(api)
        token2, _ = join_room(api, code)
        start_room(api, code, host)
        _reach_votacion(api, code, host, token2)
        _reveal(api, code, host, token2)
        assert state(api, code, host)["state"] == "REVELACION"
    assert len(calls) == 1
    assert calls[0]["usage"] is None
    assert calls[0]["result"]["valid_game"] is True
    assert "Metadata de uso malformada" in caplog.text


def test_revelacion_usa_el_provider_de_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El proveedor registrado sale de ServerConfig, no de una constante."""
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "src.orchestrator.server.log_game_run",
        lambda **kwargs: calls.append(kwargs),
    )
    with serve(
        client=EngineClient(MetadataStub()),
        config=ServerConfig(model_id=MODEL_ID, provider="together"),
    ) as (api, _):
        code, host, _ = open_room(api)
        token2, _ = join_room(api, code)
        start_room(api, code, host)
        _reach_votacion(api, code, host, token2)
        _reveal(api, code, host, token2)
    assert len(calls) == 1
    assert calls[0]["params"].provider == "together"
