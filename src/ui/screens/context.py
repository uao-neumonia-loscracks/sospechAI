"""Contexto de render compartido por las pantallas y la raíz de composición."""

from collections.abc import Callable
from dataclasses import dataclass

from src.ui.api import RoomIdentity, StateSnapshot


@dataclass(frozen=True)
class ScreenContext:
    """Datos de sesión y callbacks que la pantalla activa recibe para renderizarse.

    Las pantallas solo leen: la mutación de la sesión y el llamado a `api.py`
    viven en `src/ui/app.py` (UIF-07).
    """

    room_identity: RoomIdentity | None = None
    snapshot: StateSnapshot | None = None
    notice: str | None = None
    on_accept_consent: Callable[[], None] | None = None
    on_create_room: Callable[[], None] | None = None
    on_join_room: Callable[[str], None] | None = None
    on_start_room: Callable[[], None] | None = None
    on_open_voting: Callable[[], None] | None = None
    on_submit_message: Callable[[str], None] | None = None
    on_submit_vote: Callable[[str], None] | None = None
