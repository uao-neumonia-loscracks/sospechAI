"""Pruebas del arnés de bots (A10): partida completa, determinismo y registro."""

import json
import sqlite3
from pathlib import Path

import pytest

from tests.harness.__main__ import main
from tests.harness.bots import (
    IMPOSTOR_BANK,
    HarnessConfig,
    ScriptedEngineStub,
    choose_votes,
)
from tests.harness.runner import run_and_save, run_game


def test_five_bots_and_impostor_reach_reveal() -> None:
    """Cinco bots y un impostor terminan solos una partida válida."""
    # Arrange
    config = HarnessConfig(bots=5, rounds=2)
    stub = ScriptedEngineStub()

    # Act
    result = run_game(config, stub).result()

    # Assert
    assert result["state"] == "REVELACION"
    assert result["valid_game"] is True
    assert len(result["votes"]) == 5
    assert [m["is_ai"] for m in result["transcript"]].count(True) == 2
    assert len(stub.requests) == 2


def test_same_config_produces_identical_games() -> None:
    """Dos corridas con la misma configuración dan el mismo resultado."""
    # Arrange
    config = HarnessConfig(bots=4, vote_mode="random", seed=7)

    # Act
    first = run_game(config, ScriptedEngineStub()).result()
    second = run_game(config, ScriptedEngineStub()).result()

    # Assert
    assert first == second


def test_fixed_votes_go_to_next_player_without_self_vote() -> None:
    """En modo fijo cada bot vota al siguiente participante, en ciclo."""
    # Arrange
    voters = ["Jugador 1", "Jugador 2", "Jugador 3"]
    candidates = voters + ["Jugador 4"]

    # Act
    votes = choose_votes(voters, candidates, "fixed", seed=0)

    # Assert
    assert votes == {
        "Jugador 1": "Jugador 2",
        "Jugador 2": "Jugador 3",
        "Jugador 3": "Jugador 4",
    }


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_random_votes_never_target_the_voter(seed: int) -> None:
    """El voto al azar nunca es un autovoto y solo apunta a participantes."""
    # Arrange
    voters = [f"Jugador {n}" for n in range(1, 6)]
    candidates = voters + ["Jugador 6"]

    # Act
    votes = choose_votes(voters, candidates, "random", seed=seed)

    # Assert
    assert all(voter != suspect for voter, suspect in votes.items())
    assert set(votes.values()) <= set(candidates)


def test_slow_bots_expire_the_round_and_skip_the_engine() -> None:
    """Si los bots tardan más que la ventana, la partida se interrumpe sin tasa.

    Sin humanos que respondan en la ronda, el cierre por ventana es quorum_lost.
    """
    # Arrange
    config = HarnessConfig(bots=3, round_timeout=5.0, response_delay=5.0)
    stub = ScriptedEngineStub()

    # Act
    result = run_game(config, stub).result()

    # Assert
    assert result["valid_game"] is False
    assert result["interruption_reason"] == "quorum_lost"
    assert result["tasa_deteccion"] is None
    assert stub.requests == []


def test_impostor_request_carries_public_history() -> None:
    """En la segunda ronda el engine recibe los mensajes ya publicados."""
    # Arrange
    config = HarnessConfig(bots=2, rounds=2)
    stub = ScriptedEngineStub()

    # Act
    run_game(config, stub)

    # Assert
    first, second = stub.requests
    assert len(first.history) == 1
    assert len(second.history) == 4
    assert second.config.system_prompt_version == "v2"
    assert second.config.max_words == 15


def test_scripted_engine_closes_with_empty_final_chunk() -> None:
    """El engine doble respeta el contrato: deltas y un final vacío al cierre."""
    # Arrange
    stub = ScriptedEngineStub()

    # Act
    chunks = list(stub.GenerateUtterance(None, timeout=1.0))

    # Assert
    assert chunks[-1].is_final and chunks[-1].text_delta == ""
    assert "".join(c.text_delta for c in chunks[:-1]) == IMPOSTOR_BANK[0]


def test_game_is_recorded_in_sqlite(tmp_path: Path) -> None:
    """La partida terminada queda registrada con su resultado completo."""
    # Arrange
    database = tmp_path / "arnes.sqlite3"

    # Act
    result, session_id = run_and_save(HarnessConfig(), ScriptedEngineStub(), database)

    # Assert
    connection = sqlite3.connect(database)
    try:
        row = connection.execute(
            "SELECT payload FROM practice_games WHERE id = ?", (session_id,)
        ).fetchone()
    finally:
        connection.close()
    assert json.loads(row[0]) == result


@pytest.mark.parametrize(
    "overrides",
    [{"bots": 1}, {"rounds": 0}, {"rounds": 9}, {"response_delay": -1}],
)
def test_invalid_config_is_rejected(overrides: dict) -> None:
    """Configuraciones que no pueden jugar se rechazan al construirlas."""
    # Arrange
    arguments = dict(overrides)

    # Act
    with pytest.raises(ValueError) as captured:
        HarnessConfig(**arguments)

    # Assert
    assert str(captured.value) != ""


def test_cli_plays_and_records_a_game(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`python -m tests.harness --bots 5` termina con código 0 y deja registro."""
    # Arrange
    database = tmp_path / "cli.sqlite3"

    # Act
    exit_code = main(["--bots", "5", "--db", str(database)])

    # Assert
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Estado final: REVELACION" in output
    assert database.exists()
