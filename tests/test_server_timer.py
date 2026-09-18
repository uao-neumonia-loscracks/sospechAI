"""Timer del servidor, turno de la IA y concurrencia (fase 3).

Levanta el ``GameServer`` real con inyección de reloj, doble de engine que
registra intentos y peticiones, y timer opcional con tick pequeño. Nunca toca
Hugging Face: el doble devuelve streams locales o errores gRPC simulados.
"""

import http.client
import json
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import grpc
import pytest

from proto import impostor_pb2 as pb
from src.orchestrator.engine_client import EngineClient
from src.orchestrator.game import Game, GameState
from src.orchestrator.server import DEFAULT_PROMPTS, GameServer, ServerConfig
from src.orchestrator.session import SessionStore

MODEL_ID = "test/model:provider"


class RemoteError(grpc.RpcError):
    """Simular un estado gRPC sin depender de Hugging Face."""

    def __init__(self, status: grpc.StatusCode) -> None:
        """Guardar el estado remoto y un detalle que no debe mostrarse."""
        self.status = status
        super().__init__("private-provider-message")

    def code(self) -> grpc.StatusCode:
        """Ofrecer la misma consulta de estado que RpcError."""
        return self.status


@dataclass
class RecordingStub:
    """Doble del engine que registra intentos, presupuesto y petición."""

    chunks: list[pb.UtteranceChunk] = field(default_factory=list)
    error: grpc.RpcError | None = None
    calls: int = 0
    timeout: float | None = None
    request: pb.UtteranceRequest | None = None

    def GenerateUtterance(
        self, request: pb.UtteranceRequest, *, timeout: float
    ) -> Iterator[pb.UtteranceChunk]:
        """Registrar la llamada y devolver el stream preparado (nuevo por turno)."""
        self.calls += 1
        self.timeout = timeout
        self.request = request
        if self.error is not None:
            raise self.error
        return iter(self.chunks)


def chunks(text: str = "Un café.") -> list[pb.UtteranceChunk]:
    """Construir una respuesta válida y su cierre final explícito."""
    return [pb.UtteranceChunk(text_delta=text), pb.UtteranceChunk(is_final=True)]


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


@contextmanager
def serve(
    *,
    stub: RecordingStub | None = None,
    game_factory: Any = None,
    timer: bool = False,
    timer_tick: float = 0.01,
    prompts: tuple[str, ...] | None = None,
) -> Iterator[tuple[Api, SessionStore, RecordingStub]]:
    """Abrir un GameServer real con timer opcional y devolver el doble del engine."""
    store = SessionStore()
    recording = stub or RecordingStub(chunks=chunks())
    factory = game_factory or (lambda: Game(rounds=1, round_timeout=None))
    server = GameServer(
        ("127.0.0.1", 0),
        store,
        EngineClient(recording),
        prompts=prompts or DEFAULT_PROMPTS,
        config=ServerConfig(model_id=MODEL_ID),
        game_factory=factory,
        timer_tick=timer_tick,
    )
    if timer:
        server.start_timer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    try:
        yield Api(conn), store, recording
    finally:
        conn.close()
        server.stop_timer()
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()


def wait_until(predicate: Callable[[], bool], *, timeout: float) -> bool:
    """Esperar hasta que la condición se cumpla; tolerante al tick del timer."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def open_room(api: Api) -> tuple[str, str, str]:
    """Crear una sala: (room_code, token_host, alias_host)."""
    status, _, body = api.send("POST", "/rooms")
    assert status == 201
    return body["room_code"], body["session_token"], body["alias"]


def join_room(api: Api, code: str) -> tuple[str, str]:
    """Unir un humano a la sala: (token, alias)."""
    status, _, body = api.send("POST", f"/rooms/{code}/join")
    assert status == 201
    return body["session_token"], body["alias"]


def start_room(api: Api, code: str, host: str) -> None:
    """Abrir la partida como anfitrión."""
    status, _, body = api.send("POST", f"/rooms/{code}/start", token=host)
    assert (status, body) == (204, None)


def submit(api: Api, code: str, token: str, text: str) -> None:
    """Enviar el mensaje de un humano."""
    assert_204(
        api.send("POST", f"/rooms/{code}/messages", payload={"text": text}, token=token)
    )


def state(api: Api, code: str, token: str) -> dict:
    """Leer el estado vigente de la sala."""
    status, _, body = api.send("GET", f"/rooms/{code}/state", token=token)
    assert status == 200
    assert isinstance(body, dict)
    return body


def assert_204(result: tuple[int, dict[str, str], Any]) -> None:
    """Exigir 204, sin Content-Type y sin cuerpo interpretado."""
    status, headers, body = result
    assert (status, headers.get("Content-Type"), body) == (204, None, None)


def reach_votacion(api: Api, code: str, host: str, token2: str) -> None:
    """Llegar a VOTACION: dos humanos, turno de IA automático y apertura."""
    submit(api, code, host, "primera respuesta")
    submit(api, code, token2, "segunda respuesta")
    assert_204(api.send("POST", f"/rooms/{code}/voting/open", token=host))


# ---------------------------------------------------------------------------
# Timer del servidor
# ---------------------------------------------------------------------------


def test_timer_fires_with_zero_client_queries() -> None:
    """El timer vence la ronda sin ninguna petición de cliente entre medio."""

    def factory() -> Game:
        return Game(rounds=1, max_words=15, round_timeout=0.05)

    with serve(timer=True, timer_tick=0.01, game_factory=factory) as (api, store, _):
        code, host, _ = open_room(api)
        join_room(api, code)
        start_room(api, code, host)
        assert wait_until(
            lambda: store.room(code).game.state == GameState.REVEAL, timeout=2.0
        )
        snapshot = state(api, code, host)
        assert snapshot["state"] == "REVELACION"
        assert snapshot["result"]["interruption_reason"] == "quorum_lost"
        assert snapshot["result"]["valid_game"] is False
        assert snapshot["result"]["transcript"] == []


def test_timer_leaves_lobby_and_alive_windows_untouched() -> None:
    """check_expiration() no hace nada en LOBBY ni en una ventana viva."""
    with serve(timer=True, timer_tick=0.01) as (api, store, _):
        code, host, _ = open_room(api)
        join_room(api, code)
        time.sleep(0.12)
        assert store.room(code).game.state == GameState.LOBBY
        start_room(api, code, host)
        time.sleep(0.12)
        assert store.room(code).game.state == GameState.ROUND


def test_votacion_never_auto_advances() -> None:
    """Una partida en VOTACION no tiene deadline: las ticks no la mueven."""
    with serve(timer=True, timer_tick=0.01) as (api, store, _):
        code, host, _ = open_room(api)
        token2, _ = join_room(api, code)
        start_room(api, code, host)
        reach_votacion(api, code, host, token2)
        assert store.room(code).game.state == GameState.VOTING
        time.sleep(0.12)
        assert store.room(code).game.state == GameState.VOTING


# ---------------------------------------------------------------------------
# Concurrencia
# ---------------------------------------------------------------------------


def test_two_concurrent_votes_produce_single_reveal() -> None:
    """Dos votos simultáneos revelan una sola vez, sin errores duplicados."""
    with serve() as (api, store, _):
        code, host, _ = open_room(api)
        token2, _ = join_room(api, code)
        token3, _ = join_room(api, code)
        start_room(api, code, host)
        submit(api, code, host, "primera respuesta")
        submit(api, code, token2, "segunda respuesta")
        submit(api, code, token3, "tercera respuesta")
        assert_204(api.send("POST", f"/rooms/{code}/voting/open", token=host))
        assert_204(
            api.send(
                "POST",
                f"/rooms/{code}/votes",
                payload={"suspect": "Jugador 1"},
                token=token3,
            )
        )
        assert store.room(code).game.state == GameState.VOTING
        results: list[tuple[int, dict[str, str], Any]] = []
        barrier = threading.Barrier(2)

        def vote(conn: http.client.HTTPConnection, token: str, suspect: str) -> None:
            """Votar en un hilo propio con su conexión dedicada."""
            barrier.wait()
            results.append(
                Api(conn).send(
                    "POST",
                    f"/rooms/{code}/votes",
                    payload={"suspect": suspect},
                    token=token,
                )
            )

        conn_a = http.client.HTTPConnection("127.0.0.1", api.conn.port, timeout=10)
        conn_b = http.client.HTTPConnection("127.0.0.1", api.conn.port, timeout=10)
        first = threading.Thread(target=vote, args=(conn_a, host, "Jugador 3"))
        second = threading.Thread(target=vote, args=(conn_b, token2, "Jugador 3"))
        first.start()
        second.start()
        first.join(timeout=10)
        second.join(timeout=10)
        conn_a.close()
        conn_b.close()
        assert sorted(status for status, _, _ in results) == [204, 204]
        snapshot = state(api, code, host)
        assert snapshot["state"] == "REVELACION"
        assert snapshot["votes_received"] == 3
        assert snapshot["result"]["valid_game"] is True


def test_concurrent_messages_serialize_with_state_reads() -> None:
    """Mensajes simultáneos producen un estado consistente, sin mutaciones parciales."""
    with serve() as (api, store, _):
        code, host, _ = open_room(api)
        token2, _ = join_room(api, code)
        start_room(api, code, host)
        observed: list[set[str]] = []
        barrier = threading.Barrier(2)
        published = ["primera respuesta", "segunda respuesta"]

        def send_message(
            conn: http.client.HTTPConnection, token: str, text: str
        ) -> None:
            """Enviar un mensaje en su propio hilo y conexión."""
            barrier.wait()
            status, _, body = Api(conn).send(
                "POST", f"/rooms/{code}/messages", payload={"text": text}, token=token
            )
            assert (status, body) == (204, None)

        def read_states() -> None:
            """Sondear el estado mientras se escriben los mensajes."""
            reader = Api(
                http.client.HTTPConnection("127.0.0.1", api.conn.port, timeout=10)
            )
            for _ in range(15):
                snapshot = state(reader, code, host)
                observed.append({m["text"] for m in snapshot["messages"]})
            reader.conn.close()

        conn_a = http.client.HTTPConnection("127.0.0.1", api.conn.port, timeout=10)
        conn_b = http.client.HTTPConnection("127.0.0.1", api.conn.port, timeout=10)
        threads = [
            threading.Thread(target=send_message, args=(conn_a, host, published[0])),
            threading.Thread(target=send_message, args=(conn_b, token2, published[1])),
            threading.Thread(target=read_states),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        conn_a.close()
        conn_b.close()
        final = state(api, code, host)
        final_texts = {m["text"] for m in final["messages"]}
        assert "primera respuesta" in final_texts and "segunda respuesta" in final_texts
        assert final["state"] in {"RONDA", "DISCUSION", "REVELACION"}
        for read in observed:
            assert read <= final_texts


# ---------------------------------------------------------------------------
# Turno de la IA
# ---------------------------------------------------------------------------


def test_last_human_message_triggers_one_ai_turn() -> None:
    """El último mensaje humano dispara exactamente un turno de IA con su petición."""
    with serve(prompts=("pregunta uno", "pregunta dos")) as (api, _, stub):
        code, host, _ = open_room(api)
        token2, _ = join_room(api, code)
        start_room(api, code, host)
        submit(api, code, host, "primera respuesta")
        assert stub.calls == 0
        submit(api, code, token2, "segunda respuesta")
        assert stub.calls == 1
        assert stub.timeout == pytest.approx(8.0)
        assert stub.request is not None
        assert stub.request.room_id == code
        assert stub.request.persona_id == "p1"
        assert stub.request.prompt == "pregunta uno"
        assert stub.request.config.engine_backend == "hf-router"
        assert stub.request.config.model_id == MODEL_ID
        assert stub.request.config.max_words == 15
        assert stub.request.config.temperature == pytest.approx(0.9)
        assert stub.request.config.top_p == pytest.approx(0.9)
        snapshot = state(api, code, host)
        assert snapshot["state"] == "DISCUSION"
        assert [m["text"] for m in snapshot["messages"]] == [
            "primera respuesta",
            "segunda respuesta",
            "Un café.",
        ]
        assert snapshot["messages"][-1]["alias"] == "Jugador 3"


def test_one_ai_turn_per_round_with_two_rounds() -> None:
    """En dos rondas la IA responde una vez por ronda con su prompt propio."""

    def factory() -> Game:
        return Game(rounds=2, max_words=15, round_timeout=None)

    with serve(game_factory=factory, prompts=("pregunta uno", "pregunta dos")) as (
        api,
        _,
        stub,
    ):
        code, host, _ = open_room(api)
        token2, _ = join_room(api, code)
        start_room(api, code, host)
        submit(api, code, host, "ronda uno")
        submit(api, code, token2, "ronda uno")
        assert stub.calls == 1
        assert stub.request is not None and stub.request.prompt == "pregunta uno"
        snapshot = state(api, code, host)
        assert snapshot["state"] == "RONDA" and snapshot["round_number"] == 2
        submit(api, code, host, "ronda dos")
        submit(api, code, token2, "ronda dos")
        assert stub.calls == 2
        assert stub.request is not None and stub.request.prompt == "pregunta dos"
        snapshot = state(api, code, host)
        assert snapshot["state"] == "DISCUSION"
        assert len(snapshot["messages"]) == 6
        assert "result" not in snapshot  # result solo existe en REVELACION


def test_engine_failure_interrupts_without_retry() -> None:
    """Un fallo del engine revela con engine_unavailable y no reintenta."""
    stub = RecordingStub(error=RemoteError(grpc.StatusCode.UNAVAILABLE))
    with serve(stub=stub) as (api, _, _):
        code, host, _ = open_room(api)
        token2, _ = join_room(api, code)
        start_room(api, code, host)
        submit(api, code, host, "primera respuesta")
        submit(api, code, token2, "segunda respuesta")
        assert stub.calls == 1
        snapshot = state(api, code, host)
        assert snapshot["state"] == "REVELACION"
        result = snapshot["result"]
        assert result["interruption_reason"] == "engine_unavailable"
        assert result["valid_game"] is False
        assert [m["text"] for m in result["transcript"]] == [
            "primera respuesta",
            "segunda respuesta",
        ]
        assert "Un café." not in [m["text"] for m in result["transcript"]]


@pytest.mark.parametrize(
    "stub,reason",
    [
        (
            RecordingStub(error=RemoteError(grpc.StatusCode.DEADLINE_EXCEEDED)),
            "engine_timeout",
        ),
        (
            RecordingStub(error=RemoteError(grpc.StatusCode.UNAVAILABLE)),
            "engine_unavailable",
        ),
        (
            RecordingStub(error=RemoteError(grpc.StatusCode.RESOURCE_EXHAUSTED)),
            "engine_rejected",
        ),
        (RecordingStub(chunks=[pb.UtteranceChunk(is_final=True)]), "engine_protocol"),
        (RecordingStub(chunks=chunks("palabra " * 16)), "invalid_engine_response"),
    ],
)
def test_engine_outcomes_map_to_interruption_reason(
    stub: RecordingStub, reason: str
) -> None:
    """Cada salida del engine llega como interruption_reason, nunca como HTTP error."""
    with serve(stub=stub) as (api, _, _):
        code, host, _ = open_room(api)
        token2, _ = join_room(api, code)
        start_room(api, code, host)
        submit(api, code, host, "primera respuesta")
        submit(api, code, token2, "segunda respuesta")
        assert stub.calls == 1
        snapshot = state(api, code, host)
        assert snapshot["state"] == "REVELACION"
        assert snapshot["result"]["interruption_reason"] == reason
        assert snapshot["result"]["valid_game"] is False


def test_ai_has_no_token_and_cannot_vote() -> None:
    """La IA no recibe token: ningún endpoint puede actuar en su nombre."""
    with serve() as (api, store, _):
        code, host, _ = open_room(api)
        join_room(api, code)
        start_room(api, code, host)
        room = store.room(code)
        assert room is not None
        assert "Jugador 3" not in room.players.values()
        assert "Jugador 3" not in room.players
        status, _, body = api.send(
            "POST",
            f"/rooms/{code}/votes",
            payload={"suspect": "Jugador 2"},
            token="Jugador 3",
        )
        assert (status, body["code"]) == (401, "session_expired")


def test_timer_reveal_logs_game_once_without_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El vencimiento por timer registra la partida una vez, sin uso del engine."""
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "src.orchestrator.server.log_game_run",
        lambda **kwargs: calls.append(kwargs),
    )

    def factory() -> Game:
        return Game(rounds=1, max_words=15, round_timeout=0.05)

    with serve(timer=True, timer_tick=0.01, game_factory=factory) as (api, store, _):
        code, host, _ = open_room(api)
        join_room(api, code)
        start_room(api, code, host)
        assert wait_until(
            lambda: store.room(code).game.state == GameState.REVEAL, timeout=2.0
        )
        snapshot = state(api, code, host)
        assert snapshot["state"] == "REVELACION"
    assert len(calls) == 1
    assert calls[0]["usage"] is None
    assert calls[0]["result"]["interruption_reason"] == "round_timeout"
    assert calls[0]["params"].n_players == 3
