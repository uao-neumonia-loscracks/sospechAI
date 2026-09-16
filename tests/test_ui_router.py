"""Pruebas del router puro de la UI: transición de pantalla y frecuencia de polling.

Cubren UIF-02 (el consentimiento no se salta), UIF-06 (frecuencias del contrato),
UIF-09 (la pantalla se deriva del estado) y UIF-11 (pruebas AAA sin Streamlit).
"""

import importlib

import pytest

from src.ui.router import Screen, poll_interval_seconds, resolve_screen

SCREEN_MODULES = (
    "src.ui.screens.consent",
    "src.ui.screens.lobby",
    "src.ui.screens.chat",
    "src.ui.screens.voting",
)


def test_resolve_screen_without_consent_always_returns_consent() -> None:
    """Sin consentimiento aceptado ninguna pantalla posterior es accesible."""
    # Arrange
    states = (None, "LOBBY", "RONDA", "DISCUSION", "VOTACION", "REVELACION")

    # Act
    resolved = [resolve_screen(consent_agreed=False, state=state) for state in states]

    # Assert
    assert resolved == [Screen.CONSENT] * len(states)


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (None, Screen.LOBBY),
        ("LOBBY", Screen.LOBBY),
        ("RONDA", Screen.CHAT),
        ("DISCUSION", Screen.CHAT),
        ("VOTACION", Screen.VOTING),
        ("REVELACION", Screen.VOTING),
    ],
)
def test_resolve_screen_after_consent_maps_state_to_screen(
    state: str | None, expected: Screen
) -> None:
    """Con consentimiento aceptado, el estado de cable decide la pantalla activa."""
    # Arrange
    consent_agreed = True

    # Act
    resolved = resolve_screen(consent_agreed=consent_agreed, state=state)

    # Assert
    assert resolved == expected


@pytest.mark.parametrize("state", ["RONDA", "DISCUSION", "VOTACION"])
def test_poll_interval_is_one_second_during_play(state: str) -> None:
    """Los estados de juego se refrescan cada segundo (contrato §14.1)."""
    # Arrange
    expected = 1.0

    # Act
    interval = poll_interval_seconds(state)

    # Assert
    assert interval == expected


@pytest.mark.parametrize("state", [None, "LOBBY", "REVELACION"])
def test_poll_interval_is_two_and_a_half_seconds_outside_play(
    state: str | None,
) -> None:
    """Lobby y revelación usan la banda de 2 a 3 segundos (contrato §14.1)."""
    # Arrange
    expected = 2.5

    # Act
    interval = poll_interval_seconds(state)

    # Assert
    assert interval == expected


def test_app_and_screens_import_and_start_at_consent() -> None:
    """El arranque importa limpio y la primera pantalla derivada es consentimiento."""
    # Arrange
    app_module = importlib.import_module("src.ui.app")

    # Act
    screens = [importlib.import_module(name) for name in SCREEN_MODULES]
    initial = resolve_screen(consent_agreed=False, state=None)

    # Assert
    assert callable(app_module.main)
    assert all(callable(screen.render) for screen in screens)
    assert initial == Screen.CONSENT
