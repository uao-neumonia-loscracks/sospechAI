"""Normalización de texto compartida por el orquestador, el engine y la UI.

AGENTS.md exige que la normalización viva en UNA sola función: humanos y modelo
pasan por ella, y dos rutas distintas sesgarían el experimento. Este módulo es
esa única implementación; los tres servicios importan de aquí.

Es código puro y sin estado, así que respeta la regla de `src/common/`: no
conoce rondas, votos, jugadores, puntajes, partidas, gRPC ni HTTP.
"""

import unicodedata


def normalize_text(text: str) -> str:
    """Unificar espacios y representación Unicode, conservando tildes y estilo.

    Aplica NFC y colapsa todo tipo de espacio —incluidos los no separables— a
    un único espacio. No toca tildes, mayúsculas, puntuación ni registro.
    """
    return " ".join(unicodedata.normalize("NFC", text).split())
