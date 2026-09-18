"""Boca única de la UI hacia una fuente de datos del contrato (UIF-07).

Las pantallas importan exclusivamente este módulo; nunca tocan el Protocol, la
fuente ni nada de ``src/orchestrator/`` ni ``src/impostor_engine/`` (UIF-10).
"""

from dataclasses import dataclass
from os import environ
from typing import Protocol


@dataclass(frozen=True)
class RoomIdentity:
    """Respuesta 201 de crear sala y de unirse a sala (contrato §§6.1-6.2)."""

    room_code: str
    session_token: str
    alias: str


@dataclass(frozen=True)
class ChatMessage:
    """Un elemento de ``messages`` en public_state() (contrato §7.1)."""

    round_number: int
    alias: str
    text: str


@dataclass(frozen=True)
class StateSnapshot:
    """Espejo de public_state() (contrato §7.1); en REVELACION incluye `result`."""

    state: str
    round_number: int | None
    rounds: int
    max_words: int
    players: list[str]
    messages: list[ChatMessage]
    votes_received: int
    remaining_seconds: float | None
    result: dict | None

    @classmethod
    def from_mapping(cls, raw: dict) -> "StateSnapshot":
        """Construir desde el JSON del cable, sin remodelar claves."""
        messages = [ChatMessage(**message) for message in raw["messages"]]
        return cls(
            state=raw["state"],
            round_number=raw.get("round_number"),
            rounds=raw["rounds"],
            max_words=raw["max_words"],
            players=list(raw["players"]),
            messages=messages,
            votes_received=raw["votes_received"],
            remaining_seconds=raw.get("remaining_seconds"),
            result=raw.get("result"),
        )


class ApiError(Exception):
    """Falla de la fuente; el cliente ramifica por `code`, nunca por `message` (contrato §8)."""

    def __init__(self, code: str, http_status: int, message: str) -> None:
        self.code = code
        self.http_status = http_status
        self.message = message
        super().__init__(f"{code} ({http_status}): {message}")


class SospechAI(Protocol):
    """Contrato interno de fuente de datos; FakeSospechAI y HttpSospechAI lo cumplen."""

    def create_room(self) -> RoomIdentity: ...

    def join_room(self, room_code: str) -> RoomIdentity: ...

    def get_state(self, room_code: str, session_token: str) -> StateSnapshot: ...

    def start(self, room_code: str, session_token: str) -> None: ...

    def open_voting(self, room_code: str, session_token: str) -> None: ...

    def submit_message(self, room_code: str, session_token: str, text: str) -> None: ...

    def submit_vote(self, room_code: str, session_token: str, suspect: str) -> None: ...


def create_room() -> RoomIdentity:
    """Crear una sala y unirse como anfitrión ("Jugador 1")."""
    return _source().create_room()


def join_room(room_code: str) -> RoomIdentity:
    """Unirse a una sala en LOBBY con el código normalizado a mayúsculas."""
    return _source().join_room(room_code.upper())


def get_state(room_code: str, session_token: str) -> StateSnapshot:
    """Leer la instantánea (contrato §8) de una sala existente."""
    return _source().get_state(room_code.upper(), session_token)


def start(room_code: str, session_token: str) -> None:
    """Registrar la IA y arrancar la partida (solo anfitrión)."""
    _source().start(room_code.upper(), session_token)


def open_voting(room_code: str, session_token: str) -> None:
    """Abrir la votación (solo anfitrión)."""
    _source().open_voting(room_code.upper(), session_token)


def submit_message(room_code: str, session_token: str, text: str) -> None:
    """Enviar un mensaje de ronda validado por la fuente."""
    _source().submit_message(room_code.upper(), session_token, text)


def submit_vote(room_code: str, session_token: str, suspect: str) -> None:
    """Emitir el voto de un humano contra POST /rooms/{code}/votes (contrato §6.6)."""
    _source().submit_vote(room_code.upper(), session_token, suspect)


def _source() -> SospechAI:
    """Seleccionar la fuente por `SOSPECHAI_UI_SOURCE` (swap localizado, UIF-07).

    "fake" (por defecto) -> FakeSospechAI in-memory; "http" -> HttpSospechAI con
    base URL en `SOSPECHAI_ORCHESTRATOR_URL`. Las pantallas no cambian (UIF-07).
    """
    from src.ui.sources import FakeSospechAI, HttpSospechAI

    source = environ.get("SOSPECHAI_UI_SOURCE", "fake")
    if source == "fake":
        return FakeSospechAI()
    if source == "http":
        base_url = environ.get("SOSPECHAI_ORCHESTRATOR_URL")
        if not base_url:
            raise ApiError(
                "internal", 500, "Falta SOSPECHAI_ORCHESTRATOR_URL con la fuente http."
            )
        return HttpSospechAI(base_url=base_url)
    raise ApiError("internal", 500, f"Fuente desconocida: {source!r}.")
