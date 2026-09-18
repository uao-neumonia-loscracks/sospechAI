"""Lobby de la partida: alias del servidor y cero datos personales (UIF-03).

Sin campos de nombre real ni correo y sin entrada de alias: el alias «Jugador N»
lo asigna el servidor y llega en `RoomIdentity.alias` (contrato §3).
"""

import streamlit as st

from src.ui.screens.context import ScreenContext


def render(ctx: ScreenContext) -> None:
    """Renderizar la entrada al lobby o la sala según la identidad de sesión."""
    st.title("Lobby")
    if ctx.room_identity is None:
        _render_entry(ctx)
    else:
        _render_room(ctx)


def _render_entry(ctx: ScreenContext) -> None:
    """Ofrecer crear una sala nueva o unirse por código."""
    if st.button("Crear nueva sala", key="create_room"):
        if ctx.on_create_room is not None:
            ctx.on_create_room()
    room_code = st.text_input("Código de sala", key="join_code")
    if st.button("Unirse a sala", key="join_room"):
        if room_code and ctx.on_join_room is not None:
            ctx.on_join_room(room_code)
    if ctx.notice:
        st.warning(ctx.notice)


def _render_room(ctx: ScreenContext) -> None:
    """Mostrar el alias, el código, la lista plana y el inicio para el anfitrión."""
    st.write(f"Tu alias: **{ctx.room_identity.alias}**")
    st.write(f"Código de sala: **{ctx.room_identity.room_code}**")
    if ctx.room_identity.alias == "Jugador 1":
        if st.button("Iniciar partida", key="start_room"):
            if ctx.on_start_room is not None:
                ctx.on_start_room()
    else:
        st.write("Esperando a que el anfitrión inicie la partida.")
    if ctx.snapshot is not None:
        st.write("Jugadores:")
        for alias in ctx.snapshot.players:
            st.write(f"- {alias}")
    if ctx.notice:
        st.warning(ctx.notice)
