"""Sala de chat de la ronda: mensajes con alias y contador de palabras.

El contenido definitivo (mensajes, campo de entrada y bloqueo por `max_words`)
se completa en la fase 3; aquí solo se presenta el placeholder navegable.
"""

import streamlit as st

from src.ui.screens.context import ScreenContext


def render(ctx: ScreenContext) -> None:
    """Renderizar el placeholder de la sala de chat (UIF-04)."""
    st.title("Sala de chat")
    st.write("Placeholder del esqueleto: los mensajes llegan con la fase 2.")
