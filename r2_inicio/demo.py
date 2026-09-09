"""Ejecutar una partida local para aprender el flujo de R2."""

import argparse
from pathlib import Path

from r2_inicio.game import Game, RuleViolation
from r2_inicio.storage import save_practice_game

PROMPTS = (
    "¿Qué harías si se va la luz justo antes de entregar un trabajo?",
    "¿Qué comida escogerías después de una clase larga?",
)
AUTO_RESPONSES = (
    "Yo buscaría una opción cerca y les escribiría a mis compañeros.",
    "Una empanada con ají y un jugo de maracuyá.",
)
SCRIPTED_RESPONSES = (
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


def run_demo(*, automatic: bool, database: Path) -> None:
    """Ejecutar dos rondas con una persona en consola y tres participantes simulados."""
    game = Game(rounds=2, max_words=15)
    aliases = [game.add_player() for _ in range(3)]
    aliases.append(game.add_player(is_ai=True))
    print("SospechAI | Inicio de R2")
    print("MODO DE PRÁCTICA: respuestas simuladas; no es un experimento con personas.")
    print(
        "Controlas a Jugador 1. El resto usa respuestas de ejemplo, sin un modelo real."
    )
    print("Reglas provisionales: 2 rondas, 15 palabras y un voto por humano.\n")
    game.start()
    for index, prompt in enumerate(PROMPTS):
        print(f"RONDA {index + 1}: {prompt}")
        while True:
            text = AUTO_RESPONSES[index] if automatic else input("Tu respuesta: ")
            try:
                accepted = game.submit_message(aliases[0], text)
                print(f"{aliases[0]}: {accepted}")
                break
            except RuleViolation as error:
                if automatic:
                    raise
                print(error)
        for alias, text in zip(aliases[1:], SCRIPTED_RESPONSES[index], strict=True):
            accepted = game.submit_message(alias, text)
            print(f"{alias}: {accepted}")
        print()
    print("DISCUSION: revisa las respuestas anteriores.")
    if not automatic:
        input("Presiona Enter para abrir la votación: ")
    game.open_voting()
    while True:
        choice = "4" if automatic else input("¿A quién señalas? Escribe 2, 3 o 4: ")
        try:
            game.cast_vote(aliases[0], f"Jugador {choice.strip()}")
            break
        except RuleViolation as error:
            if automatic:
                raise
            print(error)
    game.cast_vote(aliases[1], aliases[3])
    game.cast_vote(aliases[2], aliases[1])
    result = game.result()
    print(f"\nREVELACION: el impostor era {result['impostor_alias']}.")
    print(f"Puntajes: {result['scores']}")
    print(
        f"Proporción de votos correctos en esta simulación: {result['tasa_deteccion']:.1%}"
    )
    print("Respuestas del impostor:")
    for message in result["transcript"]:
        if message["is_ai"]:
            print(f"  Ronda {message['round_number']}: {message['text']}")
    session_id = save_practice_game(game, database)
    print(f"Partida de práctica guardada: {session_id}")
    print(f"Base de datos: {database}")


def main() -> int:
    """Interpretar opciones y terminar sin traceback si se interrumpe la consola."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--auto", action="store_true", help="Simular también tus entradas."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(__file__).parent / "salidas" / "partidas_demo.sqlite3",
        help="Destino de SQLite para las partidas de práctica.",
    )
    options = parser.parse_args()
    try:
        run_demo(automatic=options.auto, database=options.db)
    except (EOFError, KeyboardInterrupt):
        print("\nPráctica interrumpida. Solo se guardan las partidas terminadas.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
