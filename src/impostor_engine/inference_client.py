"""Cliente HTTP de streaming (solo stdlib) hacia el router de Hugging Face.

Reintentos: como máximo uno y únicamente cuando el fallo es de red previo al
envío de la petición (conexión rechazada, DNS, socket timeout en el connect) y
el deadline restante lo permite. Nunca se reintenta una respuesta HTTP, jamás
después de recibir un byte del stream, ni en errores de autenticación o
crédito. Per ACUERDOS_R2 los reintentos no deben duplicar llamadas facturables:
cada byte recibido implica que la petición pudo haberse facturado.
"""

from __future__ import annotations

import json
import math
import os
import time
from collections.abc import Iterator
from typing import Protocol
from urllib import error, request

ROUTER_BASE = "https://router.huggingface.co/v1"
USER_AGENT = "sospechai-engine/0.1 (curso UAO 2026-2)"

INPUT_PRICE_PER_1M = 0.17
OUTPUT_PRICE_PER_1M = 0.20
CACHED_PRICE_PER_1M = 0.136


def estimate_cost_usd(
    *, prompt_tokens: int, completion_tokens: int, cached_tokens: int = 0
) -> float:
    """Estimar el costo en USD de una llamada según tarifas publicadas."""
    return (
        prompt_tokens * INPUT_PRICE_PER_1M
        + completion_tokens * OUTPUT_PRICE_PER_1M
        + cached_tokens * CACHED_PRICE_PER_1M
    ) / 1_000_000


class StreamClient(Protocol):
    """Interfaz mínima que el servicer exige a su cliente de inferencia."""

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
        """Ceder los deltas de texto de una generación."""
        ...


class InferenceError(Exception):
    """Fallo de inferencia con un código estable, sin exponer credenciales."""

    def __init__(self, kind: str, message: str = "") -> None:
        """Conservar el tipo y un mensaje seguro para registrar."""
        self.kind = kind
        super().__init__(message or kind)


class _StreamState:
    """Acumular deltas y el último uso durante la lectura del stream."""

    def __init__(self, max_tokens: int) -> None:
        """Guardar el límite y preparar acumuladores vacíos."""
        self.max_tokens = max_tokens
        self.deltas: list[str] = []


class InferenceClient:
    """Consumir un stream OpenAI-compatible y exponer los deltas y el uso."""

    def __init__(self, *, timeout: float = 60.0, token: str | None = None) -> None:
        """Configurar el timeout por llamada y el token opcional."""
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("El timeout debe ser finito y positivo.")
        self.timeout = timeout
        self.token = token
        self.last_usage: dict[str, object] = {}
        self.attempts: int = 0

    def _bearer(self) -> str:
        """Resolver el token en el momento de la llamada desde HF_TOKEN."""
        token = self.token or os.environ.get("HF_TOKEN", "")
        if not token or not token.startswith("hf_"):
            raise InferenceError(
                "auth", "Falta HF_TOKEN válido (debe empezar con hf_)."
            )
        return token

    def stream_chat(
        self,
        messages: list[dict],
        *,
        model_id: str,
        temperature: float = 0.9,
        top_p: float = 0.9,
        max_tokens: int = 64,
        timeout: float | None = None,
    ) -> Iterator[str]:
        """Enviar una generación en streaming y ceder cada delta de texto.

        ``messages`` es la lista OpenAI-compatible ya construida por el llamador
        (sistema, historial y mensaje del usuario). El token se lee en el momento
        de la llamada desde HF_TOKEN. Acumula el último evento 'usage' y lo deja
        disponible como self.last_usage.
        """
        token = self._bearer()
        self.last_usage = {}
        self.attempts = 0
        budget = timeout if timeout is not None else self.timeout
        if not math.isfinite(budget) or budget <= 0:
            raise InferenceError("timeout", "Presupuesto no válido.")
        deadline = time.monotonic() + budget
        state = _StreamState(max_tokens)
        self._attempt(
            token, messages, model_id, temperature, top_p, max_tokens, deadline, state
        )
        yield from state.deltas

    def _attempt(
        self,
        token: str,
        messages: list[dict],
        model_id: str,
        temperature: float,
        top_p: float,
        max_tokens: int,
        deadline: float,
        state: _StreamState,
    ) -> None:
        """Ejecutar un intento único; reintentar solo fallos de red previos al envío."""
        retried = False
        while True:
            self.attempts += 1
            try:
                self._read_stream(
                    token,
                    messages,
                    model_id,
                    temperature,
                    top_p,
                    max_tokens,
                    deadline,
                    state,
                )
                return
            except _SendFailure as failure:
                if failure.is_timeout:
                    raise InferenceError("timeout", failure.message) from None
                remaining = deadline - time.monotonic()
                if retried or remaining <= 0:
                    raise InferenceError("unavailable", failure.message) from None
                retried = True
                continue
            except _StreamFailure as failure:
                raise InferenceError(failure.kind, failure.message) from None

    def _read_stream(
        self,
        token: str,
        messages: list[dict],
        model_id: str,
        temperature: float,
        top_p: float,
        max_tokens: int,
        deadline: float,
        state: _StreamState,
    ) -> None:
        """Abrir la conexión y consumir el stream completo."""
        body = json.dumps(
            {
                "model": model_id,
                "messages": messages,
                "temperature": temperature,
                "top_p": top_p,
                "max_tokens": max_tokens,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
        ).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }
        req = request.Request(
            f"{ROUTER_BASE}/chat/completions",
            data=body,
            headers=headers,
            method="POST",
        )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _SendFailure("deadline agotado antes de enviar", is_timeout=True)
        try:
            response = request.urlopen(req, timeout=remaining)
        except error.HTTPError as http_error:
            raise _StreamFailure(*self._map_http(http_error)) from None
        except (error.URLError, OSError, TimeoutError) as send_error:
            timeout_kind = _is_timeout(send_error)
            raise _SendFailure(str(send_error), is_timeout=timeout_kind) from None
        try:
            with response:
                self._consume(response, state)
        except (error.URLError, OSError, TimeoutError) as read_error:
            if _is_timeout(read_error):
                raise _StreamFailure("timeout", str(read_error)) from None
            raise _StreamFailure("unavailable", str(read_error)) from None

    def _consume(self, response, state: _StreamState) -> None:
        """Leer líneas SSE, capturar uso temprano y acumular deltas."""
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            event = json.loads(data)
            usage = event.get("usage")
            if isinstance(usage, dict):
                self.last_usage = usage
            choices = event.get("choices")
            if not isinstance(choices, list) or not choices:
                continue
            delta = choices[0].get("delta", {})
            if isinstance(delta, dict) and delta.get("content"):
                state.deltas.append(str(delta["content"]))

    def _map_http(self, http_error: error.HTTPError) -> tuple[str, str]:
        """Traducir una respuesta HTTP a (kind, mensaje seguro)."""
        detail = http_error.read().decode("utf-8", errors="replace")[:200]
        code = http_error.code
        if code in (401, 403):
            return "auth", f"HTTP {code}: {detail}".strip()
        if code == 402:
            return "credits", f"HTTP {code}: crédito agotado; {detail}".strip()
        if code in (404, 422):
            return "rejected", f"HTTP {code}: {detail}".strip()
        if code in (429,) or code >= 500:
            return "unavailable", f"HTTP {code}: {detail}".strip()
        return "rejected", f"HTTP {code}: {detail}".strip()


class _SendFailure(Exception):
    """Fallo de red previo al envío; el único candidato a reintento."""

    def __init__(self, message: str, *, is_timeout: bool) -> None:
        """Conservar el mensaje y si es un agotamiento de tiempo."""
        self.message = message
        self.is_timeout = is_timeout
        super().__init__(message)


class _StreamFailure(Exception):
    """Fallo ya vinculado a una respuesta o al cuerpo; nunca se reintenta."""

    def __init__(self, kind: str, message: str) -> None:
        """Guardar el tipo y el mensaje para traducir a InferenceError."""
        self.kind = kind
        self.message = message
        super().__init__(message)


def _is_timeout(exc: BaseException) -> bool:
    """Detectar de forma robusta un agotamiento de tiempo de socket."""
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, error.URLError) and isinstance(exc.reason, TimeoutError):
        return True
    return isinstance(getattr(exc, "reason", None), TimeoutError)
