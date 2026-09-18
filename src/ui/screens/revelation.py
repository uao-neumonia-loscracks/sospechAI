"""Pantalla de revelación terminal: contenido derivado por los helpers puros (D6).

ÚNICO lugar de la UI donde se renderiza `is_ai` (§9). La derivación vive en
`src/ui/revelation.py`; esta pantalla solo formatea lo derivado (UIF-19).
"""

import streamlit as st

from src.ui.revelation import revelation_summary
from src.ui.screens.context import ScreenContext


def render(ctx: ScreenContext) -> None:
    """Renderizar la revelación del impostor desde `ctx.snapshot.result`."""
    st.title("Revelación")
    if ctx.snapshot is None or ctx.snapshot.result is None:
        st.write("La revelación aún no está disponible.")
        return
    summary = revelation_summary(ctx.snapshot.result)
    st.subheader(f"El impostor era {summary['impostor']}")
    verdict, interruption = summary["verdict"]
    if interruption:
        st.warning(f"Partida interrumpida: {interruption}")
    elif verdict is True:
        st.success("¡La tripulación acertó!")
    else:
        st.error("El impostor escapó.")
    st.write("Votos")
    for vote in summary["votes"]:
        st.write(f"**{vote['voter']}** votó a **{vote['suspect']}**")
    st.write("Recuento")
    for count in summary["vote_counts"]:
        st.write(f"{count['suspect']}: **{count['count']}** voto(s)")
    st.write("Transcript")
    for message in summary["transcript"]:
        role = "impostor" if message["is_ai"] else "tripulación"
        st.write(
            f"**{message['alias']}** "
            f"(ronda {message['round_number']}, {role}): {message['text']}"
        )
    st.caption(summary["prompt_version"])
