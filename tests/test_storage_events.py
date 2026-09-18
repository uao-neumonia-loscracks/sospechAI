"""Persistencia append-only del flujo de eventos de ciclo de vida.

Verifica el adaptador ``append_game_event`` sobre sqlite temporal: los
eventos se anexan en orden con ids crecientes, el CHECK cerrado rechaza tipos
desconocidos, la carga de cierre conserva exactamente las cuatro claves
pactadas con R1, la columna ``round_number`` se extrae de la carga, el CHECK
no puede desincronizarse de los tipos del dominio, y ``practice_games``
convive intacto en la misma base.
"""

import json
import re
import sqlite3
from pathlib import Path

import pytest

from src.orchestrator.game import GAME_EVENT_TYPES, EventSink, Game
from src.orchestrator.storage import append_game_event, save_practice_game


def _recorder(database: Path, code: str) -> EventSink:
    """Construir el sumidero que anexa cada emisión al flujo de la sala."""

    def sink(event_type: str, payload: dict) -> None:
        append_game_event(database, code, event_type, payload)

    return sink


def _play_full_game(code: str, database: Path) -> None:
    """Jugar una partida completa con el sumidero persistiendo en la base."""
    game = Game(rounds=1, event_sink=_recorder(database, code))
    aliases = [game.add_player() for _ in range(3)]
    aliases.append(game.add_player(is_ai=True))
    game.start()
    for alias in aliases:
        game.submit_message(alias, "Una respuesta de prueba.")
    game.open_voting()
    for alias in aliases[:3]:
        game.cast_vote(alias, aliases[3])


def _finished_game() -> Game:
    """Partida terminada en REVELACION con tres humanos y una IA."""
    game = Game(rounds=1)
    aliases = [game.add_player() for _ in range(3)]
    aliases.append(game.add_player(is_ai=True))
    game.start()
    for alias in aliases:
        game.submit_message(alias, "Una respuesta de prueba.")
    game.open_voting()
    for alias in aliases[:3]:
        game.cast_vote(alias, aliases[3])
    return game


def _rows(database: Path) -> list[tuple[int, str, str, str, object, str]]:
    """Leer las filas de game_events ordenadas por id con sus seis columnas."""
    connection = sqlite3.connect(database)
    try:
        return list(
            connection.execute(
                "SELECT id, game_id, created_at, event_type, round_number, payload "
                "FROM game_events ORDER BY id"
            )
        )
    finally:
        connection.close()


def test_game_events_are_append_only_with_increasing_ids(tmp_path: Path) -> None:
    """Los eventos de dos partidas se acumulan en orden de inserción."""
    database = tmp_path / "events.sqlite3"
    _play_full_game("ROOM1", database)
    _play_full_game("ROOM2", database)
    rows = _rows(database)
    ids = [row[0] for row in rows]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))
    assert [row[1] for row in rows] == ["ROOM1"] * 4 + ["ROOM2"] * 4
    assert [row[3] for row in rows] == [
        "game.started",
        "round.started",
        "round.completed",
        "game.closed",
    ] * 2


def test_unknown_event_type_is_rejected_by_check(tmp_path: Path) -> None:
    """Un tipo de evento fuera del conjunto cerrado no puede anexarse."""
    database = tmp_path / "events.sqlite3"
    with pytest.raises(sqlite3.IntegrityError):
        append_game_event(database, "ROOM1", "exploded", {"rounds": 1})
    assert _rows(database) == []


def test_close_payload_stores_exact_four_keys(tmp_path: Path) -> None:
    """La carga de cierre persiste exactamente las cuatro claves pactadas."""
    database = tmp_path / "events.sqlite3"
    _play_full_game("ROOM1", database)
    closed = [row for row in _rows(database) if row[3] == "game.closed"]
    assert len(closed) == 1
    stored = json.loads(closed[0][5])
    assert set(stored) == {"reason", "valid_game", "tasa_deteccion", "rounds"}
    assert stored == {
        "reason": "completed",
        "valid_game": True,
        "tasa_deteccion": 1.0,
        "rounds": 1,
    }


def test_round_number_extracted_from_payload_and_column(tmp_path: Path) -> None:
    """La columna round_number se llena desde la carga y queda nula sin ella."""
    database = tmp_path / "events.sqlite3"
    extracted = append_game_event(
        database, "ROOM1", "round.started", {"round_number": 2}
    )
    game_event = append_game_event(
        database, "ROOM1", "game.started", {"rounds": 2, "max_words": 15}
    )
    overridden = append_game_event(
        database, "ROOM1", "round.completed", {"round_number": 1}, round_number=3
    )
    rows = _rows(database)
    assert [row[0] for row in rows] == [extracted, game_event, overridden]
    assert rows[0][4] == 2
    assert rows[1][4] is None
    assert rows[2][4] == 3


def test_event_type_check_matches_domain_game_event_types(tmp_path: Path) -> None:
    """El CHECK de la tabla no puede desincronizarse de los tipos del dominio."""
    database = tmp_path / "events.sqlite3"
    append_game_event(database, "ROOM1", "game.started", {"rounds": 1, "max_words": 15})
    connection = sqlite3.connect(database)
    try:
        (create_sql,) = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'game_events'"
        ).fetchone()
    finally:
        connection.close()
    match = re.search(r"event_type IN \(([^)]*)\)", create_sql)
    assert match is not None
    literal_types = re.findall(r"'([^']+)'", match.group(1))
    assert literal_types == list(GAME_EVENT_TYPES)


def test_practice_games_survive_alongside_game_events(tmp_path: Path) -> None:
    """practice_games y game_events conviven en la misma base sin tocarse."""
    database = tmp_path / "mixed.sqlite3"
    game = _finished_game()
    first = save_practice_game(game, database)
    _play_full_game("ROOM1", database)
    second = save_practice_game(game, database)
    connection = sqlite3.connect(database)
    try:
        practice = list(
            connection.execute(
                "SELECT id, session_kind, payload FROM practice_games ORDER BY id"
            )
        )
        event_types = list(
            connection.execute("SELECT event_type FROM game_events ORDER BY id")
        )
    finally:
        connection.close()
    assert [row[0] for row in practice] == [first, second]
    assert [row[1] for row in practice] == ["simulacion", "simulacion"]
    assert json.loads(practice[0][2]) == game.result()
    assert [row[0] for row in event_types] == [
        "game.started",
        "round.started",
        "round.completed",
        "game.closed",
    ]
