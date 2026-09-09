"""Riesgos de inferencia remota: deadlines, streams parciales y rechazo de turnos."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Event

import grpc
import pytest

from proto import impostor_pb2 as pb
from proto import impostor_pb2_grpc as rpc
from src.orchestrator.engine_client import EngineClient, EngineFailure, apply_ai_turn
from src.orchestrator.game import Game, RuleViolation


@dataclass
class Clock:
    """Reloj controlado que permite probar ventanas sin pausas reales."""

    now: float = 0.0

    def __call__(self) -> float:
        """Devolver el tiempo elegido por la prueba."""
        return self.now


class RemoteError(grpc.RpcError):
    """Simular un estado gRPC sin depender de Hugging Face."""

    def __init__(self, status: grpc.StatusCode) -> None:
        """Guardar el estado remoto y un detalle que no debe mostrarse."""
        self.status = status
        super().__init__("private-provider-message")

    def code(self) -> grpc.StatusCode:
        """Ofrecer la misma consulta de estado que RpcError."""
        return self.status


class FakeCall:
    """Stream controlado con cancelación verificable."""

    def __init__(self, chunks: list) -> None:
        """Preparar fragmentos o errores para una llamada."""
        self.chunks = iter(chunks)
        self.cancelled = False

    def __iter__(self) -> "FakeCall":
        """Permitir consumir el stream como una llamada de gRPC."""
        return self

    def __next__(self) -> pb.UtteranceChunk:
        """Entregar un fragmento o elevar un error en mitad de la respuesta."""
        item = next(self.chunks)
        if isinstance(item, grpc.RpcError):
            raise item
        return item

    def cancel(self) -> None:
        """Registrar la liberación de recursos de la llamada."""
        self.cancelled = True


class Stub:
    """Doble determinista que mide intentos y presupuesto enviado."""

    def __init__(self, chunks: list) -> None:
        """Definir la respuesta sin ninguna llamada HTTP."""
        self.call = FakeCall(chunks)
        self.calls = 0
        self.timeout: float | None = None
        self.request: pb.UtteranceRequest | None = None

    def GenerateUtterance(
        self, request: pb.UtteranceRequest, *, timeout: float
    ) -> FakeCall:
        """Registrar una petición y devolver el stream preparado."""
        self.calls += 1
        self.timeout = timeout
        self.request = request
        return self.call


def request() -> pb.UtteranceRequest:
    """Construir configuración explícita; el nombre es ficticio para estas pruebas."""
    return pb.UtteranceRequest(
        room_id="practice",
        prompt="¿Qué comiste?",
        config=pb.GenerationConfig(
            temperature=0.9,
            top_p=0.9,
            max_words=15,
            system_prompt_version="abc1234",
            engine_backend="hf-router",
            model_id="test/model:provider",
        ),
    )


def active_game(clock: Clock | None = None, rounds: int = 1) -> tuple[Game, list[str]]:
    """Abrir una partida con dos humanos y un impostor."""
    game = Game(rounds=rounds, clock=clock or Clock())
    aliases = [game.add_player(), game.add_player(), game.add_player(is_ai=True)]
    game.start()
    return game, aliases


def chunks(text: str = "Un café.") -> list[pb.UtteranceChunk]:
    """Construir una respuesta y un cierre vacío explícito."""
    return [pb.UtteranceChunk(text_delta=text), pb.UtteranceChunk(is_final=True)]


def test_complete_stream_preserves_request_and_has_one_attempt() -> None:
    """Los fragmentos se unen sin normalización duplicada ni reintentos ocultos."""
    stub = Stub(
        [
            pb.UtteranceChunk(text_delta="  café"),
            pb.UtteranceChunk(text_delta=" rico  "),
            pb.UtteranceChunk(is_final=True),
        ]
    )
    req = request()
    assert EngineClient(stub).generate(req, timeout=3) == "  café rico  "
    assert stub.request == req
    assert stub.calls == 1 and stub.timeout == 3 and stub.call.cancelled


@pytest.mark.parametrize(
    "stream",
    [
        [],
        [pb.UtteranceChunk(text_delta="parcial")],
        [pb.UtteranceChunk(is_final=True)],
        [pb.UtteranceChunk(text_delta="texto", is_final=True)],
        chunks() + [pb.UtteranceChunk(text_delta="extra")],
        chunks() + [pb.UtteranceChunk(is_final=True)],
        chunks("  "),
    ],
)
def test_malformed_stream_is_never_published(stream: list) -> None:
    """Un stream incompleto o ambiguo se descarta íntegramente."""
    stub = Stub(stream)
    with pytest.raises(EngineFailure, match="engine_protocol"):
        EngineClient(stub).generate(request(), timeout=1)
    assert stub.call.cancelled


def test_oversized_stream_is_cancelled() -> None:
    """El límite de memoria funciona incluso si el proveedor incumple el contrato."""
    stub = Stub(chunks("mucho texto"))
    with pytest.raises(EngineFailure):
        EngineClient(stub, max_chars=4).generate(request(), timeout=1)
    assert stub.call.cancelled


@pytest.mark.parametrize(
    "status,expected",
    [
        (grpc.StatusCode.DEADLINE_EXCEEDED, "engine_timeout"),
        (grpc.StatusCode.UNAVAILABLE, "engine_unavailable"),
        (grpc.StatusCode.RESOURCE_EXHAUSTED, "engine_rejected"),
        (grpc.StatusCode.FAILED_PRECONDITION, "engine_rejected"),
        (grpc.StatusCode.UNAUTHENTICATED, "engine_rejected"),
        (grpc.StatusCode.PERMISSION_DENIED, "engine_rejected"),
    ],
)
def test_remote_failure_discards_partial_output_without_retry(
    status: grpc.StatusCode, expected: str
) -> None:
    """Cada estado remoto llega como código seguro; no duplica el consumo de API."""
    stub = Stub([pb.UtteranceChunk(text_delta="parcial"), RemoteError(status)])
    with pytest.raises(EngineFailure) as captured:
        EngineClient(stub).generate(request(), timeout=1)
    assert str(captured.value) == expected
    assert stub.calls == 1 and stub.call.cancelled


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_deadline_cannot_start_an_rpc(timeout: float) -> None:
    """No se inicia una petición sin un presupuesto válido."""
    stub = Stub(chunks())
    with pytest.raises(ValueError):
        EngineClient(stub).generate(request(), timeout=timeout)
    assert stub.calls == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("engine_backend", "local-llamacpp"),
        ("model_id", ""),
        ("system_prompt_version", ""),
        ("max_words", 0),
        ("temperature", -1),
        ("temperature", float("nan")),
        ("top_p", 0),
        ("top_p", 1.1),
    ],
)
def test_invalid_configuration_is_rejected_before_network(
    field: str, value: object
) -> None:
    """La configuración errónea se rechaza antes de generar posibles cargos."""
    req = request()
    setattr(req.config, field, value)
    stub = Stub(chunks())
    with pytest.raises(ValueError):
        EngineClient(stub).generate(req, timeout=1)
    assert stub.calls == 0


@pytest.mark.parametrize("window", [0, -2, float("inf"), float("nan")])
def test_invalid_round_window_is_rejected(window: float) -> None:
    """Una ventana inválida no crea partidas que nunca vencen."""
    with pytest.raises(ValueError):
        Game(round_timeout=window)


@pytest.mark.parametrize("elapsed", [20, 21])
def test_expired_round_reveals_without_fabricating_a_detection_rate(
    elapsed: float,
) -> None:
    """El vencimiento exacto y tardío interrumpen y revelan la partida."""
    clock = Clock()
    game, aliases = active_game(clock)
    clock.now = elapsed
    with pytest.raises(RuleViolation):
        game.submit_message(aliases[0], "Respuesta tardía")
    result = game.result()
    assert result["impostor_alias"] == aliases[2]
    assert result["valid_game"] is False
    assert result["tasa_deteccion"] is None
    assert result["scores"] == {}
    assert result["interruption_reason"] == "round_timeout"


def test_round_window_resets_and_old_response_is_rejected() -> None:
    """La segunda ronda obtiene su ventana propia y rechaza un turno anterior."""
    clock = Clock()
    game, aliases = active_game(clock, rounds=2)
    clock.now = 19.9
    for alias in aliases:
        game.submit_message(alias, "Hola", expected_round=1)
    assert game.remaining_time() == pytest.approx(20)
    with pytest.raises(RuleViolation):
        game.submit_message(aliases[0], "Tarde", expected_round=1)
    assert len(game.public_state()["messages"]) == 3


def test_ai_turn_uses_remaining_window_and_the_shared_normalizer() -> None:
    """El presupuesto RPC nunca supera la ventana disponible."""
    clock = Clock()
    game, aliases = active_game(clock)
    clock.now = 18
    stub = Stub(chunks("  cafe\u0301   rico  "))
    assert apply_ai_turn(game, aliases[2], EngineClient(stub), request())
    assert stub.timeout == pytest.approx(2)
    assert game.public_state()["messages"][0]["text"] == "café rico"


def test_window_expiring_between_validation_and_rpc_does_not_call_engine() -> None:
    """El tiempo puede agotarse entre validar el turno y calcular el deadline."""
    ticks = iter([0.0, 19.99, 20.0])
    game = Game(clock=lambda: next(ticks))
    game.add_player()
    game.add_player()
    ai = game.add_player(is_ai=True)
    game.start()
    stub = Stub(chunks())
    assert not apply_ai_turn(game, ai, EngineClient(stub), request())
    assert stub.calls == 0
    assert game.result()["interruption_reason"] == "round_timeout"


def test_failed_ai_turn_reveals_and_never_inserts_partial_text() -> None:
    """La ausencia de API no se transforma en un voto incorrecto ni una respuesta falsa."""
    game, aliases = active_game()
    stub = Stub(
        [
            pb.UtteranceChunk(text_delta="parcial"),
            RemoteError(grpc.StatusCode.UNAVAILABLE),
        ]
    )
    assert not apply_ai_turn(game, aliases[2], EngineClient(stub), request())
    assert game.result()["transcript"] == []
    assert not game.result()["valid_game"]


def test_engine_over_word_limit_is_rejected_by_the_same_game_rule() -> None:
    """La guarda de R1 no sustituye la validación simétrica del controlador."""
    game, aliases = active_game()
    assert not apply_ai_turn(
        game, aliases[2], EngineClient(Stub(chunks("palabra " * 16))), request()
    )
    assert game.result()["interruption_reason"] == "invalid_engine_response"
    assert game.result()["transcript"] == []


def test_repeated_ai_turn_does_not_spend_a_second_request() -> None:
    """El controlador rechaza una repetición antes de iniciar otro RPC."""
    game, aliases = active_game()
    stub = Stub(chunks())
    client = EngineClient(stub)
    assert apply_ai_turn(game, aliases[2], client, request())
    with pytest.raises(RuleViolation):
        apply_ai_turn(game, aliases[2], client, request())
    assert stub.calls == 1


class TestEngine(rpc.ImpostorEngineServicer):
    """Servidor de prueba real por loopback; no realiza inferencia ni llamadas HTTP."""

    __test__ = False

    def GenerateUtterance(
        self, req: pb.UtteranceRequest, context: grpc.ServicerContext
    ) -> Iterator[pb.UtteranceChunk]:
        """Emitir un stream o esperar para verificar el deadline de transporte."""
        if req.prompt == "slow":
            Event().wait(0.2)
        yield from chunks()

    def HealthCheck(
        self, req: pb.HealthRequest, context: grpc.ServicerContext
    ) -> pb.HealthResponse:
        """Identificar explícitamente el engine de pruebas."""
        return pb.HealthResponse(healthy=True, model_id="test-only")


@pytest.fixture
def real_stub() -> Iterator[rpc.ImpostorEngineStub]:
    """Abrir y cerrar un servidor y un canal gRPC locales con puerto efímero."""
    with ThreadPoolExecutor(max_workers=2) as executor:
        server = grpc.server(executor)
        rpc.add_ImpostorEngineServicer_to_server(TestEngine(), server)
        port = server.add_insecure_port("127.0.0.1:0")
        server.start()
        try:
            with grpc.insecure_channel(f"127.0.0.1:{port}") as channel:
                grpc.channel_ready_future(channel).result(timeout=3)
                yield rpc.ImpostorEngineStub(channel)
        finally:
            server.stop(0).wait()


@pytest.mark.integration
def test_generated_stubs_work_over_real_grpc(real_stub: rpc.ImpostorEngineStub) -> None:
    """Los stubs publicados permiten consultar salud y recibir un stream real."""
    assert real_stub.HealthCheck(pb.HealthRequest(), timeout=1).healthy
    assert EngineClient(real_stub).generate(request(), timeout=1) == "Un café."


@pytest.mark.integration
def test_grpc_transport_enforces_the_deadline(
    real_stub: rpc.ImpostorEngineStub,
) -> None:
    """El límite de espera lo impone gRPC, incluso si el engine no responde a tiempo."""
    req = request()
    req.prompt = "slow"
    with pytest.raises(EngineFailure, match="engine_timeout"):
        EngineClient(real_stub).generate(req, timeout=0.01)
