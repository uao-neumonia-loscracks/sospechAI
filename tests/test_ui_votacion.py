"""Pruebas de la apertura de votación del anfitrión y del polling estable (UIV-01…UIV-05).

Cubren el helper puro `mostrar_open_voting` (UIV-01), la firma de snapshot sin
`remaining_seconds` (UIV-03) y el wiring del callback `on_open_voting` en el
contexto (UIV-05c). Sin AppTest (D6): todo es AAA sobre funciones puras.
"""

import pytest

from src.ui.api import ChatMessage, StateSnapshot
from src.ui.app import _snapshot_sig
from src.ui.router import mostrar_open_voting
from src.ui.screens.context import ScreenContext


def _snapshot(state: str, remaining_seconds: float | None = 30.0) -> StateSnapshot:
    """Instantánea mínima del contrato §7.1 para ejercitar la firma."""
    return StateSnapshot(
        state=state,
        round_number=1,
        rounds=2,
        max_words=20,
        players=["Jugador 1", "Jugador 2", "Jugador 3"],
        messages=[
            ChatMessage(round_number=1, alias="Jugador 2", text="Sospecho de la IA")
        ],
        votes_received=0,
        remaining_seconds=remaining_seconds,
        result=None,
    )


def test_mostrar_open_voting_anfitrion_en_discusion() -> None:
    """El anfitrión ve el botón solo durante la discusión (UIV-01)."""
    # Arrange
    state = "DISCUSION"
    alias = "Jugador 1"

    # Act
    visible = mostrar_open_voting(state, alias)

    # Assert
    assert visible is True


@pytest.mark.parametrize(
    ("state", "alias"),
    [
        ("DISCUSION", "Jugador 2"),
        ("RONDA", "Jugador 1"),
        ("VOTACION", "Jugador 1"),
        ("REVELACION", "Jugador 1"),
        (None, "Jugador 1"),
    ],
)
def test_mostrar_open_voting_no_visible_fuera_de_alcance(
    state: str | None, alias: str
) -> None:
    """No anfitrión o fuera de DISCUSION: el botón no se muestra (UIV-01)."""
    # Act
    visible = mostrar_open_voting(state, alias)

    # Assert
    assert visible is False


def test_snapshot_sig_ignora_el_tick_del_timer() -> None:
    """Dos instantáneas iguales salvo remaining_seconds tienen la misma firma (UIV-03)."""
    # Arrange
    antes = _snapshot("DISCUSION", remaining_seconds=35.0)
    despues = _snapshot("DISCUSION", remaining_seconds=34.0)

    # Act
    sig_antes = _snapshot_sig(antes)
    sig_despues = _snapshot_sig(despues)

    # Assert
    assert sig_antes == sig_despues


def test_snapshot_sig_detecta_el_cambio_a_votacion() -> None:
    """DISCUSION→VOTACION altera la firma aunque el resto sea igual (UIV-03)."""
    # Arrange
    discusion = _snapshot("DISCUSION", remaining_seconds=35.0)
    votacion = _snapshot("VOTACION", remaining_seconds=35.0)

    # Act
    sig_discusion = _snapshot_sig(discusion)
    sig_votacion = _snapshot_sig(votacion)

    # Assert
    assert sig_discusion != sig_votacion


def test_on_open_voting_default_none_y_callback_preservado() -> None:
    """El contexto expone on_open_voting con default None y conserva el provisto (UIV-05c)."""
    # Arrange

    def _abrir() -> None:
        """Callback de apertura de la prueba."""

    # Act
    por_defecto = ScreenContext()
    provisto = ScreenContext(on_open_voting=_abrir)

    # Assert
    assert por_defecto.on_open_voting is None
    assert provisto.on_open_voting is _abrir
