"""Vista de votación vacía y navegable (UIF-08). Contenido real en R3-2.

No renderiza controles ni ninguna clave de `result` (UIF-08 y UIF-10): la
votación y la revelación con contenido llegan con R3-2.
"""

import streamlit as st

from src.ui.screens.context import ScreenContext


def render(ctx: ScreenContext) -> None:
    """Renderizar la votación sin controles ni claves de `result` (UIF-08)."""
    st.title("Votación")
    if ctx.snapshot is not None and ctx.snapshot.state == "REVELACION":
        st.write("La partida terminó. La revelación se presenta con R3-2.")
    else:
        st.write("La votación y sus controles llegan con R3-2.")
