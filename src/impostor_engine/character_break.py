"""Detector determinista de quiebres de personaje en un utterance generado.

Opera sin I/O sobre texto normalizado (conserva tildes y colapsa espacios)
y con coincidencia insensible a mayúsculas. Solo las afirmaciones en primera
persona rompen el personaje: mencionar "la IA" como sospechoso o "modelo" de
celular son usos legítimos del chat y nunca disparan un patrón. El estilo
deliberado de v3 (minúsculas, sin tildes, sin punto final) es imperfección,
nunca un detector.
"""

from __future__ import annotations

import re

from src.impostor_engine.guards import normalize_text

#: Patrones curados de quiebre de personaje: (etiqueta, frase literal).
#: Cada frase es un meta-claim en primera persona, nunca una palabra suelta;
#: "IA" o "modelo" solos jamás deben aparecer como patrón.
CHARACTER_BREAK_PATTERNS: tuple[tuple[str, str], ...] = (
    # Afirmar ser una inteligencia artificial.
    ("ai_claim", "soy una inteligencia artificial"),
    ("ai_claim", "soy inteligencia artificial"),
    ("ai_claim", "soy una ia"),
    ("ai_claim", "soy un ia"),
    ("ai_claim", "soy la ia"),
    # Afirmar ser un modelo de lenguaje, incluida la forma "como modelo".
    ("model_claim", "soy un modelo de lenguaje"),
    ("model_claim", "como modelo de lenguaje"),
    ("model_claim", "como un modelo de lenguaje"),
    ("model_claim", "soy un modelo de ia"),
    # Afirmar ser un asistente virtual.
    ("assistant_claim", "soy un asistente"),
    ("assistant_claim", "soy tu asistente"),
    # Afirmar ser un robot.
    ("robot_claim", "soy un robot"),
    ("robot_claim", "soy el robot"),
    # Afirmar ser un programa informático.
    ("program_claim", "soy un programa"),
    # Negar tener emociones.
    ("no_emotions", "no tengo emociones"),
    ("no_emotions", "no siento emociones"),
    # Mencionar la propia programación (con y sin tilde, estilo v3).
    ("programming_mention", "mi programacion"),
    ("programming_mention", "mi programación"),
    # Mencionar las instrucciones recibidas.
    ("instructions_mention", "mis instrucciones"),
    # Rechazo que delata el meta-prompt ("no puedo decir eso").
    ("meta_refusal", "no puedo decir eso"),
    # Revelar que no es humano.
    ("non_human", "no soy humano"),
    ("non_human", "no soy una persona"),
    # Revelar que es una máquina (con y sin tilde, estilo v3).
    ("machine_claim", "soy una maquina"),
    ("machine_claim", "soy una máquina"),
)

_COMPILED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (label, re.compile(rf"\b{re.escape(phrase)}\b"))
    for label, phrase in CHARACTER_BREAK_PATTERNS
)


def detect_character_break(text: str) -> list[str]:
    """Devolver las etiquetas de los quiebres presentes; [] si el texto está limpio.

    Normaliza (NFC + colapso de espacios) y compara en minúsculas. Las
    coincidencias respetan límites de palabra para no acertar prefijos o
    sufijos de otras palabras ("iatrógena" no contiene "ia" como palabra).
    """
    lowered = normalize_text(text).lower()
    if not lowered:
        return []
    matched: list[str] = []
    for label, pattern in _COMPILED_PATTERNS:
        if pattern.search(lowered) is not None and label not in matched:
            matched.append(label)
    return matched
