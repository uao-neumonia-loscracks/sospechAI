"""Pruebas AAA del facade ``api.py`` y del fake sin red (UIF-07, UIF-11).

Cubren las tareas 2.3 (formas exactas del contrato, máquina congelada, alias
con la IA en último lugar y catálogo de errores) y 2.6 (bloqueo combinado:
mensaje dentro del límite aceptado y visible; sobre el límite, ``too_many_words``
y ausencia de la conversación).
"""

import dataclasses
import json
import random
import secrets
import socket
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator

import pytest

from src.ui.api import (
    ApiError,
    ChatMessage,
    RoomIdentity,
    StateSnapshot,
    create_room,
    get_state,
    join_room,
    open_voting,
    start,
    submit_message,
    submit_vote,
)
from src.ui.sources.http import HttpSospechAI
from src.ui.words import count_words, within_limit

PUBLIC_STATE_KEYS = (
    "state",
    "round_number",
    "rounds",
    "max_words",
    "players",
    "messages",
    "votes_received",
    "remaining_seconds",
    "result",
    "round_prompt",
)
RESULT_KEYS = (
    "state",
    "impostor_alias",
    "rounds",
    "max_words",
    "votes",
    "vote_counts",
    "scores",
    "valid_game",
    "interruption_reason",
    "tasa_deteccion",
    "prompt_version",
    "transcript",
)


def _started_room() -> tuple[RoomIdentity, RoomIdentity]:
    """Abrir una sala con dos humanos en la primera ronda (solo Arrange)."""
    host = create_room()
    guest = join_room(host.room_code)
    start(host.room_code, host.session_token)
    return host, guest


def _voting_room() -> tuple[RoomIdentity, RoomIdentity]:
    """Avançar la máquina hasta VOTACION con dos humanos (solo Arrange)."""
    host, guest = _started_room()
    submit_message(
        host.room_code, host.session_token, "Yo creo que el problema fue la luz."
    )
    submit_message(
        host.room_code, guest.session_token, "Buscaría una cafetería para terminar."
    )
    open_voting(host.room_code, host.session_token)
    return host, guest


def test_state_snapshot_fields_match_contract_keys() -> None:
    """La instantánea exponer todas las claves del contrato §7.1, ni más ni menos."""
    # Arrange
    expected = list(PUBLIC_STATE_KEYS)

    # Act
    field_names = [field.name for field in dataclasses.fields(StateSnapshot)]

    # Assert
    assert field_names == expected


def test_from_mapping_sin_result_lo_deja_en_none() -> None:
    """Un estado sin REVELACION no lleva `result` (contrato §7.1)."""
    # Arrange
    raw = {
        "state": "LOBBY",
        "round_number": 0,
        "rounds": 2,
        "max_words": 15,
        "players": ["Jugador 1"],
        "messages": [],
        "votes_received": 0,
        "remaining_seconds": None,
    }

    # Act
    snapshot = StateSnapshot.from_mapping(raw)

    # Assert
    assert snapshot.state == "LOBBY"
    assert snapshot.round_number == 0
    assert snapshot.rounds == 2
    assert snapshot.max_words == 15
    assert snapshot.players == ["Jugador 1"]
    assert snapshot.messages == []
    assert snapshot.votes_received == 0
    assert snapshot.remaining_seconds is None
    assert snapshot.result is None


def test_from_mapping_convierte_los_mensajes_a_chat_message() -> None:
    """Cada mensaje del cable se modela como `ChatMessage` (contrato §7.1)."""
    # Arrange
    raw = {
        "state": "RONDA",
        "round_number": 1,
        "rounds": 2,
        "max_words": 15,
        "players": ["Jugador 1", "Jugador 2", "Jugador 3"],
        "messages": [
            {"round_number": 1, "alias": "Jugador 1", "text": "Hola a todos."}
        ],
        "votes_received": 0,
        "remaining_seconds": 20.0,
    }

    # Act
    snapshot = StateSnapshot.from_mapping(raw)

    # Assert
    assert snapshot.messages == [
        ChatMessage(round_number=1, alias="Jugador 1", text="Hola a todos.")
    ]


def test_from_mapping_lee_round_prompt_y_tolera_su_ausencia() -> None:
    """round_prompt pasa del cable a la instantánea; sin la clave, None (v1.0)."""
    # Arrange
    raw = {
        "state": "RONDA",
        "round_number": 1,
        "rounds": 2,
        "max_words": 15,
        "players": ["Jugador 1", "Jugador 2", "Jugador 3"],
        "messages": [],
        "votes_received": 0,
        "remaining_seconds": 20.0,
        "round_prompt": "¿Qué harías si se va la luz justo antes de entregar un trabajo?",
    }
    legacy = dict(raw)
    del legacy["round_prompt"]

    # Act
    with_prompt = StateSnapshot.from_mapping(raw)
    without_prompt = StateSnapshot.from_mapping(legacy)

    # Assert
    assert with_prompt.round_prompt == raw["round_prompt"]
    assert without_prompt.round_prompt is None


def test_round_prompt_del_fake_se_expone_en_la_ronda() -> None:
    """El fake publica la pregunta de la ronda vigente para los humanos (UIF-07)."""
    # Arrange
    host, _ = _started_room()

    # Act
    snapshot = get_state(host.room_code, host.session_token)

    # Assert
    assert snapshot.state == "RONDA"
    assert snapshot.round_prompt == (
        "¿Qué harías si se va la luz justo antes de entregar un trabajo?"
    )


def test_round_prompt_del_fake_cambia_por_ronda() -> None:
    """En la segunda ronda el fake publica la segunda pregunta del contrato."""
    # Arrange
    host, _ = _started_room()
    submit_message(host.room_code, host.session_token, "Yo creo que fue la luz.")

    # Act
    snapshot = get_state(host.room_code, host.session_token)

    # Assert
    assert snapshot.round_number == 2
    assert snapshot.round_prompt == "¿Qué comida escogerías después de una clase larga?"


def test_from_mapping_conserva_result_en_revelacion() -> None:
    """En REVELACION el `result` embebido se conserva sin remodelar (contrato §7.2)."""
    # Arrange
    result = {
        "state": "REVELACION",
        "impostor_alias": "Jugador 3",
        "rounds": 2,
        "max_words": 15,
        "votes": {"Jugador 1": "Jugador 3", "Jugador 2": "Jugador 3"},
        "vote_counts": {"Jugador 3": 2},
        "scores": {"Jugador 1": 1, "Jugador 2": 1},
        "valid_game": True,
        "interruption_reason": None,
        "tasa_deteccion": 1.0,
        "transcript": [],
    }
    raw = {
        "state": "REVELACION",
        "round_number": 2,
        "rounds": 2,
        "max_words": 15,
        "players": ["Jugador 1", "Jugador 2", "Jugador 3"],
        "messages": [],
        "votes_received": 2,
        "remaining_seconds": None,
        "result": result,
    }

    # Act
    snapshot = StateSnapshot.from_mapping(raw)

    # Assert
    assert snapshot.result == result


def test_create_room_devuelve_anfitrion_en_lobby() -> None:
    """El creador es "Jugador 1" y la sala arranca en LOBBY (contrato §4)."""
    # Arrange
    # (sin precondiciones)

    # Act
    host = create_room()
    snapshot = get_state(host.room_code, host.session_token)

    # Assert
    assert host.room_code.isupper()
    assert host.session_token
    assert host.alias == "Jugador 1"
    assert snapshot.state == "LOBBY"
    assert snapshot.round_number == 0
    assert snapshot.round_prompt is None
    assert snapshot.players == ["Jugador 1"]


def test_join_room_asigna_el_siguiente_alias() -> None:
    """Unirse a una sala en LOBBY asigna el siguiente "Jugador N" (contrato §3)."""
    # Arrange
    host = create_room()

    # Act
    guest = join_room(host.room_code)
    snapshot = get_state(host.room_code, host.session_token)

    # Assert
    assert guest.alias == "Jugador 2"
    assert snapshot.players == ["Jugador 1", "Jugador 2"]


def test_join_room_normaliza_el_codigo_a_mayusculas() -> None:
    """El código de sala se normaliza a mayúsculas en el cliente (contrato §3)."""
    # Arrange
    host = create_room()

    # Act
    guest = join_room(host.room_code.lower())

    # Assert
    assert guest.alias == "Jugador 2"


def test_machine_avanza_lobby_ronda_discusion() -> None:
    """La máquina congelada recorre LOBBY, RONDA, RONDA y DISCUSION en orden."""
    # Arrange
    host, guest = _started_room()
    visited: list[str] = []
    rounds: list[int | None] = []
    remaining: list[float | None] = []

    # Act
    snapshot = get_state(host.room_code, host.session_token)
    visited.append(snapshot.state)
    rounds.append(snapshot.round_number)
    remaining.append(snapshot.remaining_seconds)
    submit_message(
        host.room_code, host.session_token, "Yo creo que el problema fue la luz."
    )
    snapshot = get_state(host.room_code, host.session_token)
    visited.append(snapshot.state)
    rounds.append(snapshot.round_number)
    remaining.append(snapshot.remaining_seconds)
    submit_message(
        host.room_code, guest.session_token, "Buscaría una cafetería para terminar."
    )
    snapshot = get_state(host.room_code, host.session_token)
    visited.append(snapshot.state)
    rounds.append(snapshot.round_number)
    remaining.append(snapshot.remaining_seconds)

    # Assert
    assert visited == ["RONDA", "RONDA", "DISCUSION"]
    assert snapshot.state == "DISCUSION"
    assert snapshot.players == ["Jugador 1", "Jugador 2", "Jugador 3"]
    assert rounds == [1, 2, 2]
    assert remaining == [20.0, 20.0, None]
    assert snapshot.result is None


def test_open_voting_y_poll_revelan_el_resultado() -> None:
    """open_voting lleva a VOTACION y un segundo poll revela REVELACION con `result`."""
    # Arrange
    host, guest = _started_room()
    submit_message(
        host.room_code, host.session_token, "Yo creo que el problema fue la luz."
    )
    submit_message(
        host.room_code, guest.session_token, "Buscaría una cafetería para terminar."
    )

    # Act
    open_voting(host.room_code, host.session_token)
    voting = get_state(host.room_code, host.session_token)
    revealed = get_state(host.room_code, host.session_token)

    # Assert
    assert voting.state == "VOTACION"
    assert voting.round_number == 2
    assert voting.votes_received == 0
    assert voting.result is None
    assert revealed.state == "REVELACION"
    assert revealed.round_number == 2
    assert revealed.votes_received == 2
    assert revealed.result is not None
    assert all(key in revealed.result for key in RESULT_KEYS)
    assert revealed.result["state"] == "REVELACION"
    assert revealed.result["impostor_alias"] == "Jugador 3"
    assert revealed.result["valid_game"] is True
    assert revealed.result["interruption_reason"] is None
    assert sum(revealed.result["vote_counts"].values()) == 2
    assert sum(message["is_ai"] for message in revealed.result["transcript"]) == 2


def test_result_del_fake_emite_prompt_version_v2() -> None:
    """El fake emite la clave aditiva prompt_version "v2" (contrato v1.1 §7.2)."""
    # Arrange
    host, _ = _voting_room()

    # Act
    get_state(host.room_code, host.session_token)
    revealed = get_state(host.room_code, host.session_token)

    # Assert
    assert revealed.result["prompt_version"] == "v2"


def test_submit_vote_feliz_registra_y_revela_en_el_siguiente_poll() -> None:
    """Un voto humano aceptado (204) se registra y el poll cierra en REVELACION."""
    # Arrange
    host, _ = _voting_room()
    get_state(host.room_code, host.session_token)

    # Act
    submit_vote(host.room_code, host.session_token, "Jugador 2")
    revealed = get_state(host.room_code, host.session_token)

    # Assert
    assert revealed.state == "REVELACION"
    assert revealed.votes_received == 2
    assert revealed.result["votes"]["Jugador 1"] == "Jugador 2"
    assert "Jugador 2" in revealed.result["votes"]


def test_submit_vote_de_todos_los_humanos_revela_sin_guion() -> None:
    """Con voto real de todos los humanos, el poll cierra sin llenado scriptado."""
    # Arrange
    host, guest = _voting_room()
    get_state(host.room_code, host.session_token)

    # Act
    submit_vote(host.room_code, host.session_token, "Jugador 2")
    submit_vote(guest.room_code, guest.session_token, "Jugador 1")
    revealed = get_state(host.room_code, host.session_token)

    # Assert
    assert revealed.state == "REVELACION"
    assert revealed.result["votes"] == {
        "Jugador 1": "Jugador 2",
        "Jugador 2": "Jugador 1",
    }
    assert revealed.votes_received == 2


def test_submit_vote_a_uno_mismo_es_self_vote() -> None:
    """Votar por el propio alias devuelve self_vote (400) y no registra (§6.6/§8)."""
    # Arrange
    host, _ = _voting_room()

    # Act
    with pytest.raises(ApiError) as exc_info:
        submit_vote(host.room_code, host.session_token, "Jugador 1")
    snapshot = get_state(host.room_code, host.session_token)

    # Assert
    assert exc_info.value.code == "self_vote"
    assert exc_info.value.http_status == 400
    assert snapshot.state == "VOTACION"
    assert snapshot.votes_received == 0


def test_segundo_voto_del_mismo_humano_es_duplicate_vote() -> None:
    """Un segundo voto del mismo jugador devuelve duplicate_vote (409)."""
    # Arrange
    host, _ = _voting_room()
    submit_vote(host.room_code, host.session_token, "Jugador 2")

    # Act
    with pytest.raises(ApiError) as exc_info:
        submit_vote(host.room_code, host.session_token, "Jugador 3")

    # Assert
    assert exc_info.value.code == "duplicate_vote"
    assert exc_info.value.http_status == 409


def test_submit_vote_con_sospechoso_no_jugador_es_not_a_player() -> None:
    """Un sospechoso que no es jugador de la sala devuelve not_a_player (403)."""
    # Arrange
    host, _ = _voting_room()

    # Act
    with pytest.raises(ApiError) as exc_info:
        submit_vote(host.room_code, host.session_token, "Jugador 99")

    # Assert
    assert exc_info.value.code == "not_a_player"
    assert exc_info.value.http_status == 403


def test_submit_vote_con_token_invalido_es_session_expired() -> None:
    """Un token desconocido al votar devuelve session_expired (401, §8)."""
    # Arrange
    host, _ = _voting_room()

    # Act
    with pytest.raises(ApiError) as exc_info:
        submit_vote(host.room_code, "token_no_emitido", "Jugador 2")

    # Assert
    assert exc_info.value.code == "session_expired"
    assert exc_info.value.http_status == 401


def test_submit_vote_fuera_de_votacion_es_wrong_state() -> None:
    """Enviar un voto antes de VOTACION devuelve wrong_state (409)."""
    # Arrange
    host, _ = _started_room()

    # Act
    with pytest.raises(ApiError) as exc_info:
        submit_vote(host.room_code, host.session_token, "Jugador 2")

    # Assert
    assert exc_info.value.code == "wrong_state"
    assert exc_info.value.http_status == 409


def test_get_state_de_sala_desconocida_es_room_not_found() -> None:
    """Una sala que no existe devuelve room_not_found (404, contrato §8)."""
    # Arrange
    room_code = "ZZZZZ"
    session_token = "s_cualquiera"

    # Act
    with pytest.raises(ApiError) as exc_info:
        get_state(room_code, session_token)

    # Assert
    assert exc_info.value.code == "room_not_found"
    assert exc_info.value.http_status == 404


def test_get_state_con_token_desconocido_es_session_expired() -> None:
    """Un token desconocido devuelve session_expired (401, contrato §8)."""
    # Arrange
    host = create_room()

    # Act
    with pytest.raises(ApiError) as exc_info:
        get_state(host.room_code, "token_no_emitido")

    # Assert
    assert exc_info.value.code == "session_expired"
    assert exc_info.value.http_status == 401


def test_token_de_otra_sala_es_not_a_player() -> None:
    """Un token válido de otra sala no es un jugador de esta (403, contrato §8)."""
    # Arrange
    room_a = create_room()
    room_b = create_room()

    # Act
    with pytest.raises(ApiError) as exc_info:
        get_state(room_a.room_code, room_b.session_token)

    # Assert
    assert exc_info.value.code == "not_a_player"
    assert exc_info.value.http_status == 403


def test_unirse_tras_start_es_wrong_state() -> None:
    """Unirse fuera de LOBBY devuelve wrong_state (409, contrato §8)."""
    # Arrange
    host, _ = _started_room()

    # Act
    with pytest.raises(ApiError) as exc_info:
        join_room(host.room_code)

    # Assert
    assert exc_info.value.code == "wrong_state"
    assert exc_info.value.http_status == 409


def test_start_con_un_solo_humano_es_invalid_roster() -> None:
    """start necesita al menos dos humanos: invalid_roster (409, contrato §8)."""
    # Arrange
    host = create_room()

    # Act
    with pytest.raises(ApiError) as exc_info:
        start(host.room_code, host.session_token)

    # Assert
    assert exc_info.value.code == "invalid_roster"
    assert exc_info.value.http_status == 409


def test_start_de_no_anfitrion_es_forbidden_host_action() -> None:
    """Solo el anfitrión puede start: forbidden_host_action (403, contrato §8)."""
    # Arrange
    host = create_room()
    guest = join_room(host.room_code)

    # Act
    with pytest.raises(ApiError) as exc_info:
        start(host.room_code, guest.session_token)

    # Assert
    assert exc_info.value.code == "forbidden_host_action"
    assert exc_info.value.http_status == 403


def test_mensaje_vacio_tras_normalizacion_es_empty_message() -> None:
    """Un texto sin contenido tras normalizar devuelve empty_message (400)."""
    # Arrange
    host, _ = _started_room()

    # Act
    with pytest.raises(ApiError) as exc_info:
        submit_message(host.room_code, host.session_token, "   ")

    # Assert
    assert exc_info.value.code == "empty_message"
    assert exc_info.value.http_status == 400


def test_mensaje_dentro_del_limite_se_acepta_y_queda_visible() -> None:
    """Dentro del límite, el facade acepta y el mensaje aparece en la conversación."""
    # Arrange
    host, _ = _started_room()
    text = "Hola, ¿cómo va el debate?"
    snapshot = get_state(host.room_code, host.session_token)

    # Act
    submit_message(host.room_code, host.session_token, text)
    updated = get_state(host.room_code, host.session_token)

    # Assert
    assert within_limit(count_words(text), snapshot.max_words) is True
    assert updated.messages != snapshot.messages
    assert any(
        message.round_number == 1
        and message.alias == host.alias
        and message.text == "Hola, ¿cómo va el debate?"
        for message in updated.messages
    )


def test_mensaje_sobre_el_limite_es_too_many_words_y_no_queda_visible() -> None:
    """Sobre el límite, el facade lanza too_many_words y no agrega la conversación."""
    # Arrange
    host, _ = _started_room()
    over_limit = " ".join(["palabra"] * 20)
    snapshot = get_state(host.room_code, host.session_token)

    # Act
    with pytest.raises(ApiError) as exc_info:
        submit_message(host.room_code, host.session_token, over_limit)
    updated = get_state(host.room_code, host.session_token)

    # Assert
    assert within_limit(count_words(over_limit), snapshot.max_words) is False
    assert exc_info.value.code == "too_many_words"
    assert exc_info.value.http_status == 400
    assert updated.messages == snapshot.messages
    assert all(over_limit not in message.text for message in updated.messages)


# --- Integración HTTP (tarea 2.7): HttpSospechAI contra un ThreadingHTTPServer local ---

_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


class _TestApiError(Exception):
    """Falla de negocio del servidor de prueba, traducida a una respuesta no-2xx."""

    def __init__(self, code: str, http_status: int, message: str) -> None:
        self.code = code
        self.http_status = http_status
        self.message = message


@dataclasses.dataclass
class _TestRoom:
    """Sala del servidor de prueba; espejo mínimo del contrato §§5-7."""

    state: str = "LOBBY"
    round_number: int = 0
    rounds: int = 2
    max_words: int = 15
    tokens: dict[str, str] = dataclasses.field(default_factory=dict)
    host_token: str = ""
    ai_added: bool = False
    messages: list[dict] = dataclasses.field(default_factory=list)
    votes: dict[str, str] = dataclasses.field(default_factory=dict)
    result: dict | None = None
    remaining_seconds: float | None = None


class _ContractHandler(BaseHTTPRequestHandler):
    """Handler HTTP estándar que respeta las formas de cable del contrato §§6-8."""

    rooms: dict[str, _TestRoom] = {}
    request_log: list[tuple[str, str, str | None]] = []

    def log_message(self, format: str, *args: object) -> None:
        """Silenciar el log por defecto de BaseHTTPRequestHandler."""

    def do_GET(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch()

    def _dispatch(self) -> None:
        token = self.headers.get("X-Session-Token")
        self.request_log.append((self.command, self.path, token))
        try:
            handler, args = self._route()
            handler(token, *args)
        except _TestApiError as exc:
            self._send_error(exc.http_status, exc.code, exc.message)

    def _route(self) -> tuple[Callable[..., None], tuple[str, ...]]:
        parts = [part for part in self.path.strip("/").split("/") if part]
        if self.command == "POST" and parts == ["rooms"]:
            return self._op_create, ()
        if self.command == "POST" and len(parts) == 3 and parts[2] == "join":
            return self._op_join, (parts[1],)
        if self.command == "POST" and len(parts) == 3 and parts[2] == "start":
            return self._op_start, (parts[1],)
        if self.command == "GET" and len(parts) == 3 and parts[2] == "state":
            return self._op_state, (parts[1],)
        if self.command == "POST" and len(parts) == 3 and parts[2] == "messages":
            return self._op_messages, (parts[1],)
        if self.command == "POST" and len(parts) == 3 and parts[2] == "votes":
            return self._op_votes, (parts[1],)
        if (
            self.command == "POST"
            and len(parts) == 4
            and parts[2] == "voting"
            and parts[3] == "open"
        ):
            return self._op_voting_open, (parts[1],)
        raise _TestApiError("not_found", 404, "Ruta desconocida.")

    def _op_create(self, _token: str | None) -> None:
        code = self._new_code()
        session_token = secrets.token_hex(8)
        room = _TestRoom()
        room.tokens[session_token] = "Jugador 1"
        room.host_token = session_token
        self.rooms[code] = room
        self._send_json(
            201,
            {"room_code": code, "session_token": session_token, "alias": "Jugador 1"},
        )

    def _op_join(self, _token: str | None, code: str) -> None:
        room = self._room(code)
        if room.state != "LOBBY":
            raise _TestApiError("wrong_state", 409, "La sala ya no acepta jugadores.")
        session_token = secrets.token_hex(8)
        alias = f"Jugador {len(room.tokens) + 1}"
        room.tokens[session_token] = alias
        self._send_json(201, {"session_token": session_token, "alias": alias})

    def _op_start(self, token: str | None, code: str) -> None:
        room = self._room(code)
        self._alias_for(room, token)
        if room.state != "LOBBY":
            raise _TestApiError("wrong_state", 409, "La partida ya comenzó.")
        if token != room.host_token:
            raise _TestApiError(
                "forbidden_host_action", 403, "Solo el anfitrión inicia."
            )
        if len(room.tokens) < 2:
            raise _TestApiError(
                "invalid_roster", 409, "Se necesitan al menos dos humanos."
            )
        room.ai_added = True
        room.state = "RONDA"
        room.round_number = 1
        room.remaining_seconds = 20.0
        self._send_no_content()

    def _op_state(self, token: str | None, code: str) -> None:
        room = self._room(code)
        self._alias_for(room, token)
        players = list(room.tokens.values())
        if room.ai_added:
            players.append(f"Jugador {len(players) + 1}")
        body = {
            "state": room.state,
            "round_number": room.round_number,
            "rounds": room.rounds,
            "max_words": room.max_words,
            "players": players,
            "messages": [dict(message) for message in room.messages],
            "votes_received": len(room.votes),
            "remaining_seconds": room.remaining_seconds,
            "result": room.result,
        }
        self._send_json(200, body)

    def _op_messages(self, token: str | None, code: str) -> None:
        room = self._room(code)
        alias = self._alias_for(room, token)
        if room.state != "RONDA":
            raise _TestApiError(
                "wrong_state", 409, "Los mensajes solo se envían en ronda."
            )
        text = self._payload().get("text", "")
        if text == "malformed_error_body":
            self._send_raw(400, b"el cuerpo de error no es JSON")
            return
        normalized = " ".join(text.split())
        if not normalized:
            raise _TestApiError("empty_message", 400, "Escribe un mensaje con texto.")
        if len(normalized.split()) > room.max_words:
            raise _TestApiError(
                "too_many_words", 400, f"Máximo {room.max_words} palabras por mensaje."
            )
        submitted = [m for m in room.messages if m["round_number"] == room.round_number]
        if any(m["alias"] == alias for m in submitted):
            raise _TestApiError(
                "duplicate_message", 409, "Ya enviaste un mensaje esta ronda."
            )
        room.messages.append(
            {"round_number": room.round_number, "alias": alias, "text": normalized}
        )
        self._advance_round(room)
        self._send_no_content()

    def _op_votes(self, token: str | None, code: str) -> None:
        room = self._room(code)
        alias = self._alias_for(room, token)
        if room.state != "VOTACION":
            raise _TestApiError(
                "wrong_state", 409, "Los votos solo se emiten en votación."
            )
        suspect = self._payload().get("suspect", "")
        players = list(room.tokens.values())
        if room.ai_added:
            players.append(f"Jugador {len(players) + 1}")
        if suspect not in players:
            raise _TestApiError(
                "not_a_player", 403, "El sospechoso no es jugador de la sala."
            )
        if suspect == alias:
            raise _TestApiError("self_vote", 400, "No puedes votar por ti mismo.")
        if alias in room.votes:
            raise _TestApiError("duplicate_vote", 409, "Ya emitiste tu voto.")
        room.votes[alias] = suspect
        self._send_no_content()

    def _op_voting_open(self, token: str | None, code: str) -> None:
        room = self._room(code)
        self._alias_for(room, token)
        if room.state != "DISCUSION":
            raise _TestApiError(
                "wrong_state", 409, "La votación solo se abre en debate."
            )
        if token != room.host_token:
            raise _TestApiError(
                "forbidden_host_action", 403, "Solo el anfitrión abre la votación."
            )
        room.state = "VOTACION"
        room.remaining_seconds = None
        self._send_no_content()

    def _advance_round(self, room: _TestRoom) -> None:
        humans = list(room.tokens.values())
        ai_alias = f"Jugador {len(humans) + 1}"
        submitted = [
            m["alias"] for m in room.messages if m["round_number"] == room.round_number
        ]
        if not all(human in submitted for human in humans):
            return
        if ai_alias not in submitted:
            room.messages.append(
                {
                    "round_number": room.round_number,
                    "alias": ai_alias,
                    "text": "Estoy de acuerdo con el resto del grupo.",
                }
            )
        if room.round_number < room.rounds:
            room.round_number += 1
        else:
            room.state = "DISCUSION"
            room.remaining_seconds = None

    def _room(self, code: str) -> _TestRoom:
        room = self.rooms.get(code.upper())
        if room is None:
            raise _TestApiError("room_not_found", 404, "La sala no existe.")
        return room

    def _alias_for(self, room: _TestRoom, token: str | None) -> str:
        alias = room.tokens.get(token or "")
        if alias is None:
            raise _TestApiError(
                "session_expired", 401, "El token de sesión no es válido."
            )
        return alias

    def _payload(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        try:
            return json.loads(raw) if raw else {}
        except ValueError:
            raise _TestApiError("malformed_request", 400, "Cuerpo JSON inválido.")

    def _new_code(self) -> str:
        while True:
            code = "".join(random.choices(_ALPHABET, k=5))
            if code not in self.rooms:
                return code

    def _send_no_content(self) -> None:
        self.send_response(204)
        self.end_headers()

    def _send_json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_raw(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, code: str, message: str) -> None:
        self._send_json(status, {"code": code, "message": message})


@pytest.fixture
def http_contract() -> Iterator[str]:
    """Levantar un ThreadingHTTPServer local y devolver su base URL (Arrange)."""
    _ContractHandler.rooms = {}
    _ContractHandler.request_log = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ContractHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    yield base_url
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _http_started_room(client: HttpSospechAI) -> tuple[RoomIdentity, RoomIdentity]:
    """Crear, unir y arrancar una sala por HTTP (solo Arrange)."""
    host = client.create_room()
    guest = client.join_room(host.room_code)
    client.start(host.room_code, host.session_token)
    return host, guest


def _http_voting_room(client: HttpSospechAI) -> tuple[RoomIdentity, RoomIdentity]:
    """Avançar por HTTP hasta VOTACION con dos humanos (solo Arrange)."""
    host, guest = _http_started_room(client)
    client.submit_message(host.room_code, host.session_token, "Yo creo que fue la luz.")
    client.submit_message(
        host.room_code, guest.session_token, "Buscaría otra conexión."
    )
    client.submit_message(
        host.room_code, host.session_token, "Me parece bien, seguimos."
    )
    client.submit_message(
        host.room_code, guest.session_token, "Coincido con el equipo."
    )
    client.open_voting(host.room_code, host.session_token)
    return host, guest


@pytest.mark.integration
def test_create_room_mapea_201_sin_token_de_sesion(http_contract: str) -> None:
    """create_room no envía cabecera y mapea el 201 a una identidad de anfitrión."""
    # Arrange
    client = HttpSospechAI(base_url=http_contract)

    # Act
    identity = client.create_room()

    # Assert
    assert identity.alias == "Jugador 1"
    assert identity.room_code.isupper()
    assert identity.session_token
    assert ("POST", "/rooms", None) in _ContractHandler.request_log


@pytest.mark.integration
def test_join_room_normaliza_a_mayusculas_y_sin_token(http_contract: str) -> None:
    """join_room normaliza el código y el 201 llega sin cabecera de sesión."""
    # Arrange
    client = HttpSospechAI(base_url=http_contract)
    host = client.create_room()

    # Act
    guest = client.join_room(host.room_code.lower())

    # Assert
    assert guest.alias == "Jugador 2"
    assert guest.room_code.isupper()
    assert (
        "POST",
        f"/rooms/{host.room_code}/join",
        None,
    ) in _ContractHandler.request_log


@pytest.mark.integration
def test_flujo_204_200_con_cabecera_recorre_la_maquina(http_contract: str) -> None:
    """Acciones 204, estado 200 y cabecera X-Session-Token en cada petición autenticada."""
    # Arrange
    client = HttpSospechAI(base_url=http_contract)
    host, guest = _http_started_room(client)

    # Act
    snapshot = client.get_state(host.room_code, host.session_token)
    client.submit_message(host.room_code, host.session_token, "Yo creo que fue la luz.")
    client.submit_message(
        host.room_code, guest.session_token, "Buscaría otra conexión."
    )
    client.submit_message(
        host.room_code, host.session_token, "Me parece bien, seguimos."
    )
    client.submit_message(
        host.room_code, guest.session_token, "Coincido con el equipo."
    )
    client.open_voting(host.room_code, host.session_token)
    after_open = client.get_state(host.room_code, host.session_token)

    # Assert
    assert snapshot.state == "RONDA"
    assert snapshot.players == ["Jugador 1", "Jugador 2", "Jugador 3"]
    assert after_open.state == "VOTACION"
    assert after_open.round_number == 2
    assert "Yo creo que fue la luz." in [m.text for m in after_open.messages]
    assert len(_ContractHandler.request_log) >= 6
    for method, path, token in _ContractHandler.request_log:
        if method == "POST" and path == "/rooms":
            assert token is None
        elif path.endswith("/join"):
            assert token is None
        else:
            assert token in (host.session_token, guest.session_token)


@pytest.mark.integration
def test_too_many_words_se_parsea_por_code(http_contract: str) -> None:
    """El 400 con código too_many_words se traduce a ApiError por `code`."""
    # Arrange
    client = HttpSospechAI(base_url=http_contract)
    host, _ = _http_started_room(client)
    over_limit = " ".join(["palabra"] * 20)

    # Act
    with pytest.raises(ApiError) as exc_info:
        client.submit_message(host.room_code, host.session_token, over_limit)

    # Assert
    assert exc_info.value.code == "too_many_words"
    assert exc_info.value.http_status == 400
    assert exc_info.value.message == "Máximo 15 palabras por mensaje."


@pytest.mark.integration
def test_session_expired_se_parsea_por_code(http_contract: str) -> None:
    """El 401 con código session_expired se traduce a ApiError por `code`."""
    # Arrange
    client = HttpSospechAI(base_url=http_contract)
    host = client.create_room()

    # Act
    with pytest.raises(ApiError) as exc_info:
        client.get_state(host.room_code, "token_no_emitido")

    # Assert
    assert exc_info.value.code == "session_expired"
    assert exc_info.value.http_status == 401


@pytest.mark.integration
def test_unirse_tras_start_es_wrong_state_por_http(http_contract: str) -> None:
    """El 409 con código wrong_state se traduce a ApiError por `code`."""
    # Arrange
    client = HttpSospechAI(base_url=http_contract)
    host, _ = _http_started_room(client)

    # Act
    with pytest.raises(ApiError) as exc_info:
        client.join_room(host.room_code)

    # Assert
    assert exc_info.value.code == "wrong_state"
    assert exc_info.value.http_status == 409


@pytest.mark.integration
def test_submit_vote_por_http_204_y_registra_el_voto(http_contract: str) -> None:
    """submit_vote por HTTP llega a POST /rooms/{code}/votes y recibe 204."""
    # Arrange
    client = HttpSospechAI(base_url=http_contract)
    host, _ = _http_voting_room(client)

    # Act
    client.submit_vote(host.room_code, host.session_token, "Jugador 2")
    snapshot = client.get_state(host.room_code, host.session_token)

    # Assert
    assert ("POST", f"/rooms/{host.room_code}/votes", host.session_token) in (
        _ContractHandler.request_log
    )
    assert snapshot.votes_received == 1


@pytest.mark.integration
def test_submit_vote_por_http_self_vote_es_400(http_contract: str) -> None:
    """El 400 con código self_vote se traduce a ApiError por `code` (§8)."""
    # Arrange
    client = HttpSospechAI(base_url=http_contract)
    host, _ = _http_voting_room(client)

    # Act
    with pytest.raises(ApiError) as exc_info:
        client.submit_vote(host.room_code, host.session_token, host.alias)

    # Assert
    assert exc_info.value.code == "self_vote"
    assert exc_info.value.http_status == 400


@pytest.mark.integration
def test_submit_vote_por_http_duplicate_vote_es_409(http_contract: str) -> None:
    """El 409 con código duplicate_vote se traduce a ApiError por `code` (§8)."""
    # Arrange
    client = HttpSospechAI(base_url=http_contract)
    host, _ = _http_voting_room(client)
    client.submit_vote(host.room_code, host.session_token, "Jugador 2")

    # Act
    with pytest.raises(ApiError) as exc_info:
        client.submit_vote(host.room_code, host.session_token, "Jugador 3")

    # Assert
    assert exc_info.value.code == "duplicate_vote"
    assert exc_info.value.http_status == 409


@pytest.mark.integration
def test_get_state_tolera_result_v10_sin_prompt_version(
    http_contract: str,
) -> None:
    """Un servidor v1.0 (result sin prompt_version) no rompe el transporte (§13)."""
    # Arrange
    client = HttpSospechAI(base_url=http_contract)
    host, _ = _http_started_room(client)
    room = _ContractHandler.rooms[host.room_code]
    room.state = "REVELACION"
    room.result = {
        "state": "REVELACION",
        "impostor_alias": "Jugador 3",
        "rounds": 2,
        "max_words": 15,
        "votes": {"Jugador 1": "Jugador 3"},
        "vote_counts": {"Jugador 3": 1},
        "scores": {"Jugador 1": 1},
        "valid_game": True,
        "interruption_reason": None,
        "tasa_deteccion": 1.0,
        "transcript": [],
    }

    # Act
    snapshot = client.get_state(host.room_code, host.session_token)

    # Assert
    assert snapshot.state == "REVELACION"
    assert snapshot.result["impostor_alias"] == "Jugador 3"
    assert snapshot.result["tasa_deteccion"] == 1.0
    assert "prompt_version" not in snapshot.result


@pytest.mark.integration
def test_error_sin_cuerpo_json_es_malformed_request(http_contract: str) -> None:
    """Un error no-2xx sin cuerpo JSON válido se traduce a malformed_request (400)."""
    # Arrange
    client = HttpSospechAI(base_url=http_contract)
    host, _ = _http_started_room(client)

    # Act
    with pytest.raises(ApiError) as exc_info:
        client.submit_message(
            host.room_code, host.session_token, "malformed_error_body"
        )

    # Assert
    assert exc_info.value.code == "malformed_request"
    assert exc_info.value.http_status == 400


@pytest.mark.integration
def test_error_de_red_es_internal_sin_detalle_del_proveedor() -> None:
    """Un fallo de red se traduce a ApiError("internal", 500) sin detalle del proveedor."""
    # Arrange
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    dead_port = probe.getsockname()[1]
    probe.close()
    client = HttpSospechAI(base_url=f"http://127.0.0.1:{dead_port}")

    # Act
    with pytest.raises(ApiError) as exc_info:
        client.get_state("AB12C", "token_cualquiera")

    # Assert
    assert exc_info.value.code == "internal"
    assert exc_info.value.http_status == 500
    assert exc_info.value.message == "El orquestador no está disponible (error de red)."


@pytest.mark.integration
def test_selector_http_usa_sospeschai_orchestrator_url(
    monkeypatch: pytest.MonkeyPatch, http_contract: str
) -> None:
    """El swap localizado a http usa la base URL de SOSPECHAI_ORCHESTRATOR_URL (UIF-07)."""
    # Arrange
    monkeypatch.setenv("SOSPECHAI_UI_SOURCE", "http")
    monkeypatch.setenv("SOSPECHAI_ORCHESTRATOR_URL", http_contract)

    # Act
    identity = create_room()

    # Assert
    assert identity.alias == "Jugador 1"
    assert identity.room_code.isupper()
    assert ("POST", "/rooms", None) in _ContractHandler.request_log
