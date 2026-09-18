"""Entry point de Streamlit: router por `session_state` y composición de pantallas.

Arranque canónico: `uv run streamlit run src/ui/app.py`. Streamlit ejecuta este
archivo como script e inserta `src/ui/` en `sys.path`; para que los imports
absolutos `src.ui.*` resuelvan, se añade la raíz del proyecto antes de importar.
No se usa `st.navigation` ni la carpeta `pages/` (UIF-09).
"""

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.ui import api  # noqa: E402 (el bootstrap de sys.path lo precede a propósito)

SESSION_KEYS = ("consent_accepted", "room_identity", "snapshot", "notice")


def _run_api(state: Any, action: Callable[..., Any], *args: Any) -> Any:
    """Ejecutar una acción del facade y registrar el aviso de error en la sesión."""

    try:
        result = action(*args)
        state["notice"] = None
        return result
    except api.ApiError as error:
        state["notice"] = error.message
        return None


def _accept_consent(state: Any) -> None:
    """Registrar la aceptación; el avance lo decide `resolve_screen` (UIF-02)."""

    state["consent_accepted"] = True
    state["notice"] = None


def _create_room(state: Any) -> None:
    """Crear una sala nueva y cargar su primera instantánea."""

    identity = _run_api(state, api.create_room)
    if identity is None:
        return
    state["room_identity"] = identity
    state["snapshot"] = _run_api(
        state, api.get_state, identity.room_code, identity.session_token
    )


def _join_room(state: Any, room_code: str) -> None:
    """Unirse a una sala por código y cargar su instantánea (contrato §4)."""

    identity = _run_api(state, api.join_room, room_code)
    if identity is None:
        return
    state["room_identity"] = identity
    state["snapshot"] = _run_api(
        state, api.get_state, identity.room_code, identity.session_token
    )


def _mutate(state: Any, action: Callable[..., Any], *args: Any) -> None:
    """Aplicar una mutación y refrescar la instantánea si el servidor la aceptó."""

    identity = state.get("room_identity")
    if identity is None:
        return
    _run_api(state, action, identity.room_code, identity.session_token, *args)
    if state.get("notice") is not None:
        return
    state["snapshot"] = _run_api(
        state, api.get_state, identity.room_code, identity.session_token
    )


def _start_room(state: Any) -> None:
    """Iniciar la partida (solo anfitrión)."""

    _mutate(state, api.start)


def _submit_message(state: Any, text: str) -> None:
    """Enviar un mensaje de ronda y refrescar la conversación (UIF-05)."""

    _mutate(state, api.submit_message, text)


def _snapshot_sig(snapshot: Any) -> tuple[Any, ...] | None:
    """Resumen observable de la instantánea para decidir si re-renderizar."""

    if snapshot is None:
        return None
    return (
        snapshot.state,
        snapshot.round_number,
        tuple(snapshot.players),
        snapshot.messages,
        snapshot.votes_received,
        snapshot.remaining_seconds,
    )


def main() -> None:
    """Componer pantallas con el facade `api.py` y el polling no bloqueante (UIF-06/07)."""

    import streamlit as st

    from src.ui.router import Screen, poll_interval_seconds, resolve_screen
    from src.ui.screens import (
        ScreenContext,
        render_chat,
        render_consent,
        render_lobby,
        render_voting,
    )

    state = st.session_state
    for key in SESSION_KEYS:
        if key not in state:
            state[key] = False if key == "consent_accepted" else None

    screen = resolve_screen(
        consent_agreed=state["consent_accepted"],
        state=getattr(state.get("snapshot"), "state", None),
    )
    renderers = {
        Screen.CONSENT: render_consent,
        Screen.LOBBY: render_lobby,
        Screen.CHAT: render_chat,
        Screen.VOTING: render_voting,
    }
    context = ScreenContext(
        room_identity=state.get("room_identity"),
        snapshot=state.get("snapshot"),
        notice=state.get("notice"),
        on_accept_consent=lambda: _accept_consent(state),
        on_create_room=lambda: _create_room(state),
        on_join_room=lambda room_code: _join_room(state, room_code),
        on_start_room=lambda: _start_room(state),
        on_submit_message=lambda text: _submit_message(state, text),
    )
    renderers[screen](context)

    identity = state.get("room_identity")
    if identity is not None:
        interval = poll_interval_seconds(getattr(state.get("snapshot"), "state", None))

        @st.fragment(run_every=interval)
        def poll_snapshot() -> None:
            """Refrescar la instantánea sin bloquear la interacción (UIF-06/14.1)."""

            snapshot = _run_api(
                state, api.get_state, identity.room_code, identity.session_token
            )
            if snapshot is None:
                return
            if _snapshot_sig(snapshot) != _snapshot_sig(state.get("snapshot")):
                state["snapshot"] = snapshot
                st.rerun(scope="app")

        poll_snapshot()


if __name__ == "__main__":
    main()
