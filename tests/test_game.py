"""Pruebas de reglas observables, privacidad de la vista y persistencia."""

import json
import sqlite3
from pathlib import Path

import pytest

from src.orchestrator.game import DEFAULT_PROMPTS, Game, GameState, RuleViolation
from src.orchestrator.storage import save_practice_game


class Clock:
    """Reloj determinista con `now` mutable y `advance(segundos)` para pruebas."""

    def __init__(self, now: float = 0.0) -> None:
        """Fijar el instante inicial elegido por la prueba."""
        self.now = now

    def __call__(self) -> float:
        """Devolver el instante actual sin esperar tiempo real."""
        return self.now

    def advance(self, seconds: float) -> None:
        """Sumar segundos al instante actual."""
        self.now += seconds


@pytest.fixture
def clock() -> Clock:
    """Reloj de prueba para conducir vencimientos sin pausas reales."""
    return Clock()


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


def reach_voting_with_two_humans() -> tuple[Game, list[str]]:
    """Abrir la votación con dos humanos y una IA para probar las abstenciones."""
    game = Game(rounds=1)
    aliases = [game.add_player() for _ in range(2)]
    aliases.append(game.add_player(is_ai=True))
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


def test_explicit_abstention_completes_voting() -> None:
    """Abstenerse cuenta como acción: revela sin bloquear la partida."""
    game, aliases = reach_voting_with_two_humans()
    impostor = aliases[2]
    game.cast_vote(aliases[0], impostor)
    game.cast_vote(aliases[1], None)
    assert game.state == GameState.REVEAL
    result = game.result()
    assert result["valid_game"] is True
    assert result["votes"] == {aliases[0]: impostor, aliases[1]: None}
    assert result["tasa_deteccion"] == pytest.approx(1.0)


def test_abstention_is_excluded_from_detection_metrics() -> None:
    """La abstención no aparece en el conteo de votos ni en los aciertos."""
    game, aliases = reach_voting_with_two_humans()
    impostor = aliases[2]
    game.cast_vote(aliases[0], impostor)
    game.cast_vote(aliases[1], None)
    result = game.result()
    assert result["vote_counts"] == {impostor: 1}
    assert result["scores"] == {aliases[0]: 1}
    assert aliases[1] not in result["vote_counts"]
    assert aliases[1] not in result["scores"]


def test_all_humans_abstain_is_valid_without_detection_data() -> None:
    """Una partida válida sin votos escrutables no fabrica una tasa de detección."""
    game, aliases = reach_voting_with_two_humans()
    game.cast_vote(aliases[0], None)
    game.cast_vote(aliases[1], None)
    assert game.state == GameState.REVEAL
    result = game.result()
    assert result["valid_game"] is True
    assert result["votes"] == {aliases[0]: None, aliases[1]: None}
    assert result["vote_counts"] == {}
    assert result["scores"] == {}
    assert result["tasa_deteccion"] is None


def test_abstention_never_tallies_for_the_impostor() -> None:
    """El conteo del impostor solo suma votos reales, nunca abstenciones."""
    game, aliases = reach_voting()
    impostor = aliases[3]
    game.cast_vote(aliases[0], impostor)
    game.cast_vote(aliases[1], aliases[2])
    game.cast_vote(aliases[2], None)
    assert game.state == GameState.REVEAL
    result = game.result()
    assert result["vote_counts"] == {impostor: 1, aliases[2]: 1}
    assert None not in result["vote_counts"]
    assert result["scores"] == {aliases[0]: 1, aliases[1]: 0}
    assert result["tasa_deteccion"] == pytest.approx(0.5)


def test_public_snapshot_cannot_mutate_the_game() -> None:
    """Modificar una copia de la vista no cambia los participantes internos."""
    game, _ = make_game()
    view = game.public_state()
    view["players"].clear()
    view["messages"].append({"text": "Mensaje inventado"})
    assert len(game.public_state()["players"]) == 4
    assert game.public_state()["messages"] == []


def test_round_prompt_is_none_before_start() -> None:
    """En LOBBY no hay pregunta de ronda vigente (round_number 0)."""
    # Arrange
    game = Game()

    # Act
    view = game.public_state()

    # Assert
    assert view["round_number"] == 0
    assert view["round_prompt"] is None


def test_round_prompt_exposes_current_round_question() -> None:
    """Cada ronda publica su pregunta vigente para los humanos."""
    # Arrange
    game, aliases = make_game(rounds=2)

    # Act
    game.start()
    first = game.public_state()["round_prompt"]
    for alias in aliases:
        game.submit_message(alias, "Respuesta de prueba.")
    second = game.public_state()["round_prompt"]

    # Assert
    assert first == DEFAULT_PROMPTS[0]
    assert second == DEFAULT_PROMPTS[1]


def test_custom_prompts_are_used_for_each_round() -> None:
    """El constructor permite inyectar las preguntas de la partida."""
    # Arrange
    game = Game(rounds=2, prompts=("¿Pregunta A?", "¿Pregunta B?"))
    aliases = [game.add_player() for _ in range(3)]
    aliases.append(game.add_player(is_ai=True))

    # Act
    game.start()
    first = game.public_state()["round_prompt"]
    for alias in aliases:
        game.submit_message(alias, "Respuesta de prueba.")
    second = game.public_state()["round_prompt"]

    # Assert
    assert first == "¿Pregunta A?"
    assert second == "¿Pregunta B?"


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


def reach_discussion_with_clock(clock: Clock) -> tuple[Game, list[str]]:
    """Completar las respuestas para probar el vencimiento de la discusión."""
    game = Game(rounds=1, round_timeout=60.0, clock=clock)
    aliases = [game.add_player() for _ in range(3)]
    aliases.append(game.add_player(is_ai=True))
    game.start()
    for alias in aliases:
        game.submit_message(alias, "Una respuesta de prueba.")
    return game, aliases


def open_voting_with_clock(clock: Clock, *, humans: int = 3) -> tuple[Game, list[str]]:
    """Abrir la votación con un reloj controlado y el número de humanos pedido."""
    game = Game(rounds=1, round_timeout=60.0, clock=clock)
    aliases = [game.add_player() for _ in range(humans)]
    aliases.append(game.add_player(is_ai=True))
    game.start()
    for alias in aliases:
        game.submit_message(alias, "Una respuesta de prueba.")
    game.open_voting()
    return game, aliases


# ---------------------------------------------------------------------------
# Vencimientos por fase y quorum (R2-4)
# ---------------------------------------------------------------------------


def test_discussion_deadline_auto_advances_with_fresh_deadline(clock: Clock) -> None:
    """Una discusión sin actividad avanza a votación con una ventana nueva."""
    game, _ = reach_discussion_with_clock(clock)
    assert game.state == GameState.DISCUSSION
    assert game.remaining_time() == pytest.approx(60.0)
    clock.advance(60.0)
    game.check_expiration()
    assert game.state == GameState.VOTING
    assert game.remaining_time() == pytest.approx(60.0)
    assert "result" not in game.public_state()


def test_silent_disconnect_deadline_abstains_with_quorum_held(clock: Clock) -> None:
    """Una humana que no vota queda absuelta por vencimiento sin invalidar la partida."""
    game, aliases = open_voting_with_clock(clock)
    impostor = aliases[3]
    game.cast_vote(aliases[0], impostor)
    game.cast_vote(aliases[1], aliases[2])
    clock.advance(60.0)
    game.check_expiration()
    assert game.state == GameState.REVEAL
    result = game.result()
    assert result["valid_game"] is True
    assert result["interruption_reason"] is None
    assert result["votes"] == {
        aliases[0]: impostor,
        aliases[1]: aliases[2],
        aliases[2]: None,
    }
    assert result["tasa_deteccion"] == pytest.approx(0.5)


def test_voting_deadline_quorum_lost_closes_invalid(clock: Clock) -> None:
    """Menos de dos presentes al vencimiento cierran la partida como inválida."""
    game, _ = open_voting_with_clock(clock, humans=2)
    clock.advance(60.0)
    game.check_expiration()
    assert game.state == GameState.REVEAL
    result = game.result()
    assert result["interruption_reason"] == "quorum_lost"
    assert result["valid_game"] is False
    assert result["scores"] == {}
    assert result["tasa_deteccion"] is None


def test_round_expiry_quorum_lost_when_below_minimum(clock: Clock) -> None:
    """El quorum precede al vencimiento de ronda cuando falta una humana."""
    game = Game(rounds=1, round_timeout=60.0, clock=clock)
    aliases = [game.add_player() for _ in range(2)]
    aliases.append(game.add_player(is_ai=True))
    game.start()
    game.submit_message(aliases[0], "Solo una humana responde.")
    clock.advance(60.0)
    game.check_expiration()
    assert game.state == GameState.REVEAL
    assert game.result()["interruption_reason"] == "quorum_lost"


def test_exactly_two_present_humans_hold_quorum(clock: Clock) -> None:
    """Dos presentes en el límite sostienen el quorum y cierran la partida válida."""
    game, aliases = open_voting_with_clock(clock)
    impostor = aliases[3]
    game.cast_vote(aliases[0], impostor)
    game.cast_vote(aliases[1], None)
    clock.advance(60.0)
    game.check_expiration()
    assert game.state == GameState.REVEAL
    result = game.result()
    assert result["valid_game"] is True
    assert result["interruption_reason"] is None
    assert result["votes"] == {
        aliases[0]: impostor,
        aliases[1]: None,
        aliases[2]: None,
    }


def test_post_deadline_vote_is_rejected_after_sweep(clock: Clock) -> None:
    """Un voto posterior al vencimiento no entra en la fase ya cerrada."""
    game, aliases = open_voting_with_clock(clock, humans=2)
    clock.advance(60.0)
    with pytest.raises(RuleViolation):
        game.cast_vote(aliases[0], aliases[2])
    assert game.state == GameState.REVEAL
    assert game.result()["interruption_reason"] == "quorum_lost"


def test_no_deadline_game_never_expires() -> None:
    """Una partida sin ventana no expira en ninguna fase temporal."""
    game = Game(rounds=2, round_timeout=None)
    aliases = [game.add_player() for _ in range(3)]
    aliases.append(game.add_player(is_ai=True))
    game.start()
    game.check_expiration()
    assert game.state == GameState.ROUND
    for alias in aliases[:3]:
        game.submit_message(alias, "Una respuesta de prueba.")
    game.submit_message(aliases[3], "Respuesta de la IA.")
    assert game.state == GameState.ROUND
    game.check_expiration()
    assert game.state == GameState.ROUND
    for alias in aliases[:3]:
        game.submit_message(alias, "Una respuesta de prueba.")
    game.submit_message(aliases[3], "Respuesta de la IA.")
    assert game.state == GameState.DISCUSSION
    game.check_expiration()
    assert game.state == GameState.DISCUSSION
    game.open_voting()
    game.check_expiration()
    assert game.state == GameState.VOTING


# ---------------------------------------------------------------------------
# Eventos de ciclo de vida (R2-4)
# ---------------------------------------------------------------------------


class Sink:
    """Sumidero de eventos respaldado por lista para inspeccionar emisiones."""

    def __init__(self) -> None:
        """Preparar la lista de eventos emitidos por la partida."""
        self.events: list[tuple[str, dict]] = []

    def __call__(self, event_type: str, payload: dict) -> None:
        """Registrar una emisión del dominio."""
        self.events.append((event_type, payload))


@pytest.fixture
def sink() -> Sink:
    """Sumidero de eventos para verificar el flujo de ciclo de vida."""
    return Sink()


def make_game_with_sink(
    clock: Clock, *, rounds: int = 1
) -> tuple[Game, list[str], Sink]:
    """Preparar tres humanos, una IA y un sumidero de eventos para las pruebas."""
    sink = Sink()
    game = Game(rounds=rounds, round_timeout=60.0, clock=clock, event_sink=sink)
    aliases = [game.add_player() for _ in range(3)]
    aliases.append(game.add_player(is_ai=True))
    return game, aliases, sink


def test_full_game_event_stream_order(clock: Clock) -> None:
    """Una partida completa emite el flujo de eventos en orden y una sola vez."""
    game, aliases, sink = make_game_with_sink(clock, rounds=2)
    game.start()
    for current_round in (1, 2):
        for alias in aliases[:-1]:
            game.submit_message(alias, "Respuesta de prueba.")
        game.submit_message(aliases[-1], "Respuesta de la IA.")
    game.open_voting()
    for alias in aliases[:3]:
        game.cast_vote(alias, aliases[3])
    assert game.state == GameState.REVEAL
    assert sink.events == [
        ("game.started", {"rounds": 2, "max_words": 15}),
        ("round.started", {"round_number": 1}),
        ("round.completed", {"round_number": 1}),
        ("round.started", {"round_number": 2}),
        ("round.completed", {"round_number": 2}),
        (
            "game.closed",
            {
                "reason": "completed",
                "valid_game": True,
                "tasa_deteccion": 1.0,
                "rounds": 2,
            },
        ),
    ]
    event_types = [event_type for event_type, _ in sink.events]
    assert event_types.count("game.started") == 1
    assert event_types.count("game.closed") == 1


def test_close_events_are_exactly_once_under_repeated_ticks(clock: Clock) -> None:
    """Los ticks repetidos tras la revelación no duplican eventos de cierre."""
    game, aliases, sink = make_game_with_sink(clock)
    game.start()
    for alias in aliases:
        game.submit_message(alias, "Una respuesta de prueba.")
    game.open_voting()
    for alias in aliases[:3]:
        game.cast_vote(alias, aliases[3])
    assert game.state == GameState.REVEAL
    before = len(sink.events)
    for _ in range(5):
        game.check_expiration()
    assert len(sink.events) == before
    assert [event_type for event_type, _ in sink.events].count("game.closed") == 1


def test_close_reason_mapping(clock: Clock) -> None:
    """El motivo del cierre distingue interrupción, votación completa y vencimiento."""
    # Interrupción técnica: el motivo es el código de interrupción y la partida es inválida.
    game, aliases, sink = make_game_with_sink(clock)
    game.start()
    game.interrupt("engine_unavailable")
    assert game.state == GameState.REVEAL
    assert sink.events[-1][0] == "game.closed"
    assert sink.events[-1][1] == {
        "reason": "engine_unavailable",
        "valid_game": False,
        "tasa_deteccion": None,
        "rounds": 1,
    }

    # Votación completa: motivo "completed", partida válida.
    game, aliases, sink = make_game_with_sink(clock)
    game.start()
    for alias in aliases:
        game.submit_message(alias, "Una respuesta de prueba.")
    game.open_voting()
    for alias in aliases[:3]:
        game.cast_vote(alias, aliases[3])
    assert game.state == GameState.REVEAL
    assert sink.events[-1][0] == "game.closed"
    assert set(sink.events[-1][1]) == {
        "reason",
        "valid_game",
        "tasa_deteccion",
        "rounds",
    }
    assert sink.events[-1][1]["reason"] == "completed"
    assert sink.events[-1][1]["valid_game"] is True
    assert sink.events[-1][1]["tasa_deteccion"] == pytest.approx(1.0)

    # Vencimiento de votación con quorum: motivo "voting_timeout", partida válida.
    game, aliases, sink = make_game_with_sink(clock)
    game.start()
    for alias in aliases:
        game.submit_message(alias, "Una respuesta de prueba.")
    game.open_voting()
    game.cast_vote(aliases[0], aliases[3])
    game.cast_vote(aliases[1], aliases[2])
    clock.advance(60.0)
    game.check_expiration()
    assert game.state == GameState.REVEAL
    assert sink.events[-1][0] == "game.closed"
    assert set(sink.events[-1][1]) == {
        "reason",
        "valid_game",
        "tasa_deteccion",
        "rounds",
    }
    assert sink.events[-1][1]["reason"] == "voting_timeout"
    assert sink.events[-1][1]["valid_game"] is True
    assert sink.events[-1][1]["tasa_deteccion"] == pytest.approx(0.5)


def test_sink_is_optional(clock: Clock) -> None:
    """Sin sumidero la partida no gestiona eventos y mantiene idéntico comportamiento."""
    game, aliases = open_voting_with_clock(clock)
    impostor = aliases[3]
    game.cast_vote(aliases[0], impostor)
    game.cast_vote(aliases[1], aliases[2])
    game.cast_vote(aliases[2], aliases[1])
    assert game.event_sink is None
    result = game.public_state()["result"]
    assert game.state == GameState.REVEAL
    assert result["valid_game"] is True
    assert result["interruption_reason"] is None
    assert result["votes"] == {
        aliases[0]: impostor,
        aliases[1]: aliases[2],
        aliases[2]: aliases[1],
    }
