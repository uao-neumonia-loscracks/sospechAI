"""Identidad de sesión: tokens opacos, salas y host ligados por el servidor.

El almacén de sesiones es la única fuente de identidad del servidor
multijugador: emite un token por jugador, lo liga 1:1 a un alias asignado
por el dominio y deriva el host de quién creó la sala.
"""

import secrets

import pytest

from src.orchestrator.game import Game
from src.orchestrator.session import IssuedIdentity, Room, SessionStore


def new_game() -> Game:
    """Partida fresca sin ventana de tiempo para aislar la identidad."""
    return Game(rounds=1, round_timeout=None)


def test_create_issues_host_identity() -> None:
    """Crear una sala emite token, alias Jugador 1 y código de 5 caracteres."""
    store = SessionStore()
    game = new_game()

    identity = store.create(game=game)
    room = store.room(identity.room_code)

    assert isinstance(identity, IssuedIdentity)
    assert identity.session_token
    assert identity.alias == "Jugador 1"
    assert len(identity.room_code) == 5
    assert identity.room_code.isupper()
    assert identity.room_code.isalnum()
    assert store.alias_for(room, identity.session_token) == "Jugador 1"
    assert store.is_host(room, identity.session_token)


def test_join_issues_a_distinct_identity() -> None:
    """Unirse emite otro token y el alias Jugador 2 en la misma sala."""
    store = SessionStore()
    host = store.create(game=new_game())
    room = store.room(host.room_code)

    guest = store.join(room.code, game=room.game)

    assert guest is not None
    assert isinstance(guest, IssuedIdentity)
    assert guest.session_token != host.session_token
    assert guest.alias == "Jugador 2"
    assert guest.room_code == host.room_code
    assert store.room(guest.room_code) is room
    assert store.alias_for(room, guest.session_token) == "Jugador 2"


def test_public_api_has_no_forge_path() -> None:
    """La superficie pública no ofrece reasignar un alias a un token."""
    store = SessionStore()

    public_api = {name for name in dir(store) if not name.startswith("_")}

    assert public_api == {"alias_for", "create", "is_host", "join", "room"}


def test_alias_binding_is_stable_and_one_to_one() -> None:
    """Un token resuelve siempre al mismo alias; otro join nunca lo reasigna."""
    store = SessionStore()
    host = store.create(game=new_game())
    room = store.room(host.room_code)

    guest = store.join(room.code, game=room.game)

    assert store.alias_for(room, host.session_token) == "Jugador 1"
    assert store.alias_for(room, guest.session_token) == "Jugador 2"
    third = store.join(room.code, game=room.game)
    assert third is not None and third.session_token != guest.session_token
    assert store.alias_for(room, guest.session_token) == "Jugador 2"
    assert store.alias_for(room, third.session_token) == "Jugador 3"
    assert store.alias_for(room, host.session_token) == "Jugador 1"


def test_unknown_and_foreign_tokens_resolve_to_none() -> None:
    """Tokens ajenos o inventados no resuelven alias en esta sala."""
    store = SessionStore()
    host = store.create(game=new_game())
    room_a = store.room(host.room_code)
    other = store.create(game=new_game())
    room_b = store.room(other.room_code)

    assert store.alias_for(room_a, "nunca-emitido") is None
    assert store.alias_for(room_a, other.session_token) is None
    assert store.alias_for(room_b, host.session_token) is None


def test_room_lookup_is_case_insensitive() -> None:
    """Buscar con minúsculas encuentra la sala; el código emitido queda en mayúsculas."""
    store = SessionStore()
    host = store.create(game=new_game())

    room = store.room(host.room_code.lower())

    assert room is not None
    assert room.code == host.room_code
    assert room.code.isupper()
    assert store.room("ZZZZZ") is None


def test_join_unknown_room_returns_none() -> None:
    """Unirse a una sala inexistente no emite identidad."""
    store = SessionStore()

    identity = store.join("NOEXI", game=new_game())

    assert identity is None


def test_room_code_collision_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un código repetido obliga a regenerar sin salas compartidas."""
    values = iter(["A"] * 10 + ["B"] * 5)
    calls = 0

    def fixed_choice(sequence: str) -> str:
        nonlocal calls
        calls += 1
        return next(values)

    monkeypatch.setattr(secrets, "choice", fixed_choice)
    store = SessionStore()

    first = store.create(game=new_game())
    second = store.create(game=new_game())

    assert first.room_code == "AAAAA"
    assert second.room_code == "BBBBB"
    assert first.room_code != second.room_code
    assert calls == 15


def test_room_codes_are_unique_across_creations() -> None:
    """Cada sala creada recibe un código distinto de los anteriores."""
    store = SessionStore()

    codes = [store.create(game=new_game()).room_code for _ in range(5)]

    assert len(codes) == len(set(codes))


def test_is_host_only_for_the_creator() -> None:
    """El host es exactamente quien creó la sala y nadie más."""
    store = SessionStore()
    host = store.create(game=new_game())
    room = store.room(host.room_code)
    guest = store.join(room.code, game=room.game)

    assert store.is_host(room, host.session_token)
    assert not store.is_host(room, guest.session_token)
    assert not store.is_host(room, "token-falso")


def test_room_exposes_identity_parts_and_lock() -> None:
    """La sala expone código, partida, host, jugadores y su candado."""
    store = SessionStore()
    host = store.create(game=new_game())
    room = store.room(host.room_code)

    assert isinstance(room, Room)
    assert isinstance(room.game, Game)
    assert room.host_token == host.session_token
    assert set(room.players) == {host.session_token}
    assert list(room.players.values()) == ["Jugador 1"]
    assert hasattr(room, "lock")
