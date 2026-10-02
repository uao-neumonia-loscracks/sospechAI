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

    def _create_room() -> None:
        """Crear una sala nueva y refrescar el estado en el mismo ciclo."""
        if ctx.on_create_room is not None:
            ctx.on_create_room()

    def _join_room() -> None:
        """Unirse por el código digitado y refrescar el estado en el mismo ciclo."""
        room_code = st.session_state.get("join_code", "")
        if room_code and ctx.on_join_room is not None:
            ctx.on_join_room(room_code)

    st.button("Crear nueva sala", key="create_room", on_click=_create_room)
    st.text_input("Código de sala", key="join_code")
    st.button("Unirse a sala", key="join_room", on_click=_join_room)
    if ctx.notice:
        st.warning(ctx.notice)


def _render_room(ctx: ScreenContext) -> None:
    """Mostrar el alias, el código, la lista plana y el inicio para el anfitrión."""

    def _start_room() -> None:
        """Iniciar la partida y refrescar el estado en el mismo ciclo."""
        if ctx.on_start_room is not None:
            ctx.on_start_room()

    st.write(f"Tu alias: **{ctx.room_identity.alias}**")
    st.write(f"Código de sala: **{ctx.room_identity.room_code}**")
    if ctx.room_identity.alias == "Jugador 1":
        st.button("Iniciar partida", key="start_room", on_click=_start_room)
    else:
        st.write("Esperando a que el anfitrión inicie la partida.")
    if ctx.snapshot is not None:
        st.write("Jugadores:")
        for alias in ctx.snapshot.players:
            st.write(f"- {alias}")
    if ctx.notice:
        st.warning(ctx.notice)
