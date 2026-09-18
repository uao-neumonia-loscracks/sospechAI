"""Guardas de salida deterministas: normalización, conteo y corte de palabras.

Opera exclusivamente sobre texto ya normalizado o lo normaliza internamente.
No corta en medio de surrogates: opera sobre graphemas completos.
"""

# Reexportado para no romper a character_break ni a servicer, que importan el
# nombre desde este módulo. La implementación vive en src/common/text.py.
from src.common.text import normalize_text as normalize_text


def count_words(text: str) -> int:
    """Devolver el número de palabras en un texto normalizado."""
    normalized = normalize_text(text)
    if not normalized:
        return 0
    return len(normalized.split())


def cut_to_max_words(text: str, max_words: int) -> str:
    """Devolver como máximo las primeras max_words del texto normalizado.

    Opera sobre graphemas completos; no corta en medio de surrogates ni
    diacríticos compuestos (NFC asegura graphemas individuales).
    """
    normalized = normalize_text(text)
    if not normalized or max_words < 1:
        return ""
    words = normalized.split()
    return " ".join(words[:max_words])
