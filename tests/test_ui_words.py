"""Pruebas AAA del contador de palabras y el límite de la UI (UIF-04, UIF-11).

Cubren la tarea 2.1 (D5): texto vacío, acento NFC como lo contaría el dominio
(``src/orchestrator/game.py:49``), múltiples espacios y puntuación, y el bloqueo
local sobre ``max_words = 15``.
"""

import pytest

from src.ui.words import count_words, within_limit


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", 0),
        ("cafe\u0301", 1),
        ("Hola,   ¿cómo   estás?", 3),
        ("uno   dos     tres", 3),
        ("Hola, ¿cómo estás?", 3),
    ],
)
def test_count_words_replica_la_normalizacion_del_dominio(
    text: str, expected: int
) -> None:
    """Contar con NFC y espacios unificados como la referencia del dominio."""
    # Arrange
    # (entrada y esperado parametrizados)

    # Act
    actual = count_words(text)

    # Assert
    assert actual == expected


def test_count_words_con_texto_vacio_devuelve_cero() -> None:
    """Un texto vacío no tiene palabras que bloquear el envío (UIF-04)."""
    # Arrange
    text = ""

    # Act
    actual = count_words(text)

    # Assert
    assert actual == 0


def test_within_limit_acepta_exactamente_en_el_maximo() -> None:
    """El límite es inclusivo: 15 palabras pasan con max_words = 15."""
    # Arrange
    words = 15
    max_words = 15

    # Act
    allowed = within_limit(words, max_words)

    # Assert
    assert allowed is True


def test_within_limit_bloquea_sobre_el_maximo() -> None:
    """Con 16 palabras y max_words = 15 el envío queda bloqueado (UIF-04)."""
    # Arrange
    words = 16
    max_words = 15

    # Act
    allowed = within_limit(words, max_words)

    # Assert
    assert allowed is False


def test_within_limit_acepta_por_debajo_del_maximo() -> None:
    """Un conteo por debajo del límite no bloquea el envío."""
    # Arrange
    words = 8
    max_words = 15

    # Act
    allowed = within_limit(words, max_words)

    # Assert
    assert allowed is True
