"""Contexto de render compartido por las pantallas y la raíz de composición."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScreenContext:
    """Datos de sesión que la pantalla activa recibe para renderizarse.

    En el esqueleto (fase 1) la identidad de sala y la instantánea todavía no
    existen y quedan como `None`; se tiparán con `RoomIdentity` y `StateSnapshot`
    cuando `api.py` los defina (fase 2).
    """

    room_identity: object | None = None
    snapshot: object | None = None
