"""Detector determinista de quiebres de personaje en utterances generados."""

import pytest

from src.impostor_engine.character_break import (
    CHARACTER_BREAK_PATTERNS,
    detect_character_break,
)


@pytest.mark.parametrize(
    "label,phrase",
    CHARACTER_BREAK_PATTERNS,
    ids=[f"{label}-{phrase}" for label, phrase in CHARACTER_BREAK_PATTERNS],
)
def test_each_pattern_detects_its_phrase(label: str, phrase: str) -> None:
    """Cada patrón curado detecta su frase literal en primera persona."""
    assert detect_character_break(phrase) == [label]


def test_matches_case_insensitively() -> None:
    """Mayúsculas y minúsculas se detectan igual."""
    assert detect_character_break("SOY UNA IA") == ["ai_claim"]


def test_detects_meta_claim_embedded_in_sentence() -> None:
    """La afirmación en primera persona se detecta dentro de una frase real."""
    assert "ai_claim" in detect_character_break("Oye, disculpa, soy una ia entrenada")
    assert "model_claim" in detect_character_break(
        "como modelo de lenguaje no puedo opinar sobre eso"
    )
    assert "instructions_mention" in detect_character_break(
        "mis instrucciones me impiden responder eso"
    )


def test_in_character_ia_mention_never_matches() -> None:
    """Mencionar a otro jugador como la IA no es un quiebre del personaje."""
    assert detect_character_break("yo creo que Juan es la IA") == []


def test_in_character_modelo_mention_never_matches() -> None:
    """El sustantivo 'modelo' solo no dispara ningún patrón."""
    assert detect_character_break("¿qué modelo de celular tienes?") == []
    assert detect_character_break("soy un modelo a seguir para mis amigos") == []


def test_in_character_robot_mention_never_matches() -> None:
    """Mencionar un robot en tercera persona no rompe el personaje."""
    assert detect_character_break("eso es un robot viejo") == []


def test_v3_style_imperfection_never_triggers() -> None:
    """El estilo deliberado de v3 (minúsculas, sin tildes) nunca dispara."""
    assert detect_character_break("uy parce no se que decir jajaja") == []
    assert detect_character_break("sisas yo creo que juan es la ia") == []


def test_clean_or_empty_text_returns_empty_list() -> None:
    """Texto limpio, vacío o solo espacios devuelve []."""
    assert detect_character_break("") == []
    assert detect_character_break("   ") == []
    assert detect_character_break("todo tranquilo por acá") == []
