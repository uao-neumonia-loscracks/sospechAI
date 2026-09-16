"""Cliente R2 -> gRPC -> engine. Solo R1 conoce HTTP, el proveedor y HF_TOKEN."""

import math
from collections.abc import Iterator
from typing import Protocol

import grpc

from proto import impostor_pb2 as pb
from src.orchestrator.game import Game, GameState, RuleViolation


class EngineStub(Protocol):
    """Interfaz mínima compatible con el stub generado y dobles de prueba."""

    def GenerateUtterance(
        self, request: pb.UtteranceRequest, *, timeout: float
    ) -> Iterator[pb.UtteranceChunk]:
        """Devolver el stream de una única generación."""
        ...


class EngineFailure(RuntimeError):
    """Fallo con código estable, sin exponer detalles o credenciales del proveedor."""

    def __init__(self, code: str) -> None:
        """Conservar únicamente el código que puede registrar el orquestador."""
        self.code = code
        super().__init__(code)


class EngineClient:
    """Acumular el stream antes de publicar una respuesta completa y válida."""

    def __init__(self, stub: EngineStub, *, max_chars: int = 16384) -> None:
        """Recibir un stub inyectable y un límite de memoria por respuesta."""
        if max_chars < 1:
            raise ValueError("max_chars debe ser positivo.")
        self.stub = stub
        self.max_chars = max_chars

    def generate(self, request: pb.UtteranceRequest, *, timeout: float) -> str:
        """Aplicar un deadline a todo el RPC y descartar streams incompletos."""
        config = request.config
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("El timeout debe ser finito y positivo.")
        if config.engine_backend != "hf-router" or not config.model_id.strip():
            raise ValueError(
                "Define hf-router y el modelo solicitado antes de llamar al engine."
            )
        if not request.prompt.strip() or not config.system_prompt_version.strip():
            raise ValueError("Faltan la pregunta o la versión del prompt.")
        if config.max_words < 1:
            raise ValueError("El límite de palabras debe ser positivo.")
        if not math.isfinite(config.temperature) or config.temperature < 0:
            raise ValueError("La temperatura debe ser finita y no negativa.")
        if not math.isfinite(config.top_p) or not 0 < config.top_p <= 1:
            raise ValueError("top_p debe pertenecer a (0, 1].")
        call = None
        parts: list[str] = []
        total_chars = 0
        final_seen = False
        try:
            call = self.stub.GenerateUtterance(request, timeout=timeout)
            for chunk in call:
                if final_seen or (chunk.is_final and chunk.text_delta):
                    raise EngineFailure("engine_protocol")
                if chunk.is_final:
                    final_seen = True
                elif chunk.text_delta:
                    total_chars += len(chunk.text_delta)
                    if total_chars > self.max_chars:
                        raise EngineFailure("engine_protocol")
                    parts.append(chunk.text_delta)
            text = "".join(parts)
            if not final_seen or not text.strip():
                raise EngineFailure("engine_protocol")
            return text
        except grpc.RpcError as error:
            codes = {
                grpc.StatusCode.DEADLINE_EXCEEDED: "engine_timeout",
                grpc.StatusCode.UNAVAILABLE: "engine_unavailable",
            }
            raise EngineFailure(codes.get(error.code(), "engine_rejected")) from None
        finally:
            if call is not None and hasattr(call, "cancel"):
                call.cancel()


def apply_ai_turn(
    game: Game,
    alias: str,
    client: EngineClient,
    request: pb.UtteranceRequest,
    *,
    timeout: float = 8.0,
) -> bool:
    """Publicar una única respuesta o revelar una partida interrumpida por inferencia."""
    expected_round = game.round_number
    game.validate_ai_turn(alias, expected_round)
    if request.config.max_words != game.max_words:
        raise ValueError(
            "La petición debe usar el mismo límite de palabras que la partida."
        )
    remaining = game.remaining_time()
    if remaining == 0:
        game.interrupt("round_timeout")
        return False
    budget = min(timeout, remaining) if remaining is not None else timeout
    try:
        text = client.generate(request, timeout=budget)
    except EngineFailure as error:
        if game.state == GameState.ROUND and game.round_number == expected_round:
            game.interrupt(error.code)
        return False
    try:
        game.submit_message(alias, text, expected_round=expected_round)
    except RuleViolation:
        if game.state == GameState.ROUND and game.round_number == expected_round:
            game.interrupt("invalid_engine_response")
        return False
    return True
