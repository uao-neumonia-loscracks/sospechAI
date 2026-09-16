"""R1-5: partida E2E de consola contra el engine real en loopback.

Une por primera vez las tres piezas en una sola ejecución:
  - engine real (src.impostor_engine.serve) escuchando en gRPC,
  - orquestador real (src.orchestrator.engine_client + game),
  - texto generado por el modelo real vía la Inference API.

Modo de uso (el engine debe estar corriendo en :50051):
  uv run python -m scripts.e2e_real_engine --endpoint 127.0.0.1:50051

El flag regenerate_on_character_break queda en False (default de serve.py),
como decidió el equipo para el piloto.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import grpc

from proto import impostor_pb2 as pb
from proto import impostor_pb2_grpc as rpc
from src.orchestrator.engine_client import EngineClient, apply_ai_turn
from src.orchestrator.game import Game
from src.orchestrator.storage import save_practice_game

MODEL_ID = "Qwen/Qwen2.5-7B-Instruct:featherless-ai"
PROMPTS = (
    "Si se va la luz justo antes de entregar un trabajo, ¿qué harías?",
    "¿Qué comida escogerías después de una clase larga?",
)
HUMAN_RESPONSES = (
    (
        "Intentaría compartir internet desde el celular y avisarle al profesor.",
        "Me tocaría buscar una cafetería y terminar desde allá.",
        "Primero revisaría la batería, luego buscaría otra conexión disponible.",
    ),
    (
        "Una arepa con queso, tengo hambre desde hace rato.",
        "Yo pediría arroz con pollo y un juguito bien frío.",
        "Preferiría una comida caliente que pueda compartir con mis amigos.",
    ),
)


def make_request(prompt: str) -> pb.UtteranceRequest:
    """Construir la petición para el engine real con la persona del archivo."""
    return pb.UtteranceRequest(
        room_id="e2e-real",
        persona_id="p1",
        prompt=prompt,
        config=pb.GenerationConfig(
            temperature=0.9,
            top_p=0.9,
            max_words=15,
            system_prompt_version="v2",
            engine_backend="hf-router",
            model_id=MODEL_ID,
        ),
    )


def run_demo(*, endpoint: str) -> int:
    """Jugar dos rondas: humanos simulados y el impostor con el engine real."""
    channel = grpc.insecure_channel(endpoint)
    grpc.channel_ready_future(channel).result(timeout=5)
    stub = rpc.ImpostorEngineStub(channel)
    client = EngineClient(stub)
    game = Game(rounds=2, max_words=15, round_timeout=None)
    humans = [game.add_player() for _ in range(3)]
    impostor = game.add_player(is_ai=True)
    print("SospechAI | R1-5 E2E contra el engine REAL")
    print(f"Modelo solicitado: {MODEL_ID}")
    print("Regeneración por quiebre de personaje: OFF")
    game.start()
    for index, prompt in enumerate(PROMPTS):
        print(f"\nRONDA {index + 1}: {prompt}")
        for alias, text in zip(humans[:2], HUMAN_RESPONSES[index][:2], strict=True):
            accepted = game.submit_message(alias, text)
            print(f"{alias}: {accepted}")
        # El impostor genera con el modelo real; los humanos 1 y 2 ya hablaron.
        ok = apply_ai_turn(game, impostor, client, make_request(prompt), timeout=15.0)
        if not ok:
            return 1
        transcript = game.public_state()["messages"]
        print(f"{impostor}: {transcript[-1]['text']}")
        alias = humans[2]
        accepted = game.submit_message(alias, HUMAN_RESPONSES[index][2])
        print(f"{alias}: {accepted}")
    print("\nDISCUSION: revisa las respuestas anteriores.")
    game.open_voting()
    votes = ((humans[0], humans[2]), (humans[1], impostor), (humans[2], humans[1]))
    for voter, suspect in votes:
        game.cast_vote(voter, suspect)
    result = game.result()
    print(f"\nREVELACION: el impostor era {result['impostor_alias']}.")
    print(f"Puntajes: {result['scores']}")
    print(f"Tasa de detección: {result['tasa_deteccion']:.1%}")
    ai_messages = [m for m in result["transcript"] if m["is_ai"]]
    print("\nRespuestas generadas por el engine REAL:")
    for message in ai_messages:
        print(f"  Ronda {message['round_number']}: {message['text']}")
    if not ai_messages:
        print("ERROR: ninguna respuesta del engine real llegó a la revelación.")
        return 1
    database = Path("data/practice/partidas_e2e_real.sqlite3")
    session_id = save_practice_game(game, database)
    print(f"\nPartida guardada: {session_id} en {database}")
    print("CRITERIO R1-5 CUMPLIDO: la partida llegó a REVELACION.")
    return 0


def main() -> int:
    """Interpretar opciones y terminar sin traceback si se interrumpe la consola."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--endpoint", default="127.0.0.1:50051", help="Dirección gRPC del engine."
    )
    options = parser.parse_args()
    try:
        return run_demo(endpoint=options.endpoint)
    except (EOFError, KeyboardInterrupt, grpc.RpcError) as error:
        print(f"\nE2E interrumpida: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
