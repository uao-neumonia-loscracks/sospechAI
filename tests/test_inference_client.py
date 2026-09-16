"""Cliente HTTP de streaming hacia el router de Hugging Face (R1)."""

import io

import pytest

from src.impostor_engine.inference_client import (
    InferenceClient,
    InferenceError,
    estimate_cost_usd,
)


@pytest.fixture(autouse=True)
def _hf_token(monkeypatch) -> None:
    """Asegurar un HF_TOKEN válido por defecto en las pruebas de red."""
    monkeypatch.setenv("HF_TOKEN", "hf_test_secret")


class FakeResponse:
    """Objeto similar a un HTTPResponse: iterable en bytes por línea."""

    def __init__(self, payload: str) -> None:
        """Conservar el cuerpo y confirmar que se cerró."""
        self._buffer = io.BytesIO(payload.encode("utf-8"))
        self.closed = False

    def __iter__(self) -> "FakeResponse":
        """Permitir iterar líneas como un HTTPResponse."""
        return self

    def __next__(self) -> bytes:
        """Devolver la siguiente línea completa en bytes."""
        line = self._buffer.readline()
        if not line:
            raise StopIteration
        return line

    def __enter__(self) -> "FakeResponse":
        """Abrir el contexto sin acciones adicionales."""
        return self

    def __exit__(self, *exc) -> None:
        """Cerrar al salir del contexto."""
        self.close()

    def close(self) -> None:
        """Marcar el cierre."""
        self.closed = True


class FakeOpener:
    """Doble de urllib.request.urlopen: devuelve respuestas o lanza errores."""

    def __init__(self, responses: list) -> None:
        """Guardar la cola de respuestas y registrar cada llamada y request."""
        self._responses = list(responses)
        self.calls = 0
        self.requests = []

    def __call__(self, req, timeout: float) -> FakeResponse:
        """Atender una petición registrando deadlocks, URL y opción de timeout."""
        self.calls += 1
        self.requests.append((req, timeout))
        response = self._responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def sse(*events: str) -> str:
    """Construir una respuesta SSE a partir de eventos y el cierre [DONE]."""
    body = "".join(f"data: {event}\n\n" for event in events)
    return body + "data: [DONE]\n\n"


def content_chunks(*texts: str) -> list[str]:
    """Crear eventos de streaming con un fragmento de texto cada uno."""
    return ['{"choices": [{"delta": {"content": "%s"}}]}' % text for text in texts]


def usage_chunk() -> str:
    """Crear el evento final sin choices que transporta el uso."""
    return '{"choices": [], "usage": {"completion_tokens": 7}}'


def test_happy_stream_yields_deltas_and_usage(monkeypatch) -> None:
    """Texto, chunk de uso y [DONE] producen los deltas y el uso final."""
    body = sse(*(content_chunks("hola", " mundo") + [usage_chunk()]))
    opener = FakeOpener([FakeResponse(body)])
    monkeypatch.setattr("urllib.request.urlopen", opener)
    client = InferenceClient(timeout=30.0)
    deltas = list(
        client.stream_chat(
            messages=[{"role": "user", "content": "¿qué tal?"}],
            model_id="m",
            max_tokens=16,
        )
    )
    assert deltas == ["hola", " mundo"]
    assert client.last_usage == {"completion_tokens": 7}
    assert opener.calls == 1


def test_usage_captured_on_empty_choices_chunk(monkeypatch) -> None:
    """El uso se captura aunque llegue en un chunk sin choices."""
    body = "data: " + usage_chunk() + "\n\ndata: [DONE]\n\n"
    opener = FakeOpener([FakeResponse(body)])
    monkeypatch.setattr("urllib.request.urlopen", opener)
    client = InferenceClient(timeout=30.0)
    assert (
        list(
            client.stream_chat(
                messages=[{"role": "user", "content": "p"}], model_id="m", max_tokens=1
            )
        )
        == []
    )
    assert client.last_usage == {"completion_tokens": 7}


def test_402_is_credits_without_retry(monkeypatch) -> None:
    """HTTP 402 se traduce a 'credits' y nunca se reintenta."""
    from urllib import error

    http = error.HTTPError(
        "url",
        402,
        "Payment Required",
        {},
        io.BytesIO(b'{"error": "creditos agotados"}'),
    )
    opener = FakeOpener([http])
    monkeypatch.setattr("urllib.request.urlopen", opener)
    client = InferenceClient(timeout=30.0)
    with pytest.raises(InferenceError) as captured:
        list(
            client.stream_chat(
                messages=[{"role": "user", "content": "p"}], model_id="m", max_tokens=1
            )
        )
    assert captured.value.kind == "credits"
    assert opener.calls == 1
    assert "creditos agotados" in str(captured.value)


def test_401_is_auth_without_retry(monkeypatch) -> None:
    """HTTP 401 se traduce a 'auth' y nunca se reintenta."""
    from urllib import error

    http = error.HTTPError(
        "url", 401, "Unauthorized", {}, io.BytesIO(b'{"error": "token invalido"}')
    )
    opener = FakeOpener([http])
    monkeypatch.setattr("urllib.request.urlopen", opener)
    client = InferenceClient(timeout=30.0)
    with pytest.raises(InferenceError) as captured:
        list(
            client.stream_chat(
                messages=[{"role": "user", "content": "p"}], model_id="m", max_tokens=1
            )
        )
    assert captured.value.kind == "auth"
    assert opener.calls == 1


def test_missing_token_is_auth(monkeypatch) -> None:
    """Sin HF_TOKEN válido se traduce a 'auth' antes de tocar la red."""
    monkeypatch.delenv("HF_TOKEN", raising=False)
    opener = FakeOpener([])
    monkeypatch.setattr("urllib.request.urlopen", opener)
    client = InferenceClient(timeout=30.0)
    with pytest.raises(InferenceError) as captured:
        list(
            client.stream_chat(
                messages=[{"role": "user", "content": "p"}], model_id="m", max_tokens=1
            )
        )
    assert captured.value.kind == "auth"
    assert opener.calls == 0


def test_network_error_before_send_retries_once_then_unavailable(monkeypatch) -> None:
    """Un error de red previo al envío se reintenta una vez y luego es 'unavailable'."""
    first = ConnectionRefusedError("conexión rechazada")
    opener = FakeOpener([first, ConnectionRefusedError("again")])
    monkeypatch.setattr("urllib.request.urlopen", opener)
    client = InferenceClient(timeout=30.0)
    with pytest.raises(InferenceError) as captured:
        list(
            client.stream_chat(
                messages=[{"role": "user", "content": "p"}], model_id="m", max_tokens=1
            )
        )
    assert captured.value.kind == "unavailable"
    assert opener.calls == 2


def test_timeout_kind_on_deadline_socket_timeout(monkeypatch) -> None:
    """Un socket timeout que agota el deadline se traduce a 'timeout'."""
    import socket
    from urllib import error

    failure = error.URLError(socket.timeout("deadline"))
    opener = FakeOpener([failure])
    monkeypatch.setattr("urllib.request.urlopen", opener)
    client = InferenceClient(timeout=30.0)
    with pytest.raises(InferenceError) as captured:
        list(
            client.stream_chat(
                messages=[{"role": "user", "content": "p"}], model_id="m", max_tokens=1
            )
        )
    assert captured.value.kind == "timeout"
    assert opener.calls == 1


def test_done_without_usage_yields_text_and_empty_usage(monkeypatch) -> None:
    """[DONE] sin uso final conserva los deltas y deja last_usage vacío."""
    body = sse(*content_chunks("hola"))
    opener = FakeOpener([FakeResponse(body)])
    monkeypatch.setattr("urllib.request.urlopen", opener)
    client = InferenceClient(timeout=30.0)
    deltas = list(
        client.stream_chat(
            messages=[{"role": "user", "content": "p"}], model_id="m", max_tokens=1
        )
    )
    assert deltas == ["hola"]
    assert client.last_usage == {}


def test_http_5xx_is_unavailable_without_retry(monkeypatch) -> None:
    """HTTP 503 se traduce a 'unavailable' sin reintentar respuestas HTTP."""
    from urllib import error

    http = error.HTTPError(
        "url", 503, "Service Unavailable", {}, io.BytesIO(b'{"error": "cargado"}')
    )
    opener = FakeOpener([http, http])
    monkeypatch.setattr("urllib.request.urlopen", opener)
    client = InferenceClient(timeout=30.0)
    with pytest.raises(InferenceError) as captured:
        list(
            client.stream_chat(
                messages=[{"role": "user", "content": "p"}], model_id="m", max_tokens=1
            )
        )
    assert captured.value.kind == "unavailable"
    assert opener.calls == 1


def test_404_is_rejected_without_retry(monkeypatch) -> None:
    """HTTP 404 se traduce a 'rejected' sin reintentar."""
    from urllib import error

    http = error.HTTPError(
        "url", 404, "Not Found", {}, io.BytesIO(b'{"error": "modelo inexistente"}')
    )
    opener = FakeOpener([http])
    monkeypatch.setattr("urllib.request.urlopen", opener)
    client = InferenceClient(timeout=30.0)
    with pytest.raises(InferenceError) as captured:
        list(
            client.stream_chat(
                messages=[{"role": "user", "content": "p"}], model_id="m", max_tokens=1
            )
        )
    assert captured.value.kind == "rejected"
    assert opener.calls == 1


def test_sent_request_builds_openai_body(monkeypatch) -> None:
    """El cuerpo incluye flujo, uso y parámetros tal como requiere OpenAI-compat."""
    import json

    opener = FakeOpener([FakeResponse("data: [DONE]\n\n")])
    monkeypatch.setattr("urllib.request.urlopen", opener)
    monkeypatch.setenv("HF_TOKEN", "hf_test_secret")
    client = InferenceClient(timeout=30.0)
    list(
        client.stream_chat(
            messages=[{"role": "user", "content": "¿qué tal?"}],
            model_id="org/model:provider",
            temperature=0.9,
            top_p=0.95,
            max_tokens=24,
        )
    )
    req, timeout = opener.requests[0]
    body = json.loads(req.data.decode("utf-8"))
    assert body["model"] == "org/model:provider"
    assert body["messages"] == [{"role": "user", "content": "¿qué tal?"}]
    assert body["temperature"] == 0.9
    assert body["top_p"] == 0.95
    assert body["max_tokens"] == 24
    assert body["stream"] is True
    assert body["stream_options"] == {"include_usage": True}
    assert timeout == pytest.approx(30.0, abs=0.1)
    auth = req.get_header("Authorization")
    assert auth == "Bearer hf_test_secret"
    headers = dict(req.header_items())
    assert headers["User-agent"] == "sospechai-engine/0.1 (curso UAO 2026-2)"
    assert headers["Content-type"] == "application/json"


def test_attempts_counts_single_success(monkeypatch) -> None:
    """Una llamada exitosa cuenta exactamente un intento."""
    body = sse(*content_chunks("hola"))
    opener = FakeOpener([FakeResponse(body)])
    monkeypatch.setattr("urllib.request.urlopen", opener)
    client = InferenceClient(timeout=30.0)
    list(
        client.stream_chat(
            messages=[{"role": "user", "content": "p"}], model_id="m", max_tokens=1
        )
    )
    assert client.attempts == 1


def test_attempts_counts_retry_when_send_failure(monkeypatch) -> None:
    """Un fallo de red previo al envío seguido de éxito cuenta dos intentos."""
    first = ConnectionRefusedError("conexión rechazada")
    body = sse(*content_chunks("hola"))
    opener = FakeOpener([first, FakeResponse(body)])
    monkeypatch.setattr("urllib.request.urlopen", opener)
    client = InferenceClient(timeout=30.0)
    deltas = list(
        client.stream_chat(
            messages=[{"role": "user", "content": "p"}], model_id="m", max_tokens=1
        )
    )
    assert deltas == ["hola"]
    assert client.attempts == 2


def test_estimate_cost_usd() -> None:
    """El costo estimado sigue las tarifas publicadas por millón de tokens."""
    assert estimate_cost_usd(prompt_tokens=1_000_000, completion_tokens=0) == 0.17
    assert estimate_cost_usd(prompt_tokens=0, completion_tokens=1_000_000) == 0.20
    expected = 42 * 0.17e-6 + 17 * 0.20e-6
    assert estimate_cost_usd(prompt_tokens=42, completion_tokens=17) == pytest.approx(
        expected
    )
