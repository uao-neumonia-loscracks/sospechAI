"""Fuente fake in-memory del contrato UI-orquestador (Plan B del piloto, UIF-07).

Máquina congelada ``LOBBY → RONDA → DISCUSION → VOTACION → REVELACION``, alias
«Jugador N» por orden de inserción con la IA en último lugar y los mismos
recursos de guion que ``src/orchestrator/demo.py`` (copiados, nunca importados).
Sin red y sin imports de ``src/orchestrator/`` ni ``src/impostor_engine/``.
"""

from collections import Counter
from dataclasses import dataclass, field
from secrets import choice, token_hex

from src.ui.api import ApiError, RoomIdentity, StateSnapshot
from src.ui.words import normalize_text

ROOM_CODE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
SCRIPTED_RESPONSES = (
    (
        "Intentaría compartir internet desde el celular y avisarle al profesor.",
        "Me tocaría buscar una cafetería y terminar desde allá.",
        "Primero revisaría la batería, luego buscaría otra conexión disponible.",
    ),
    (
        "Una arepa con queso, tengo hambre desde hace rato.",
        "Yo pediría arroz con pollo y un juguito bien frío.",
        "Preferiría una comida caliente que pueda compartir con mis amigos.",
    ),
)


@dataclass
class _Player:
    """Participante de la sala; la marca de IA es una decisión del servidor."""

    alias: str
    is_ai: bool = False


@dataclass
class _Room:
    """Sala in-memory del fake, espejo del contrato §5-§7."""

    state: str = "LOBBY"
    round_number: int = 0
    rounds: int = 2
    max_words: int = 15
    players: dict[str, _Player] = field(default_factory=dict)
    messages: list[dict] = field(default_factory=list)
    votes: dict[str, str] = field(default_factory=dict)
    tokens: dict[str, str] = field(default_factory=dict)
    host_alias: str | None = None
    votacion_observed: bool = False
    discusion_observed: bool = False


_ROOMS: dict[str, _Room] = {}


class FakeSospechAI:
    """Fuente de datos conforme al Protocol `SospechAI`, sin red (UIF-07)."""

    def create_room(self) -> RoomIdentity:
        """Crear la sala y unir al creador como anfitrión ("Jugador 1")."""
        room_code = self._new_room_code()
        room = _Room()
        alias = "Jugador 1"
        room.players[alias] = _Player(alias=alias)
        token = self._new_token()
        room.tokens[token] = alias
        room.host_alias = alias
        _ROOMS[room_code] = room
        return RoomIdentity(room_code, token, alias)

    def join_room(self, room_code: str) -> RoomIdentity:
        """Unir a un humano en LOBBY con el siguiente "Jugador N" (contrato §3)."""
        room = self._room(room_code)
        if room.state != "LOBBY":
            raise ApiError("wrong_state", 409, "La sala ya no acepta jugadores.")
        alias = f"Jugador {len(room.players) + 1}"
        room.players[alias] = _Player(alias=alias)
        token = self._new_token()
        room.tokens[token] = alias
        return RoomIdentity(room_code.upper(), token, alias)

    def get_state(self, room_code: str, session_token: str) -> StateSnapshot:
        """Leer la instantánea; el polling scriptado avanza hasta REVELACION (ver apply)."""
        room = self._room(room_code)
        self._alias_for(room, session_token)
        if room.state == "DISCUSION":
            if room.discusion_observed:
                room.state = "VOTACION"
                room.votacion_observed = False
            else:
                room.discusion_observed = True
        if room.state == "VOTACION":
            if not room.votacion_observed:
                room.votacion_observed = True
            else:
                self._complete_votes(room)
        return self._snapshot(room)

    def start(self, room_code: str, session_token: str) -> None:
        """Registrar la IA en último lugar y arrancar RONDA (solo anfitrión)."""
        room = self._room(room_code)
        alias = self._alias_for(room, session_token)
        if room.state != "LOBBY":
            raise ApiError("wrong_state", 409, "La partida ya comenzó.")
        if alias != room.host_alias:
            raise ApiError("forbidden_host_action", 403, "Solo el anfitrión inicia.")
        humans = sum(not player.is_ai for player in room.players.values())
        if humans < 2:
            raise ApiError("invalid_roster", 409, "Se necesitan al menos dos humanos.")
        ai_alias = f"Jugador {len(room.players) + 1}"
        room.players[ai_alias] = _Player(alias=ai_alias, is_ai=True)
        room.round_number = 1
        room.state = "RONDA"

    def open_voting(self, room_code: str, session_token: str) -> None:
        """Abrir la votación desde DISCUSION (solo anfitrión)."""
        room = self._room(room_code)
        alias = self._alias_for(room, session_token)
        if room.state != "DISCUSION":
            raise ApiError("wrong_state", 409, "La votación solo se abre en debate.")
        if alias != room.host_alias:
            raise ApiError("forbidden_host_action", 403, "Solo el anfitrión vota.")
        room.state = "VOTACION"
        room.votacion_observed = False

    def submit_message(self, room_code: str, session_token: str, text: str) -> None:
        """Validar el mensaje, registrarlo y completar la ronda con guion."""
        room = self._room(room_code)
        alias = self._alias_for(room, session_token)
        if room.state != "RONDA":
            raise ApiError("wrong_state", 409, "Los mensajes solo se envían en ronda.")
        normalized = normalize_text(text)
        if not normalized:
            raise ApiError("empty_message", 400, "Escribe un mensaje con texto.")
        if len(normalized.split()) > room.max_words:
            raise ApiError(
                "too_many_words", 400, f"Máximo {room.max_words} palabras por mensaje."
            )
        already = any(
            message["alias"] == alias and message["round_number"] == room.round_number
            for message in room.messages
        )
        if already:
            raise ApiError(
                "duplicate_message", 409, "Ya enviaste un mensaje esta ronda."
            )
        room.messages.append(
            {"round_number": room.round_number, "alias": alias, "text": normalized}
        )
        self._fill_remaining(room)

    def submit_vote(self, room_code: str, session_token: str, suspect: str) -> None:
        """Registrar el voto humano en VOTACION según el contrato §§6.6/8."""
        room = self._room(room_code)
        if room.state != "VOTACION":
            raise ApiError("wrong_state", 409, "Los votos solo se emiten en votación.")
        alias = self._alias_for(room, session_token)
        if room.players[alias].is_ai:
            raise ApiError("ai_cannot_vote", 403, "La IA no vota.")
        if suspect not in room.players:
            raise ApiError(
                "not_a_player", 403, "El sospechoso no es jugador de la sala."
            )
        if suspect == alias:
            raise ApiError("self_vote", 400, "No puedes votar por ti mismo.")
        if alias in room.votes:
            raise ApiError("duplicate_vote", 409, "Ya emitiste tu voto.")
        room.votes[alias] = suspect

    def _fill_remaining(self, room: _Room) -> None:
        """Completar con guion al resto de participantes y avanzar la máquina."""
        pending = [
            player.alias
            for player in room.players.values()
            if not any(
                message["alias"] == player.alias
                and message["round_number"] == room.round_number
                for message in room.messages
            )
        ]
        scripts = SCRIPTED_RESPONSES[room.round_number - 1]
        for index, alias in enumerate(pending):
            text = scripts[index] if index < len(scripts) else scripts[-1]
            room.messages.append(
                {"round_number": room.round_number, "alias": alias, "text": text}
            )
        submitted = sum(
            1
            for message in room.messages
            if message["round_number"] == room.round_number
        )
        if submitted == len(room.players):
            if room.round_number < room.rounds:
                room.round_number += 1
            else:
                room.state = "DISCUSION"

    def _complete_votes(self, room: _Room) -> None:
        """Simular los votos humanos restantes y cerrar en REVELACION (ver apply)."""
        impostor = next(
            player.alias for player in room.players.values() if player.is_ai
        )
        for alias, player in room.players.items():
            if not player.is_ai and alias not in room.votes:
                room.votes[alias] = impostor
        room.state = "REVELACION"

    def _snapshot(self, room: _Room) -> StateSnapshot:
        """Devolver el espejo literal de public_state() (contrato §7.1)."""
        view: dict = {
            "state": room.state,
            "round_number": room.round_number,
            "rounds": room.rounds,
            "max_words": room.max_words,
            "players": list(room.players),
            "messages": [dict(message) for message in room.messages],
            "votes_received": len(room.votes),
            "remaining_seconds": 20.0 if room.state == "RONDA" else None,
        }
        if room.state == "REVELACION":
            view["result"] = self._result(room)
        return StateSnapshot.from_mapping(view)

    def _result(self, room: _Room) -> dict:
        """Devolver el cuerpo literal de result() (contrato §7.2)."""
        impostor = next(
            player.alias for player in room.players.values() if player.is_ai
        )
        scores = {
            alias: int(suspect == impostor) for alias, suspect in room.votes.items()
        }
        return {
            "state": "REVELACION",
            "impostor_alias": impostor,
            "rounds": room.rounds,
            "max_words": room.max_words,
            "votes": dict(room.votes),
            "vote_counts": dict(Counter(room.votes.values())),
            "scores": scores,
            "valid_game": True,
            "interruption_reason": None,
            "tasa_deteccion": (sum(scores.values()) / len(scores) if scores else None),
            "prompt_version": "v2",
            "transcript": [
                {
                    "round_number": message["round_number"],
                    "alias": message["alias"],
                    "text": message["text"],
                    "is_ai": room.players[message["alias"]].is_ai,
                }
                for message in room.messages
            ],
        }

    def _room(self, room_code: str) -> _Room:
        """Resolver la sala por código normalizado o informar room_not_found."""
        room = _ROOMS.get(room_code.upper())
        if room is None:
            raise ApiError("room_not_found", 404, "La sala no existe.")
        return room

    def _alias_for(self, room: _Room, session_token: str) -> str:
        """Resolver el alias ligado al token o fallar según el contrato §8."""
        alias = room.tokens.get(session_token)
        if alias is not None:
            return alias
        known_elsewhere = any(
            session_token in other.tokens for other in _ROOMS.values()
        )
        if known_elsewhere:
            raise ApiError("not_a_player", 403, "El token no pertenece a esta sala.")
        raise ApiError("session_expired", 401, "El token de sesión no es válido.")

    def _new_room_code(self) -> str:
        """Generar un código opaco corto en mayúsculas sin colisiones."""
        while True:
            code = "".join(choice(ROOM_CODE_ALPHABET) for _ in range(5))
            if code not in _ROOMS:
                return code

    def _new_token(self) -> str:
        """Generar un token de sesión opaco emitido por el servidor."""
        return f"s3_{token_hex(16)}"
