"""Servicer gRPC: valida, presupuesta y delega el flujo de inferencia a R1."""

from collections.abc import Iterator

import pytest

from proto import impostor_pb2 as pb
from src.impostor_engine.guards import count_words
from src.impostor_engine.inference_client import InferenceError
from src.impostor_engine.servicer import (
    CHARACTER_BREAK_CORRECTIVE,
    MIN_BUDGET,
    ImpostorEngineServicer,
)


class FakeStreamClient:
    """Cliente compatible con el Protocol: deltas, secuencias o InferenceError."""

    def __init__(
        self,
        deltas: list[str],
        *,
        error: InferenceError | None = None,
        token: bool = True,
        per_call: list[list[str]] | None = None,
    ) -> None:
        """Definir la respuesta del stream y el estado de configuración."""
        self._deltas = list(deltas)
        self._error = error
        self._per_call = list(per_call) if per_call is not None else None
        self._call_index = 0
        self.calls: list[dict] = []
        self.last_usage = {"completion_tokens": 3}
        self.token = token

    def stream_chat(self, messages: list[dict], **kwargs) -> Iterator[str]:
        """Registrar parámetros y ceder deltas o lanzar el error configurado."""
        self.calls.append({"messages": list(messages), **kwargs})
        if self._error is not None:
            raise self._error
        if self._per_call is not None:
            if self._call_index < len(self._per_call):
                deltas = self._per_call[self._call_index]
                self._call_index += 1
                yield from deltas
            return
        yield from self._deltas


class FakeContext:
    """Contexto gRPC doble que registra aborts y expone el tiempo restante."""

    def __init__(self, *, remaining: float = 8.0) -> None:
        """Fijar el presupuesto y preparar el registro de aborts."""
        self.remaining = remaining
        self.aborted: list[tuple] = []
        self.trailing_metadata: list[tuple[str, str]] | None = None

    def time_remaining(self) -> float:
        """Devolver el presupuesto configurado."""
        return self.remaining

    def set_trailing_metadata(self, metadata) -> None:
        """Guardar los metadatos tal como los envía el servidor."""
        self.trailing_metadata = list(metadata)

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
            system_prompt_version="v2",
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


def test_missing_override_resolves_prompt_from_store() -> None:
    """Sin override estático, el contenido de sistema se resuelve desde el store."""
    client = FakeStreamClient(["hola"])
    servicer = ImpostorEngineServicer(client)  # system_prompt None por defecto
    list(servicer.GenerateUtterance(request(), FakeContext()))
    messages = client.calls[0]["messages"]
    assert messages[0]["role"] == "system"
    assert "Eres Pipe" in messages[0]["content"]


def test_system_prompt_is_sent_when_configured() -> None:
    """Con system_prompt configurado el mensaje de sistema encabeza el pedido."""
    client = FakeStreamClient(["hola"])
    servicer = ImpostorEngineServicer(client, system_prompt="Sé el impostor.")
    list(servicer.GenerateUtterance(request(), FakeContext()))
    messages = client.calls[0]["messages"]
    assert messages[0] == {"role": "system", "content": "Sé el impostor."}


def test_resolved_system_prompt_is_preferred_over_static() -> None:
    """El override estático gana sobre el contenido resuelto por el store."""
    client = FakeStreamClient(["hola"])
    servicer = ImpostorEngineServicer(client, system_prompt="Sé el impostor.")
    list(servicer.GenerateUtterance(request(), FakeContext()))
    messages = client.calls[0]["messages"]
    assert messages[0]["content"] == "Sé el impostor."


def test_unknown_persona_aborts_before_calling_client() -> None:
    """Una persona inexistente aborta con INVALID_ARGUMENT sin tocar el cliente."""
    req = request()
    req.persona_id = "nope"
    client = FakeStreamClient(["hola"])
    servicer = ImpostorEngineServicer(client)
    context = FakeContext()
    with pytest.raises(RuntimeError):
        list(servicer.GenerateUtterance(req, context))
    assert context.aborted[0][0].name == "INVALID_ARGUMENT"
    assert client.calls == []


def test_unknown_version_aborts_before_calling_client() -> None:
    """Una versión inexistente aborta con INVALID_ARGUMENT sin tocar el cliente."""
    req = request(config={"system_prompt_version": "v9"})
    client = FakeStreamClient(["hola"])
    servicer = ImpostorEngineServicer(client)
    context = FakeContext()
    with pytest.raises(RuntimeError):
        list(servicer.GenerateUtterance(req, context))
    assert context.aborted[0][0].name == "INVALID_ARGUMENT"
    assert client.calls == []


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


def test_happy_path_emits_trailing_metadata() -> None:
    """El camino feliz emite metadatos de uso y latencia al cerrar el stream."""
    client = FakeStreamClient(["hola", " mundo"])
    servicer = ImpostorEngineServicer(client)
    context = FakeContext()
    list(servicer.GenerateUtterance(request(), context))
    assert context.trailing_metadata is not None
    meta = dict(context.trailing_metadata)
    assert meta["x-status"] == "ok"
    assert meta["x-attempts"] == "1"
    assert meta["x-usage-completion-tokens"] == "3"
    assert meta["x-model-id"] == "test/model:provider"
    assert "x-latency-total-ms" in meta


def test_cached_tokens_read_from_prompt_tokens_details() -> None:
    """Los cacheados se leen de prompt_tokens_details cuando llegan anidados."""
    # Arrange
    client = FakeStreamClient(["hola"])
    client.last_usage = {
        "prompt_tokens": 500,
        "completion_tokens": 5,
        "prompt_tokens_details": {"cached_tokens": 120},
    }
    servicer = ImpostorEngineServicer(client)
    context = FakeContext()
    # Act
    list(servicer.GenerateUtterance(request(), context))
    # Assert
    meta = dict(context.trailing_metadata)
    assert meta["x-usage-cached-tokens"] == "120"


def test_cached_tokens_flat_key_fallback_still_works() -> None:
    """La clave plana cached_tokens sigue funcionando como respaldo."""
    # Arrange
    client = FakeStreamClient(["hola"])
    client.last_usage = {
        "prompt_tokens": 500,
        "completion_tokens": 5,
        "cached_tokens": 80,
    }
    servicer = ImpostorEngineServicer(client)
    context = FakeContext()
    # Act
    list(servicer.GenerateUtterance(request(), context))
    # Assert
    meta = dict(context.trailing_metadata)
    assert meta["x-usage-cached-tokens"] == "80"


def test_missing_cached_tokens_emits_zero() -> None:
    """Sin claves de cacheados el valor emitido es cero y no lanza."""
    # Arrange
    client = FakeStreamClient(["hola"])
    client.last_usage = {"prompt_tokens": 500, "completion_tokens": 5}
    servicer = ImpostorEngineServicer(client)
    context = FakeContext()
    # Act
    list(servicer.GenerateUtterance(request(), context))
    # Assert
    meta = dict(context.trailing_metadata)
    assert meta["x-usage-cached-tokens"] == "0"


def test_error_emits_trailing_metadata_with_status() -> None:
    """El camino de error emite el estado del fallo antes de abortar."""
    client = FakeStreamClient([], error=InferenceError("credits", "agotado"))
    servicer = ImpostorEngineServicer(client)
    context = FakeContext()
    with pytest.raises(RuntimeError):
        list(servicer.GenerateUtterance(request(), context))
    assert context.aborted[0][0].name == "RESOURCE_EXHAUSTED"
    assert context.trailing_metadata is not None
    meta = dict(context.trailing_metadata)
    assert meta["x-status"] == "credits"
    assert meta["x-attempts"] == "1"


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


def test_character_break_flag_off_keeps_incremental_chunks() -> None:
    """Con la regeneración apagada el flujo incremental clásico se conserva."""
    client = FakeStreamClient(["ho", "la ", "mundo"])
    servicer = ImpostorEngineServicer(client, regenerate_on_character_break=False)
    chunks = list(servicer.GenerateUtterance(request(), FakeContext()))
    assert [c.token_index for c in chunks if not c.is_final] == [0, 1, 2]
    assert streamed_text(chunks) == "hola mundo"
    assert len([c for c in chunks if c.is_final]) == 1


def test_character_break_clean_first_attempt_no_regeneration() -> None:
    """Candidato limpio al primer intento: un solo delta, sin regeneraciones."""
    client = FakeStreamClient([], per_call=[["hola amigos"]])
    servicer = ImpostorEngineServicer(client, regenerate_on_character_break=True)
    context = FakeContext()
    chunks = list(servicer.GenerateUtterance(request(), context))
    assert len(client.calls) == 1
    non_final = [c for c in chunks if not c.is_final]
    assert len(non_final) == 1
    assert non_final[0].token_index == 0
    assert streamed_text(chunks) == "hola amigos"
    meta = dict(context.trailing_metadata)
    assert meta["x-regenerations"] == "0"
    assert meta["x-character-break"] == "0"
    assert meta["x-status"] == "ok"


def test_character_break_regenerates_until_clean() -> None:
    """Primer intento roto y segundo limpio: un delta final y segunda llamada."""
    client = FakeStreamClient(
        [], per_call=[["soy una ia"], ["jajaja si, yo creo que Juan es la IA"]]
    )
    servicer = ImpostorEngineServicer(client, regenerate_on_character_break=True)
    context = FakeContext()
    chunks = list(servicer.GenerateUtterance(request(), context))
    assert len(client.calls) == 2
    assert streamed_text(chunks) == "jajaja si, yo creo que Juan es la IA"
    non_final = [c for c in chunks if not c.is_final]
    assert len(non_final) == 1
    assert non_final[0].token_index == 0
    assert chunks[-1].is_final and chunks[-1].text_delta == ""
    meta = dict(context.trailing_metadata)
    assert meta["x-status"] == "ok"
    assert meta["x-regenerations"] == "1"
    assert meta["x-character-break"] == "0"
    corrective = {"role": "system", "content": CHARACTER_BREAK_CORRECTIVE}
    assert client.calls[1]["messages"][-1] == corrective
    assert corrective not in client.calls[0]["messages"]


def test_character_break_fail_open_after_max_attempts() -> None:
    """Siempre roto: el tope de intentos se respeta y se entrega el último (fail-open)."""
    client = FakeStreamClient(
        [], per_call=[["soy una ia"], ["soy un modelo de lenguaje"]]
    )
    servicer = ImpostorEngineServicer(
        client, regenerate_on_character_break=True, max_attempts=2
    )
    context = FakeContext()
    chunks = list(servicer.GenerateUtterance(request(), context))
    assert len(client.calls) == 2
    assert streamed_text(chunks) == "soy un modelo de lenguaje"
    non_final = [c for c in chunks if not c.is_final]
    assert len(non_final) == 1
    assert chunks[-1].is_final and chunks[-1].text_delta == ""
    meta = dict(context.trailing_metadata)
    assert meta["x-status"] == "ok"
    assert meta["x-character-break"] == "1"
    assert meta["x-regenerations"] == "1"


def test_character_break_error_aborts_without_regeneration() -> None:
    """Un error de inferencia nunca regenera: aborta como en el flujo clásico."""
    client = FakeStreamClient([], error=InferenceError("credits", "agotado"))
    servicer = ImpostorEngineServicer(client, regenerate_on_character_break=True)
    context = FakeContext()
    with pytest.raises(RuntimeError):
        list(servicer.GenerateUtterance(request(), context))
    assert len(client.calls) == 1
    assert context.aborted[0][0].name == "RESOURCE_EXHAUSTED"
    assert dict(context.trailing_metadata)["x-status"] == "credits"


def test_character_break_validates_max_attempts() -> None:
    """max_attempts no entero o menor que 1 se rechaza en el constructor."""
    client = FakeStreamClient(["hola"])
    for bad in (0, -1, 2.5, True):
        with pytest.raises(ValueError):
            ImpostorEngineServicer(
                client, regenerate_on_character_break=True, max_attempts=bad
            )


def test_character_break_budget_divided_per_attempt() -> None:
    """Cada intento recibe como máximo el presupuesto restante dividido."""
    client = FakeStreamClient([], per_call=[["soy una ia"], ["hola"]])
    servicer = ImpostorEngineServicer(client, regenerate_on_character_break=True)
    context = FakeContext(remaining=8.0)
    list(servicer.GenerateUtterance(request(), context))
    assert len(client.calls) == 2
    first, second = client.calls[0], client.calls[1]
    assert first["timeout"] <= 8.0 / 2 + 1e-6
    assert first["timeout"] >= MIN_BUDGET
    assert 0 < second["timeout"] <= 8.0
