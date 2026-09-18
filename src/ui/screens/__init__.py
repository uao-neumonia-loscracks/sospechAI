"""Pantallas del flujo de partida (esqueleto navegable R3-1)."""

from src.ui.screens.chat import render as render_chat
from src.ui.screens.consent import render as render_consent
from src.ui.screens.context import ScreenContext
from src.ui.screens.lobby import render as render_lobby
from src.ui.screens.revelation import render as render_revelation
from src.ui.screens.voting import render as render_voting

__all__ = [
    "ScreenContext",
    "render_chat",
    "render_consent",
    "render_lobby",
    "render_revelation",
    "render_voting",
]
