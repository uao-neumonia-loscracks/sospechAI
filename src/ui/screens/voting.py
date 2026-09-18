"""Vista de votación vacía y navegable (esqueleto R3-1; contenido en R3-2).

No muestra controles de votación ni resultados: la lógica de votación y la
revelación con contenido son R3-2 (UIF-08).
"""

import streamlit as st

from src.ui.screens.context import ScreenContext


def render(ctx: ScreenContext) -> None:
    """Renderizar la vista de votación sin controles ni resultados (UIF-08)."""
    st.title("Votación")
    st.write("Placeholder navegable: la votación y la revelación llegan con R3-2.")
