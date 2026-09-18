"""Lógica pura de conteo de palabras de la UI (D5, UIF-04/11).

Sin imports de Streamlit: solo estimación local del conteo, con la autoridad
del límite siempre en el orquestador (UIF-05).
"""

import unicodedata


def normalize_text(text: str) -> str:
    """Unificar espacios y representación Unicode como el dominio (NFC)."""
    return " ".join(unicodedata.normalize("NFC", text).split())


def count_words(text: str) -> int:
    """Estimar las palabras como las contaría el dominio (NFC + espacios unificados)."""

    return len(normalize_text(text).split())


def within_limit(words: int, max_words: int) -> bool:
    """Aceptar el envío solo si el conteo local no supera el límite del orquestador."""
    return words <= max_words
