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
