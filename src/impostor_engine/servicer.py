"""Servicer gRPC del engine: valida, presupuesta y delega a R1.

Este módulo solo conoce HTTP y el proveedor a través del cliente de inferencia.
Aplica las guardas de generación sobre el flujo y traduce cada fallo del
cliente a un estado gRPC que el cliente de R2 pueda interpretar.
"""

from __future__ import annotations

import math
import os
from collections.abc import Iterator

import grpc

from proto import impostor_pb2 as pb
from proto import impostor_pb2_grpc as rpc
from src.impostor_engine.guards import count_words, cut_to_max_words, normalize_text
from src.impostor_engine.inference_client import InferenceError, StreamClient

MIN_BUDGET = 0.05


class ImpostorEngineServicer(rpc.ImpostorEngineServicer):
    """Servidor que genera un utterance en streaming con guardas de salida."""

    def __init__(
        self,
        client: StreamClient,
        *,
        system_prompt: str | None = None,
        round_timeout: float = 8.0,
        model_id: str = "",
    ) -> None:
        """Configurar el cliente, el prompt de sistema estático y el presupuesto."""
        if not math.isfinite(round_timeout) or round_timeout <= 0:
            raise ValueError("round_timeout debe ser finito y positivo.")
        self.client = client
        self.system_prompt = system_prompt
        self.round_timeout = round_timeout
        self.model_id = model_id

    def GenerateUtterance(
        self, request: pb.UtteranceRequest, context: grpc.ServicerContext
    ) -> Iterator[pb.UtteranceChunk]:
        """Validar la petición y emitir el stream con las guardas aplicadas."""
        self._validate(request, context)
        budget = self._budget(context)
        if budget <= MIN_BUDGET:
            context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, "sin presupuesto")
        messages = self._build_messages(request)
        max_words = request.config.max_words
        parts: list[str] = []
        emitted_chars = 0
        token_index = 0
        try:
            for raw_delta in self.client.stream_chat(
                messages,
                model_id=request.config.model_id,
                temperature=request.config.temperature,
                top_p=request.config.top_p,
                max_tokens=max_words * 3 + 8,
                timeout=budget,
            ):
                parts.append(raw_delta)
                candidate = normalize_text("".join(parts))
                if count_words(candidate) > max_words:
                    cut = cut_to_max_words(candidate, max_words)
                    if len(cut) > emitted_chars:
                        yield pb.UtteranceChunk(
                            text_delta=cut[emitted_chars:],
                            token_index=token_index,
                        )
                        token_index += 1
                    break
                if len(candidate) > emitted_chars:
                    yield pb.UtteranceChunk(
                        text_delta=candidate[emitted_chars:],
                        token_index=token_index,
                    )
                    token_index += 1
                    emitted_chars = len(candidate)
        except InferenceError as error:
            self._abort_for(error, context)
        yield pb.UtteranceChunk(is_final=True, text_delta="")

    def HealthCheck(
        self, request: pb.HealthRequest, context: grpc.ServicerContext
    ) -> pb.HealthResponse:
        """Reportar salud según configuración y disponibilidad de HF_TOKEN."""
        token = os.environ.get("HF_TOKEN", "")
        healthy = bool(token.startswith("hf_")) and self.client is not None
        model_id = self.model_id
        detail = "ok" if healthy else "falta HF_TOKEN válido o cliente no configurado"
        return pb.HealthResponse(healthy=healthy, model_id=model_id, detail=detail)

    def _validate(
        self, request: pb.UtteranceRequest, context: grpc.ServicerContext
    ) -> None:
        """Rechazar configuraciones inválidas antes de tocar el proveedor."""
        config = request.config
        checks = []
        if config.engine_backend != "hf-router":
            checks.append("engine_backend")
        if not config.model_id.strip():
            checks.append("model_id")
        if not request.prompt.strip():
            checks.append("prompt")
        if not config.system_prompt_version.strip():
            checks.append("system_prompt_version")
        if config.max_words < 1:
            checks.append("max_words")
        if not math.isfinite(config.temperature) or config.temperature < 0:
            checks.append("temperature")
        if not math.isfinite(config.top_p) or not 0 < config.top_p <= 1:
            checks.append("top_p")
        if checks:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "campos inválidos: " + ", ".join(checks),
            )

    def _budget(self, context: grpc.ServicerContext) -> float:
        """Calcular el presupuesto limitado por la ronda y el deadline de gRPC."""
        if hasattr(context, "time_remaining"):
            try:
                ctx_remaining = context.time_remaining()
            except Exception:  # noqa: BLE001 - contexto de prueba sin método real
                ctx_remaining = self.round_timeout
        else:
            ctx_remaining = self.round_timeout
        if not math.isfinite(ctx_remaining):
            ctx_remaining = self.round_timeout
        return max(0.0, min(self.round_timeout, ctx_remaining))

    def _build_messages(self, request: pb.UtteranceRequest) -> list[dict]:
        """Construir el prompt; el historial se simplifica a roles alternos.

        No podemos conocer el alias de la persona que genera, así que el
        historial se emite de forma determinista con el primer mensaje en rol
        'user', el segundo en 'assistant', y así sucesivamente. Es una
        simplificación honesta; no adivinamos identidades.
        """
        messages: list[dict] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        for index, message in enumerate(request.history):
            role = "user" if index % 2 == 0 else "assistant"
            messages.append({"role": role, "content": message.text})
        messages.append({"role": "user", "content": request.prompt})
        return messages

    def _abort_for(self, error: InferenceError, context: grpc.ServicerContext) -> None:
        """Traducir un fallo del cliente a un estado gRPC estable."""
        status = {
            "timeout": grpc.StatusCode.DEADLINE_EXCEEDED,
            "auth": grpc.StatusCode.UNAUTHENTICATED,
            "credits": grpc.StatusCode.RESOURCE_EXHAUSTED,
            "unavailable": grpc.StatusCode.UNAVAILABLE,
            "protocol": grpc.StatusCode.INTERNAL,
            "rejected": grpc.StatusCode.INTERNAL,
        }.get(error.kind, grpc.StatusCode.INTERNAL)
        context.abort(status, str(error))
