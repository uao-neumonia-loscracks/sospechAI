"""Lógica pura de conteo de palabras de la UI (D5, UIF-04/11).

Sin imports de Streamlit: solo estimación local del conteo, con la autoridad
del límite siempre en el orquestador (UIF-05).
"""

# Reexportado para no romper a sources/fake, que importa el nombre desde este
# módulo. La implementación vive en src/common/text.py.
from src.common.text import normalize_text as normalize_text


def count_words(text: str) -> int:
    """Estimar las palabras como las contaría el dominio (NFC + espacios unificados)."""

    return len(normalize_text(text).split())


def within_limit(words: int, max_words: int) -> bool:
    """Aceptar el envío solo si el conteo local no supera el límite del orquestador."""
    return words <= max_words
