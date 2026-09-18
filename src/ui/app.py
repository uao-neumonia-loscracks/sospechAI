"""Entry point de Streamlit: router por `session_state` y composición de pantallas.

Arranque canónico: `uv run streamlit run src/ui/app.py`. Streamlit ejecuta este
archivo como script e inserta `src/ui/` en `sys.path`; para que los imports
absolutos `src.ui.*` resuelvan, se añade la raíz del proyecto antes de importar.
No se usa `st.navigation` ni la carpeta `pages/` (UIF-09).
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

SESSION_KEYS = ("consent_accepted", "room_identity", "snapshot")


def main() -> None:
    """Derivar la pantalla activa de la sesión y renderizar su placeholder."""
    import streamlit as st

    from src.ui.router import Screen, resolve_screen
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

    snapshot = state["snapshot"]
    published_state = getattr(snapshot, "state", None)
    screen = resolve_screen(
        consent_agreed=state["consent_accepted"], state=published_state
    )

    renderers = {
        Screen.CONSENT: render_consent,
        Screen.LOBBY: render_lobby,
        Screen.CHAT: render_chat,
        Screen.VOTING: render_voting,
    }
    context = ScreenContext(room_identity=state["room_identity"], snapshot=snapshot)
    renderers[screen](context)


if __name__ == "__main__":
    main()
