"""Sala de chat de la ronda: mensajes, contador en vivo y bloqueo local (UIF-04/05).

La conversación mostrada es siempre `ctx.snapshot.messages`; la UI nunca agrega
mensajes localmente (UIF-05). El bloqueo deshabilita el envío sobre `max_words`;
la autoridad del límite sigue siendo el orquestador.
"""

import streamlit as st

from src.ui.screens.context import ScreenContext
from src.ui.words import count_words, within_limit


def render(ctx: ScreenContext) -> None:
    """Renderizar el chat con contador en vivo y bloqueo sobre `max_words`."""
    st.title("Sala de chat")
    if ctx.snapshot is None:
        st.write("La partida aún no ha cargado. Esperando la primera instantánea…")
        return
    max_words = ctx.snapshot.max_words

    def _send() -> None:
        """Enviar el borrador y limpiarlo solo si el servidor lo aceptó."""
        draft = st.session_state.get("draft", "")
        if ctx.on_submit_message is None:
            return
        ctx.on_submit_message(draft)
        if st.session_state.get("notice") is None:
            st.session_state["draft"] = ""

    draft = st.text_input("Tu mensaje", key="draft")
    words = count_words(draft)
    allowed = within_limit(words, max_words)
    st.caption(f"{words} / {max_words} palabras")
    if not allowed:
        st.error(f"El mensaje supera el límite de {max_words} palabras.")
    st.button(
        "Enviar",
        key="send_message",
        disabled=not allowed,
        on_click=_send,
    )
    _render_messages(ctx)
    notice = st.session_state.get("notice") or ctx.notice
    if notice:
        st.warning(notice)


def _render_messages(ctx: ScreenContext) -> None:
    """Mostrar la pregunta de la ronda y los mensajes por alias desde el orquestador."""
    st.write(f"Ronda {ctx.snapshot.round_number}")
    if ctx.snapshot.round_prompt is not None and ctx.snapshot.state in (
        "RONDA",
        "DISCUSION",
    ):
        st.subheader(ctx.snapshot.round_prompt)
    for message in ctx.snapshot.messages:
        st.write(f"**{message.alias}**: {message.text}")
