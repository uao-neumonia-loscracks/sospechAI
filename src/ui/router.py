"""Lógica pura del router de pantallas (sin dependencia de Streamlit).

Deriva la pantalla activa desde el estado de sesión y el estado publicado por el
orquestador, y define la frecuencia de polling por estado. Los valores de cable
del estado (`LOBBY`, `RONDA`, `DISCUSION`, `VOTACION`, `REVELACION`) se copian
del contrato `docs/CONTRATO_UI_ORQUESTADOR.md` §§5 y 14.1.
"""

from enum import StrEnum

GAME_STATES = ("RONDA", "DISCUSION", "VOTACION")
GAME_POLL_SECONDS = 1.0
IDLE_POLL_SECONDS = 2.5


class Screen(StrEnum):
    """Pantallas del flujo de partida (UIF-09); REVELACION es terminal (UIF-16)."""

    CONSENT = "consent"
    LOBBY = "lobby"
    CHAT = "chat"
    VOTING = "voting"
    REVELATION = "revelation"


def resolve_screen(*, consent_agreed: bool, state: str | None) -> Screen:
    """Derivar la pantalla activa a partir de la sesión y del estado del contrato.

    El consentimiento es un gate: mientras no se acepte, no se abandona la
    pantalla de consentimiento, sea cual sea el estado (UIF-02).
    """
    if not consent_agreed:
        return Screen.CONSENT
    if state in (None, "LOBBY"):
        return Screen.LOBBY
    if state in ("RONDA", "DISCUSION"):
        return Screen.CHAT
    if state == "REVELACION":
        return Screen.REVELATION
    return Screen.VOTING


def poll_interval_seconds(state: str | None) -> float:
    """Frecuencia de polling del contrato §14.1 según el estado de partida."""
    if state in GAME_STATES:
        return GAME_POLL_SECONDS
    return IDLE_POLL_SECONDS
