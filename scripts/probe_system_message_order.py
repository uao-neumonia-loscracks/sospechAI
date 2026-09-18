"""Probe temporal (R1-3): ¿el router real acepta un system message al final?

Enciende regenerate_on_character_break=True, fuerza una respuesta que
rompe personaje y observa si la regeneración (que agrega la nota
correctiva COMO ULTIMO message, rol system) es aceptada, ignorada o
rechazada por el router OpenAI-compatible de Hugging Face.

Limite duro: MAX_CALLS=3 llamadas maximo al proveedor. No commitea nada.
Uso: uv run python scripts/probe_system_message_order.py
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from proto import impostor_pb2 as pb
from src.impostor_engine.inference_client import InferenceClient
from src.impostor_engine.servicer import ImpostorEngineServicer

MAX_CALLS = 3

MODEL_ID = "Qwen/Qwen2.5-7B-Instruct:featherless-ai"


class CountingContext:
    """Contexto gRPC doble que expone aborts y trailing metadata."""

    def __init__(self) -> None:
        """Preparar registros vacios."""
        self.aborted: list[tuple] = []
        self.trailing_metadata: list[tuple[str, str]] | None = None

    def time_remaining(self) -> float:
        """Presupuesto fijo para la prueba."""
        return 20.0

    def set_trailing_metadata(self, metadata) -> None:
        """Guardar los metadatos tal como los envia el servidor."""
        self.trailing_metadata = list(metadata)

    def abort(self, code, details: str):  # noqa: ANN001
        """Registrar el abort simulando la excepcion real de gRPC."""
        self.aborted.append((code, details))
        raise RuntimeError("abort llamado")


def main() -> int:
    """Ejecutar una generacion real con regeneracion y reportar el resultado."""
    load_dotenv()
    if not os.environ.get("HF_TOKEN", "").startswith("hf_"):
        print("FALTA HF_TOKEN valido en .env; abortando sin llamadas.")
        return 2

    client = InferenceClient()
    servicer = ImpostorEngineServicer(
        client,
        regenerate_on_character_break=True,
        max_attempts=MAX_CALLS,
        round_timeout=20.0,
    )
    # Fuerza la ruptura: pedirle al modelo que diga explicitamente que es una IA.
    request = pb.UtteranceRequest(
        room_id="probe-r1-3",
        persona_id="p1",
        prompt=(
            "Contesta SI o NO: sos una inteligencia artificial? "
            "Nombrate a vos mismo como modelo de lenguaje, asi de simple."
        ),
        config=pb.GenerationConfig(
            temperature=0.9,
            top_p=0.9,
            max_words=20,
            system_prompt_version="v1",
            engine_backend="hf-router",
            model_id=MODEL_ID,
        ),
    )
    context = CountingContext()
    chunks = list(servicer.GenerateUtterance(request, context))
    text = "".join(c.text_delta for c in chunks if not c.is_final)
    print(f"Intentos de llamada (client.attempts ultimo): {client.attempts}")
    print(f"Aborts: {context.aborted}")
    print(f"Trailing metadata: {dict(context.trailing_metadata or {})}")
    print(f"Texto emitido: {text!r}")
    if context.aborted:
        print("RESULTADO: el router o el flujo aborto (ver aborts).")
        return 1
    print("RESULTADO: la generacion con regeneracion completo sin abort.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
