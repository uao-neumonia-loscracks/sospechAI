"""Pruebas AAA del facade ``api.py`` y del fake sin red (UIF-07, UIF-11).

Cubren las tareas 2.3 (formas exactas del contrato, máquina congelada, alias
con la IA en último lugar y catálogo de errores) y 2.6 (bloqueo combinado:
mensaje dentro del límite aceptado y visible; sobre el límite, ``too_many_words``
y ausencia de la conversación).
"""

import dataclasses

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
)
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
    "transcript",
)


def _started_room() -> tuple[RoomIdentity, RoomIdentity]:
    """Abrir una sala con dos humanos en la primera ronda (solo Arrange)."""
    host = create_room()
    guest = join_room(host.room_code)
    start(host.room_code, host.session_token)
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
