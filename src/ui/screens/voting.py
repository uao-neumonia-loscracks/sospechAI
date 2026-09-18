"""Votación real: selección de sospechoso con la autoridad del servidor (D3).

La UI excluye el alias propio (bloqueo visual), desactiva los controles tras un
204 («voto registrado; esperando al resto») y muestra el recuento SOLO desde la
instantánea (`votes_received`); nunca cuenta votos localmente (UIF-13). Todo
rechazo (`ApiError` de §8) se muestra sin presentar el voto como emitido
(UIF-14/15).
"""

import streamlit as st

from src.ui.screens.context import ScreenContext


def render(ctx: ScreenContext) -> None:
    """Renderizar la votación con controles reales contra `ctx.on_submit_vote`."""
    st.title("Votación")
    if ctx.snapshot is None or ctx.room_identity is None:
        st.write("La votación aún no ha cargado. Esperando la primera instantánea…")
        return
    suspects = [
        player for player in ctx.snapshot.players if player != ctx.room_identity.alias
    ]
    if st.session_state.get("vote_accepted", False):
        st.success("Voto registrado; esperando al resto.")
    elif suspects:
        suspect = st.selectbox("¿Quién creés que es el impostor?", suspects)
        vote_clicked = st.button("Votar", key="submit_vote")
        if vote_clicked and ctx.on_submit_vote is not None:
            ctx.on_submit_vote(suspect)
            if st.session_state.get("notice") is None:
                st.session_state["vote_accepted"] = True
    else:
        st.write("No hay sospechosos para votar todavía.")
    st.caption(f"Votos recibidos: {ctx.snapshot.votes_received}")
    notice = st.session_state.get("notice") or ctx.notice
    if notice:
        st.warning(notice)
