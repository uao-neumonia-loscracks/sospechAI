"""Lobby de la partida: alias del servidor y cero datos personales (esqueleto).

El contenido definitivo (alias «Jugador N», unirse por código y `start`) se
completa en la fase 3; aquí solo se presenta el placeholder navegable.
"""

import streamlit as st

from src.ui.screens.context import ScreenContext


def render(ctx: ScreenContext) -> None:
    """Renderizar el placeholder del lobby (UIF-03)."""
    st.title("Lobby")
    st.write("Placeholder del esqueleto: el alias lo asigna el servidor.")
