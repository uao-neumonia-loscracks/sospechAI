"""Pantalla de consentimiento obligatorio previo al lobby (esqueleto R3-1).

El contenido definitivo (los dos avisos fijos y la aceptación) se completa en la
fase 3; aquí solo se presenta el placeholder navegable del esqueleto.
"""

import streamlit as st

from src.ui.screens.context import ScreenContext


def render(ctx: ScreenContext) -> None:
    """Renderizar el placeholder de consentimiento previo al lobby (UIF-02)."""
    st.title("Consentimiento informado")
    st.write(
        "Placeholder del esqueleto: sin aceptar el consentimiento no se avanza "
        "al lobby."
    )
