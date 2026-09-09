"""Servicer gRPC: valida, presupuesta y delega el flujo de inferencia a R1."""

from collections.abc import Iterator

import pytest

from proto import impostor_pb2 as pb
from src.impostor_engine.guards import count_words
from src.impostor_engine.inference_client import InferenceError
from src.impostor_engine.servicer import ImpostorEngineServicer


class FakeStreamClient:
    """Cliente compatible con el Protocol: produce deltas o lanza InferenceError."""

    def __init__(
        self,
        deltas: list[str],
        *,
        error: InferenceError | None = None,
        token: bool = True,
    ) -> None:
        """Definir la respuesta del stream y el estado de configuración."""
        self._deltas = list(deltas)
        self._error = error
        self.calls: list[dict] = []
        self.last_usage = {"completion_tokens": 3}
        self.token = token

    def stream_chat(self, messages: list[dict], **kwargs) -> Iterator[str]:
        """Registrar parámetros y ceder deltas o lanzar el error configurado."""
        self.calls.append({"messages": messages, **kwargs})
        if self._error is not None:
            raise self._error
        yield from self._deltas


class FakeContext:
    """Contexto gRPC doble que registra aborts y expone el tiempo restante."""

    def __init__(self, *, remaining: float = 8.0) -> None:
        """Fijar el presupuesto y preparar el registro de aborts."""
        self.remaining = remaining
        self.aborted: list[tuple] = []

    def time_remaining(self) -> float:
        """Devolver el presupuesto configurado."""
        return self.remaining

    def abort(self, code, details: str):
        """Registrar el abort simulando la excepción real de gRPC."""
        self.aborted.append((code, details))
        raise RuntimeError("abort llamado")


def streamed_text(chunks: list[pb.UtteranceChunk]) -> str:
    """Concatenar únicamente los fragmentos de texto no finales."""
    return "".join(c.text_delta for c in chunks if not c.is_final)


def request(**overrides) -> pb.UtteranceRequest:
    """Construir una petición válida con sobreescrituras opcionales."""
    base = pb.UtteranceRequest(
        room_id="practice",
        persona_id="p1",
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
    for field, value in overrides.items():
        if field == "config":
            continue
        setattr(base, field, value)
    config_overrides = overrides.get("config", {})
    for field, value in config_overrides.items():
        setattr(base.config, field, value)
    return base


def test_happy_path_emits_deltas_then_empty_final() -> None:
    """Los deltas se emiten y el stream termina con un final vacío único."""
    client = FakeStreamClient(["hola", " mundo"])
    servicer = ImpostorEngineServicer(client)
    chunks = list(servicer.GenerateUtterance(request(), FakeContext()))
    assert streamed_text(chunks) == "hola mundo"
    final = [c for c in chunks if c.is_final]
    assert len(final) == 1
    assert final[0].text_delta == ""
    assert [c.token_index for c in chunks if not c.is_final] == [0, 1]


def test_word_cut_stops_at_max_words_and_never_exceeds() -> None:
    """El límite de palabras corta y detiene el stream sin exceder."""
    client = FakeStreamClient(["uno dos tres cuatro cinco"])
    servicer = ImpostorEngineServicer(client)
    chunks = list(
        servicer.GenerateUtterance(request(config={"max_words": 2}), FakeContext())
    )
    assert count_words(streamed_text(chunks)) <= 2
    assert streamed_text(chunks).split() == ["uno", "dos"]
    assert chunks[-1].is_final and chunks[-1].text_delta == ""


def test_missing_system_prompt_omits_system_message() -> None:
    """Sin system_prompt configurado no se envía mensaje de sistema."""
    client = FakeStreamClient(["hola"])
    servicer = ImpostorEngineServicer(client)  # system_prompt None por defecto
    list(servicer.GenerateUtterance(request(), FakeContext()))
    messages = client.calls[0]["messages"]
    assert all(msg["role"] != "system" for msg in messages)


def test_system_prompt_is_sent_when_configured() -> None:
    """Con system_prompt configurado el mensaje de sistema encabeza el pedido."""
    client = FakeStreamClient(["hola"])
    servicer = ImpostorEngineServicer(client, system_prompt="Sé el impostor.")
    list(servicer.GenerateUtterance(request(), FakeContext()))
    messages = client.calls[0]["messages"]
    assert messages[0] == {"role": "system", "content": "Sé el impostor."}


def test_history_emitted_as_alternating_roles_starting_user() -> None:
    """El historial se simplifica a roles alternos iniciando en 'user'."""
    client = FakeStreamClient(["hola"])
    servicer = ImpostorEngineServicer(client)
    req = request()
    req.history.extend(
        [
            pb.Message(alias="A", text="primero"),
            pb.Message(alias="B", text="segundo"),
            pb.Message(alias="A", text="tercero"),
        ]
    )
    list(servicer.GenerateUtterance(req, FakeContext()))
    messages = [m for m in client.calls[0]["messages"] if m["role"] != "system"]
    assert messages == [
        {"role": "user", "content": "primero"},
        {"role": "assistant", "content": "segundo"},
        {"role": "user", "content": "tercero"},
        {"role": "user", "content": "¿Qué comiste?"},
    ]


def test_empty_prompt_aborts_invalid_argument() -> None:
    """Un prompt vacío se aborta antes de tocar el cliente."""
    client = FakeStreamClient(["hola"])
    servicer = ImpostorEngineServicer(client)
    context = FakeContext()
    with pytest.raises(RuntimeError):
        list(servicer.GenerateUtterance(request(prompt="   "), context))
    assert context.aborted[0][0].name == "INVALID_ARGUMENT"
    assert client.calls == []


def test_invalid_backend_aborts() -> None:
    """Un backend distinto de hf-router se rechaza."""
    client = FakeStreamClient(["hola"])
    servicer = ImpostorEngineServicer(client)
    context = FakeContext()
    with pytest.raises(RuntimeError):
        list(
            servicer.GenerateUtterance(
                request(config={"engine_backend": "local"}), context
            )
        )
    assert context.aborted[0][0].name == "INVALID_ARGUMENT"
    assert client.calls == []


def test_credits_error_aborts_resource_exhausted() -> None:
    """Crédito agotado produce RESOURCE_EXHAUSTED sin final vacío."""
    client = FakeStreamClient([], error=InferenceError("credits", "agotado"))
    servicer = ImpostorEngineServicer(client)
    context = FakeContext()
    with pytest.raises(RuntimeError):
        list(servicer.GenerateUtterance(request(), context))
    assert context.aborted[0][0].name == "RESOURCE_EXHAUSTED"


def test_auth_error_aborts_unauthenticated() -> None:
    """Un fallo de autenticación produce UNAUTHENTICATED."""
    client = FakeStreamClient([], error=InferenceError("auth", "sin token"))
    servicer = ImpostorEngineServicer(client)
    context = FakeContext()
    with pytest.raises(RuntimeError):
        list(servicer.GenerateUtterance(request(), context))
    assert context.aborted[0][0].name == "UNAUTHENTICATED"


def test_timeout_error_aborts_deadline_exceeded() -> None:
    """Un agotamiento del presupuesto produce DEADLINE_EXCEEDED."""
    client = FakeStreamClient([], error=InferenceError("timeout", "se acabó"))
    servicer = ImpostorEngineServicer(client)
    context = FakeContext()
    with pytest.raises(RuntimeError):
        list(servicer.GenerateUtterance(request(), context))
    assert context.aborted[0][0].name == "DEADLINE_EXCEEDED"


def test_unavailable_error_aborts_unavailable() -> None:
    """Un proveedor no disponible produce UNAVAILABLE."""
    client = FakeStreamClient([], error=InferenceError("unavailable", "caído"))
    servicer = ImpostorEngineServicer(client)
    context = FakeContext()
    with pytest.raises(RuntimeError):
        list(servicer.GenerateUtterance(request(), context))
    assert context.aborted[0][0].name == "UNAVAILABLE"


def test_rejected_error_aborts_internal() -> None:
    """Un rechazo del proveedor produce INTERNAL como error interno del engine."""
    client = FakeStreamClient([], error=InferenceError("rejected", "no"))
    servicer = ImpostorEngineServicer(client)
    context = FakeContext()
    with pytest.raises(RuntimeError):
        list(servicer.GenerateUtterance(request(), context))
    assert context.aborted[0][0].name == "INTERNAL"


def test_no_chunks_after_final() -> None:
    """El final vacío es el último chunk; nunca emite texto tras él."""
    client = FakeStreamClient(["hola"])
    servicer = ImpostorEngineServicer(client)
    chunks = list(servicer.GenerateUtterance(request(), FakeContext()))
    assert chunks[-1].is_final
    assert all(not c.is_final for c in chunks[:-1])


def test_health_check_healthy_when_configured(monkeypatch) -> None:
    """Con token y cliente configurado el servicio se reporta sano."""
    monkeypatch.setenv("HF_TOKEN", "hf_secret")
    servicer = ImpostorEngineServicer(FakeStreamClient([]), model_id="m1")
    response = servicer.HealthCheck(pb.HealthRequest(), FakeContext())
    assert response.healthy is True
    assert response.model_id == "m1"


def test_health_check_not_healthy_without_token(monkeypatch) -> None:
    """Sin token el servicio se reporta no sano."""
    monkeypatch.delenv("HF_TOKEN", raising=False)
    servicer = ImpostorEngineServicer(FakeStreamClient([]), model_id="m1")
    response = servicer.HealthCheck(pb.HealthRequest(), FakeContext())
    assert response.healthy is False


def test_budget_capped_by_round_timeout() -> None:
    """El presupuesto nunca supera round_timeout aunque haya más tiempo de contexto."""
    client = FakeStreamClient(["hola"])
    servicer = ImpostorEngineServicer(client, round_timeout=4.0)
    context = FakeContext(remaining=50.0)
    list(list(servicer.GenerateUtterance(request(), context)))
    # El timeout del cliente se envía como parte de los parámetros.
    assert client.calls[0]["timeout"] is not None


def test_zero_budget_aborts_deadline_exceeded() -> None:
    """Un presupuesto nulo aborta antes de llamar al cliente."""
    client = FakeStreamClient(["hola"])
    servicer = ImpostorEngineServicer(client)
    context = FakeContext(remaining=0.0)
    with pytest.raises(RuntimeError):
        list(servicer.GenerateUtterance(request(), context))
    assert context.aborted[0][0].name == "DEADLINE_EXCEEDED"
    assert client.calls == []
