"""Pruebas AAA de los helpers puros de revelación (D6, tests/test_ui_revelation.py).

La derivación de la pantalla vive en `src/ui/revelation.py`: un módulo sin
`streamlit`, 1 función por bloque, `.get()` siempre, y degradación sin
excepción cuando `result` no trae claves (UIF-18, tolerancia v1.0).
"""

from src.ui.revelation import (
    group_verdict,
    prompt_version_text,
    revelation_impostor,
    revelation_summary,
    revelation_transcript,
    revelation_vote_counts,
    revelation_votes,
)


def _result_happy() -> dict:
    """Resultado de una partida válida terminada en REVELACION (solo Arrange)."""
    return {
        "state": "REVELACION",
        "impostor_alias": "Jugador 3",
        "votes": {"Jugador 1": "Jugador 3", "Jugador 2": "Jugador 1"},
        "vote_counts": {"Jugador 1": 1, "Jugador 3": 1},
        "valid_game": True,
        "interruption_reason": None,
        "tasa_deteccion": 0.5,
        "prompt_version": "v2",
        "transcript": [
            {"round_number": 1, "alias": "Jugador 1", "text": "Hola.", "is_ai": False},
            {
                "round_number": 1,
                "alias": "Jugador 3",
                "text": "Saludos.",
                "is_ai": True,
            },
        ],
    }


def test_revelacion_valida_revela_impostor() -> None:
    """El impostor se obtiene desde la clave autoritativa del resultado."""
    # Arrange
    result = _result_happy()

    # Act
    impostor = revelation_impostor(result)

    # Assert
    assert impostor == "Jugador 3"


def test_revelacion_valida_ordena_votos_por_quien_vota() -> None:
    """Los votos de `result.votes` se ordenan por alias ascendente para leerse bien."""
    # Arrange
    result = _result_happy()

    # Act
    votes = revelation_votes(result)

    # Assert
    assert votes == [
        {"voter": "Jugador 1", "suspect": "Jugador 3"},
        {"voter": "Jugador 2", "suspect": "Jugador 1"},
    ]


def test_revelacion_valida_ordena_recuentos_por_conteo_descendente() -> None:
    """`vote_counts` se ordena por conteo descendente y desempate alfabético."""
    # Arrange
    result = _result_happy()

    # Act
    counts = revelation_vote_counts(result)

    # Assert
    assert counts == [
        {"suspect": "Jugador 1", "count": 1},
        {"suspect": "Jugador 3", "count": 1},
    ]


def test_revelacion_valida_acierta_por_tasa_de_deteccion() -> None:
    """`tasa_deteccion > 0` se presenta como acierto del grupo (sin inventar tasa)."""
    # Arrange
    result = _result_happy()

    # Act
    verdict, interruption = group_verdict(result)

    # Assert
    assert verdict is True
    assert interruption is None


def test_partida_interrumpida_no_inventa_tasa_ni_acierto() -> None:
    """Con interrupción, el veredicto es `(None, interruption_reason)` y sin tasa."""
    # Arrange
    result = _result_happy()
    result["valid_game"] = False
    result["interruption_reason"] = "desconexion_masa"
    result["tasa_deteccion"] = None

    # Act
    verdict, interruption = group_verdict(result)

    # Assert
    assert verdict is None
    assert interruption == "desconexion_masa"


def test_transcript_preserva_la_marca_is_ai() -> None:
    """El transcript conserva `round_number`, `alias`, `text` e `is_ai` (§9)."""
    # Arrange
    result = _result_happy()

    # Act
    transcript = revelation_transcript(result)

    # Assert
    assert transcript == result["transcript"]
    assert any(message["is_ai"] for message in transcript)


def test_prompt_version_text_muestra_la_version_del_impostor() -> None:
    """Con `prompt_version` presente, el texto la muestra explícitamente."""
    # Arrange
    result = _result_happy()

    # Act
    text = prompt_version_text(result)

    # Assert
    assert text == "Prompt del impostor: v2"


def test_prompt_version_ausente_cae_a_texto_generico() -> None:
    """Servidor v1.0 sin `prompt_version`: la UI degrada a texto genérico (UIF-18)."""
    # Arrange
    result = _result_happy()
    del result["prompt_version"]

    # Act
    text = prompt_version_text(result)

    # Assert
    assert text == "Versión del prompt del impostor: no informada"


def test_claves_ausentes_no_explotan_los_helpers() -> None:
    """Cualquier clave faltante se degrada por `.get()` sin levantar excepción."""
    # Arrange
    result = {"state": "REVELACION"}

    # Act
    impostor = revelation_impostor(result)
    votes = revelation_votes(result)
    counts = revelation_vote_counts(result)
    verdict, interruption = group_verdict(result)
    transcript = revelation_transcript(result)
    summary = revelation_summary(result)

    # Assert
    assert impostor == ""
    assert votes == []
    assert counts == []
    assert verdict is None
    assert interruption is None
    assert transcript == []
    assert summary["impostor"] == ""


def test_revelation_summary_compone_todo_el_contenido() -> None:
    """`revelation_summary` agrega cada bloque en un único dict para la pantalla."""
    # Arrange
    result = _result_happy()

    # Act
    summary = revelation_summary(result)

    # Assert
    assert set(summary) == {
        "impostor",
        "votes",
        "vote_counts",
        "verdict",
        "transcript",
        "prompt_version",
    }
    assert summary["impostor"] == "Jugador 3"
    assert summary["prompt_version"] == "Prompt del impostor: v2"
