"""Conducir una partida completa de bots hasta la revelación y registrarla."""

from pathlib import Path

from src.orchestrator.engine_client import EngineClient, EngineStub, apply_ai_turn
from src.orchestrator.game import Game, GameState, RuleViolation
from src.orchestrator.storage import save_practice_game
from tests.harness.bots import (
    PROMPTS,
    HarnessConfig,
    SimulatedClock,
    bot_reply,
    build_request,
    choose_votes,
)


def _play_round(
    game: Game,
    config: HarnessConfig,
    round_index: int,
    impostor: str,
    client: EngineClient,
) -> bool:
    """Jugar una ronda; devolver False si la partida se interrumpió.

    El impostor habla en la mitad del turno, como un jugador más. Los bots
    humanos responden en orden de alias con su frase fija.
    """
    prompt = PROMPTS[round_index]
    humans = [alias for alias in game.public_state()["players"] if alias != impostor]
    turn_order = humans[: len(humans) // 2] + [impostor] + humans[len(humans) // 2 :]
    for alias in turn_order:
        if alias == impostor:
            request = build_request(config, prompt, game)
            if not apply_ai_turn(game, impostor, client, request):
                return False
            continue
        try:
            game.submit_message(alias, bot_reply(humans.index(alias), round_index))
        except RuleViolation:
            if game.state == GameState.REVEAL:
                return False
            raise
    return True


def run_game(
    config: HarnessConfig,
    stub: EngineStub,
    *,
    clock: SimulatedClock | None = None,
) -> Game:
    """Jugar una partida de `config.bots` bots y un impostor hasta REVELACION."""
    clock = clock or SimulatedClock()
    game = Game(
        rounds=config.rounds,
        max_words=config.max_words,
        round_timeout=config.round_timeout,
        clock=clock,
    )
    humans = [game.add_player() for _ in range(config.bots)]
    impostor = game.add_player(is_ai=True)
    game.start()
    client = EngineClient(stub)
    for round_index in range(config.rounds):
        clock.advance(config.response_delay)
        if not _play_round(game, config, round_index, impostor, client):
            return game
    game.open_voting()
    candidates = game.public_state()["players"]
    for voter, suspect in choose_votes(
        humans, candidates, config.vote_mode, config.seed
    ).items():
        game.cast_vote(voter, suspect)
    return game


def run_and_save(
    config: HarnessConfig, stub: EngineStub, database: Path
) -> tuple[dict, str]:
    """Jugar una partida, guardarla en SQLite y devolver resultado e identificador."""
    game = run_game(config, stub)
    session_id = save_practice_game(game, database)
    return game.result(), session_id
