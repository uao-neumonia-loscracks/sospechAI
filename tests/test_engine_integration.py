"""Integración real gRPC entre el servicer de R1 y el cliente de R2.

Levanta el ImpostorEngineServicer real en un servidor de loopback con un
cliente de inferencia simulado (sin HTTP externo) y consume el stream con
el EngineClient real de R2, validando el contrato de extremo a extremo.
"""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import grpc
import pytest

from proto import impostor_pb2 as pb
from proto import impostor_pb2_grpc as rpc
from src.impostor_engine.inference_client import InferenceError
from src.impostor_engine.servicer import ImpostorEngineServicer
from src.orchestrator.engine_client import EngineClient, EngineFailure


class FakeStreamClient:
    """Cliente de inferencia determinista: deltas fijos o un error fijo."""

    def __init__(
        self, deltas: list[str] | None = None, error: InferenceError | None = None
    ) -> None:
        """Guardar la secuencia o el fallo que debe entregar."""
        self.deltas = deltas or []
        self.error = error
        self.messages: list[dict] | None = None
        self.calls = 0

    def stream_chat(
        self,
        messages: list[dict],
        *,
        model_id: str,
        temperature: float,
        top_p: float,
        max_tokens: int,
        timeout: float,
    ) -> Iterator[str]:
        """Entregar los deltas o el error registrado; anotar la llamada."""
        self.calls += 1
        self.messages = messages
        if self.error is not None:
            raise self.error
        yield from self.deltas


@contextmanager
def serve(
    client: FakeStreamClient, **kwargs: object
) -> Iterator[rpc.ImpostorEngineStub]:
    """Abrir servidor de loopback con el servicer real y devolver el stub."""
    with ThreadPoolExecutor(max_workers=2) as executor:
        server = grpc.server(executor)
        rpc.add_ImpostorEngineServicer_to_server(
            ImpostorEngineServicer(client, **kwargs), server
        )
        port = server.add_insecure_port("127.0.0.1:0")
        server.start()
        try:
            with grpc.insecure_channel(f"127.0.0.1:{port}") as channel:
                grpc.channel_ready_future(channel).result(timeout=3)
                yield rpc.ImpostorEngineStub(channel)
        finally:
            server.stop(0).wait()


def request() -> pb.UtteranceRequest:
    """Petición válida para estas pruebas; el modelo no se toca en loopback."""
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


def test_r2_client_consumes_engine_stream_over_real_grpc() -> None:
    """El cliente real de R2 une los deltas y acepta el cierre vacío."""
    with serve(FakeStreamClient(["Hola", " mundo"])) as stub:
        assert EngineClient(stub).generate(request(), timeout=3) == "Hola mundo"


def test_trailing_metadata_reaches_r2_stub() -> None:
    """Los metadatos de observabilidad llegan al cliente al cerrar el stream."""
    with serve(FakeStreamClient(["hola", " mundo"])) as stub:
        call = stub.GenerateUtterance(request(), timeout=3)
        chunks = list(call)
        meta = dict(call.trailing_metadata())
    assert chunks[-1].is_final
    assert meta["x-status"] == "ok"
    assert meta["x-attempts"] == "1"
    assert "x-latency-total-ms" in meta
    assert "x-latency-ttft-ms" in meta


def test_word_cut_guard_reaches_r2_before_final_chunk() -> None:
    """Aunque el proveedor entregue más palabras, R2 nunca recibe el exceso."""
    deltas = ["palabra1"] + [f" palabra{i}" for i in range(2, 21)]
    fake = FakeStreamClient(deltas)
    req = request()
    req.config.max_words = 5
    with serve(fake) as stub:
        text = EngineClient(stub).generate(req, timeout=3)
    assert text == "palabra1 palabra2 palabra3 palabra4 palabra5"
    assert fake.calls == 1


def test_subword_deltas_are_not_lost_by_the_guard() -> None:
    """Fragmentos como 'ía' se conservan aunque no formen una palabra nueva."""
    fake = FakeStreamClient(["Esta", " noche", " leer", "ía", " algunos"])
    with serve(fake) as stub:
        assert EngineClient(stub).generate(request(), timeout=3) == (
            "Esta noche leería algunos"
        )


def test_credits_error_aborts_and_r2_maps_to_engine_rejected() -> None:
    """El 402 del proveedor llega como código estable engine_rejected."""
    fake = FakeStreamClient(error=InferenceError("credits", "sin saldo"))
    with serve(fake) as stub:
        with pytest.raises(EngineFailure, match="engine_rejected"):
            EngineClient(stub).generate(request(), timeout=3)


def test_timeout_aborts_and_r2_maps_to_engine_timeout() -> None:
    """El deadline del lado del engine se reporta como engine_timeout."""
    fake = FakeStreamClient(error=InferenceError("timeout", "demorado"))
    with serve(fake) as stub:
        with pytest.raises(EngineFailure, match="engine_timeout"):
            EngineClient(stub).generate(request(), timeout=3)


def test_server_rejects_invalid_request_before_calling_client() -> None:
    """La validación del servicer protege al proveedor de peticiones inválidas.

    Se llama al stub directamente porque el EngineClient de R2 ya bloquea
    esta configuración localmente; este test cubre la defensa del servidor.
    """
    invalid = request()
    invalid.config.engine_backend = "local-llamacpp"
    fake = FakeStreamClient(["nunca debe correr"])
    with serve(fake) as stub:
        with pytest.raises(grpc.RpcError) as captured:
            list(stub.GenerateUtterance(invalid, timeout=3))
    assert captured.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert fake.calls == 0


def test_system_prompt_and_history_reach_the_client_in_order() -> None:
    """El servicer arma system + historial alternado y la pregunta del usuario."""
    req = request()
    req.history.extend(
        [pb.Message(alias="uno", text="hola"), pb.Message(alias="dos", text="chau")]
    )
    fake = FakeStreamClient(["respuesta"])
    with serve(fake, system_prompt="Eres el impostor.") as stub:
        EngineClient(stub).generate(req, timeout=3)
    assert fake.messages == [
        {"role": "system", "content": "Eres el impostor."},
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "chau"},
        {"role": "user", "content": "¿Qué comiste?"},
    ]


def test_health_check_reflects_token_and_configured_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sin token el engine declara no saludable; con token reporta el modelo."""
    with serve(FakeStreamClient([]), model_id="mi-modelo:proveedor") as stub:
        assert not stub.HealthCheck(pb.HealthRequest(), timeout=1).healthy
        monkeypatch.setenv("HF_TOKEN", "hf_test")
        response = stub.HealthCheck(pb.HealthRequest(), timeout=1)
    assert response.healthy
    assert response.model_id == "mi-modelo:proveedor"
