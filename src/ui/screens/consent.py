"""Pantalla de consentimiento obligatorio previo al lobby (UIF-02).

El avance lo decide `resolve_screen` en `src/ui/app.py`, nunca esta pantalla:
aceptar solo registra la aceptación.
"""

import streamlit as st

from src.ui.screens.context import ScreenContext


def render(ctx: ScreenContext) -> None:
    """Renderizar los avisos fijos y el botón de aceptación (UIF-02)."""
    st.title("Consentimiento informado")
    st.write("Un participante de esta partida puede ser un modelo de lenguaje.")
    st.write("La conversación se registra con fines de investigación.")
    if st.button("Acepto participar", key="accept_consent"):
        if ctx.on_accept_consent is not None:
            ctx.on_accept_consent()
