"""Pruebas de reglas observables, privacidad de la vista y persistencia."""

import json
import sqlite3
from pathlib import Path

import pytest

from src.orchestrator.game import Game, GameState, RuleViolation
from src.orchestrator.storage import save_practice_game


def make_game(*, rounds: int = 1, max_words: int = 15) -> tuple[Game, list[str]]:
    """Preparar tres humanos y una IA para las pruebas."""
    game = Game(rounds=rounds, max_words=max_words)
    aliases = [game.add_player() for _ in range(3)]
    aliases.append(game.add_player(is_ai=True))
    return game, aliases


def reach_voting() -> tuple[Game, list[str]]:
    """Completar respuestas y discusión para probar las reglas de votación."""
    game, aliases = make_game()
    game.start()
    for alias in aliases:
        game.submit_message(alias, "Una respuesta de prueba.")
    game.open_voting()
    return game, aliases


@pytest.mark.parametrize("humans,has_ai", [(0, False), (1, True), (3, False)])
def test_start_requires_players_and_one_ai(humans: int, has_ai: bool) -> None:
    """Una sala incompleta no inicia ni abandona el lobby."""
    game = Game()
    for _ in range(humans):
        game.add_player()
    if has_ai:
        game.add_player(is_ai=True)
    with pytest.raises(RuleViolation):
        game.start()
    assert game.state == GameState.LOBBY


def test_second_ai_and_late_join_are_rejected() -> None:
    """No se admiten dos impostores ni participantes nuevos con la partida abierta."""
    game, _ = make_game()
    with pytest.raises(RuleViolation):
        game.add_player(is_ai=True)
    game.start()
    with pytest.raises(RuleViolation):
        game.add_player()
    assert len(game.public_state()["players"]) == 4


def test_rounds_wait_for_every_player_and_end_in_discussion() -> None:
    """El último mensaje de cada ronda produce una única transición válida."""
    game, aliases = make_game(rounds=2)
    game.start()
    for current_round in (1, 2):
        for alias in aliases[:-1]:
            game.submit_message(alias, "Respuesta de prueba.")
            assert game.round_number == current_round
            assert game.state == GameState.ROUND
        game.submit_message(aliases[-1], "Respuesta de la IA.")
    assert game.state == GameState.DISCUSSION
    assert len(game.public_state()["messages"]) == 8


@pytest.mark.parametrize("player_index", [0, 3])
@pytest.mark.parametrize("text", ["   \n", "una respuesta demasiado larga"])
def test_message_validation_is_symmetric(player_index: int, text: str) -> None:
    """Humanos e IA reciben el mismo rechazo para respuestas vacías o muy largas."""
    game, aliases = make_game(max_words=2)
    game.start()
    with pytest.raises(RuleViolation):
        game.submit_message(aliases[player_index], text)
    assert game.public_state()["messages"] == []


@pytest.mark.parametrize("player_index", [0, 3])
def test_spaces_and_unicode_are_normalized_for_every_player(player_index: int) -> None:
    """La normalización conserva las tildes y acepta el límite exacto de palabras."""
    game, aliases = make_game(max_words=2)
    game.start()
    assert (
        game.submit_message(aliases[player_index], "\tcafe\u0301   rico\n")
        == "café rico"
    )


def test_duplicate_message_does_not_advance_the_round() -> None:
    """Enviar dos veces no reemplaza la primera respuesta ni completa una ronda."""
    game, aliases = make_game()
    game.start()
    game.submit_message(aliases[0], "Primera respuesta.")
    with pytest.raises(RuleViolation):
        game.submit_message(aliases[0], "Segunda respuesta.")
    assert len(game.public_state()["messages"]) == 1
    assert game.state == GameState.ROUND


def test_actions_in_the_wrong_stage_are_rejected() -> None:
    """La API de dominio impide saltar de lobby a mensajes, votos o resultados."""
    game, aliases = make_game()
    for action in (
        lambda: game.submit_message(aliases[0], "Mensaje prematuro"),
        game.open_voting,
        lambda: game.cast_vote(aliases[0], aliases[1]),
        game.result,
    ):
        with pytest.raises(RuleViolation):
            action()
    assert game.state == GameState.LOBBY


def test_unregistered_player_cannot_send_a_message() -> None:
    """Una identidad desconocida no puede participar en la ronda."""
    game, _ = make_game()
    game.start()
    with pytest.raises(RuleViolation):
        game.submit_message("Jugador desconocido", "Hola")
    assert game.public_state()["messages"] == []


@pytest.mark.parametrize("voter,suspect", [(3, 0), (0, 0), (0, None), (None, 0)])
def test_invalid_votes_are_rejected(voter: int | None, suspect: int | None) -> None:
    """La IA, el autovoto y los alias desconocidos no generan votos válidos."""
    game, aliases = reach_voting()
    voter_alias = aliases[voter] if voter is not None else "Desconocido"
    suspect_alias = aliases[suspect] if suspect is not None else "Desconocido"
    with pytest.raises(RuleViolation):
        game.cast_vote(voter_alias, suspect_alias)
    assert game.public_state()["votes_received"] == 0


def test_duplicate_vote_and_early_reveal_are_rejected() -> None:
    """Un jugador no puede sumar dos votos ni obtener resultados incompletos."""
    game, aliases = reach_voting()
    game.cast_vote(aliases[0], aliases[3])
    with pytest.raises(RuleViolation):
        game.cast_vote(aliases[0], aliases[1])
    with pytest.raises(RuleViolation):
        game.result()
    view = game.public_state()
    assert view["votes_received"] == 1
    assert "impostor_alias" not in json.dumps(view)
    assert "is_ai" not in json.dumps(view)
    assert "votes" not in view
    assert "result" not in view


def test_last_vote_reveals_results_and_locks_the_game() -> None:
    """La revelación es automática y el resultado cerrado ya no acepta acciones."""
    game, aliases = reach_voting()
    game.cast_vote(aliases[0], aliases[3])
    game.cast_vote(aliases[1], aliases[3])
    game.cast_vote(aliases[2], aliases[1])
    result = game.public_state()["result"]
    assert game.state == GameState.REVEAL
    assert result["impostor_alias"] == aliases[3]
    assert result["scores"] == {aliases[0]: 1, aliases[1]: 1, aliases[2]: 0}
    assert result["tasa_deteccion"] == pytest.approx(2 / 3)
    assert sum(message["is_ai"] for message in result["transcript"]) == 1
    with pytest.raises(RuleViolation):
        game.cast_vote(aliases[2], aliases[3])
    with pytest.raises(RuleViolation):
        game.submit_message(aliases[0], "Mensaje tardío")


def test_public_snapshot_cannot_mutate_the_game() -> None:
    """Modificar una copia de la vista no cambia los participantes internos."""
    game, _ = make_game()
    view = game.public_state()
    view["players"].clear()
    view["messages"].append({"text": "Mensaje inventado"})
    assert len(game.public_state()["players"]) == 4
    assert game.public_state()["messages"] == []


def test_sqlite_round_trip_marks_the_session_as_simulated(tmp_path: Path) -> None:
    """El resultado completo se recupera desde disco con su naturaleza de práctica."""
    game, aliases = reach_voting()
    for alias in aliases[:3]:
        game.cast_vote(alias, aliases[3])
    database = tmp_path / "practica.sqlite3"
    session_id = save_practice_game(game, database)
    connection = sqlite3.connect(database)
    try:
        row = connection.execute(
            "SELECT session_kind, payload FROM practice_games WHERE id = ?",
            (session_id,),
        ).fetchone()
    finally:
        connection.close()
    assert row[0] == "simulacion"
    assert json.loads(row[1]) == game.result()


def test_unfinished_game_is_not_saved(tmp_path: Path) -> None:
    """No se crea una base de resultados para una partida que aún no termina."""
    game, _ = make_game()
    database = tmp_path / "incompleta.sqlite3"
    with pytest.raises(RuleViolation):
        save_practice_game(game, database)
    assert not database.exists()
