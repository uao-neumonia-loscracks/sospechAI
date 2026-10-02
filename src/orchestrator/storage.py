"""Guardar resultados completos de práctica, separados de datos experimentales."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.orchestrator.game import Game


def save_practice_game(game: Game, database: Path) -> str:
    """Persistir una partida terminada como simulación; devolver su identificador."""
    result = game.result()
    database.parent.mkdir(parents=True, exist_ok=True)
    session_id = str(uuid4())
    connection = sqlite3.connect(database)
    try:
        with connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS practice_games ("
                "id TEXT PRIMARY KEY, created_at TEXT NOT NULL, "
                "session_kind TEXT NOT NULL CHECK(session_kind = 'simulacion'), "
                "payload TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO practice_games VALUES (?, ?, ?, ?)",
                (
                    session_id,
                    datetime.now(timezone.utc).isoformat(),
                    "simulacion",
                    json.dumps(result, ensure_ascii=False),
                ),
            )
    finally:
        connection.close()
    return session_id


def append_game_event(
    database: Path,
    game_id: str,
    event_type: str,
    payload: dict,
    *,
    round_number: int | None = None,
) -> int:
    """Anexar un evento de ciclo de vida al flujo game_events; devolver su id.

    La tabla es append-only: solo se insertan filas nuevas, nunca se
    actualizan ni borran. ``round_number`` se toma de la carga cuando no se
    entrega explícito; los eventos de partida lo dejan en NULL.
    """
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    try:
        with connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS game_events ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "game_id TEXT NOT NULL, "
                "created_at TEXT NOT NULL, "
                "event_type TEXT NOT NULL "
                "CHECK (event_type IN ('game.started','round.started',"
                "'round.completed','game.closed')), "
                "round_number INTEGER NULL, "
                "payload TEXT NOT NULL)"
            )
            cursor = connection.execute(
                "INSERT INTO game_events "
                "(game_id, created_at, event_type, round_number, payload) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    game_id,
                    datetime.now(timezone.utc).isoformat(),
                    event_type,
                    (
                        round_number
                        if round_number is not None
                        else payload.get("round_number")
                    ),
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            row_id = int(cursor.lastrowid)
    finally:
        connection.close()
    return row_id
