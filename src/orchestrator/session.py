"""Registro de identidad y salas del servidor multijugador.

Cada jugador recibe un token opaco ligado 1:1 a un alias asignado por el
dominio, y cada sala guarda su propia partida bajo un candado de un solo
escritor. El host siempre es quien creó la sala.
"""

import secrets
import string
import threading
from dataclasses import dataclass

from src.orchestrator.game import Game

CODE_ALPHABET = string.ascii_uppercase + string.digits
CODE_LENGTH = 5


@dataclass
class Room:
    """Sala viva: partida, host, jugadores y el candado de un solo escritor."""

    code: str
    game: Game
    host_token: str
    players: dict[str, str]
    lock: threading.Lock


@dataclass(frozen=True)
class IssuedIdentity:
    """Credenciales emitidas a un cliente al crear o unirse a una sala."""

    room_code: str
    session_token: str
    alias: str


class SessionStore:
    """Mantener la correlación token -> alias -> sala durante toda la partida."""

    def __init__(self) -> None:
        """Crear un registro vacío de salas por código."""
        self._rooms: dict[str, Room] = {}

    def create(self, *, game: Game) -> IssuedIdentity:
        """Fundar una sala con un juego nuevo; quien la crea es el host."""
        code = self._fresh_code()
        token = secrets.token_urlsafe(24)
        alias = game.add_player()
        self._rooms[code] = Room(
            code=code,
            game=game,
            host_token=token,
            players={token: alias},
            lock=threading.Lock(),
        )
        return IssuedIdentity(room_code=code, session_token=token, alias=alias)

    def join(self, room_code: str, *, game: Game) -> IssuedIdentity | None:
        """Sumar un jugador humano a la sala indicada, si existe."""
        room = self.room(room_code)
        if room is None:
            return None
        if game is not room.game:
            raise ValueError("La sala ya tiene su propia partida.")
        token = secrets.token_urlsafe(24)
        alias = room.game.add_player()
        room.players[token] = alias
        return IssuedIdentity(room_code=room.code, session_token=token, alias=alias)

    def room(self, room_code: str) -> Room | None:
        """Buscar una sala ignorando mayúsculas y minúsculas en el código."""
        return self._rooms.get(room_code.strip().upper())

    def alias_for(self, room: Room, token: str) -> str | None:
        """Resolver el alias exacto de un token, o None si no pertenece a la sala."""
        return room.players.get(token)

    def is_host(self, room: Room, token: str) -> bool:
        """Decidir si el token pertenece a quien fundó la sala."""
        return room.host_token == token

    def _fresh_code(self) -> str:
        """Generar un código único de sala en mayúsculas, reintentando choques."""
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if code not in self._rooms:
                return code
