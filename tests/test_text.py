"""Normalización única: una sola implementación para los tres servicios.

AGENTS.md exige que la normalización viva en UNA sola función. Estas pruebas
existen para fallar el día que alguien vuelva a copiar el algoritmo en vez de
importarlo: comparan identidad de objeto, no equivalencia de comportamiento.
"""

import pytest

from src.common.text import normalize_text
from src.impostor_engine import guards
from src.orchestrator import game
from src.ui import words


class TestNormalizeText:
    """Comportamiento de la implementación única."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("  hola  mundo  ", "hola mundo"),
            ("\tcafe\u0301   rico\n", "café rico"),
            ("una", "una"),
            ("   \n\t  ", ""),
            ("a\u0301", "á"),
            ("  café  ", "café"),
            ("ÁRBOL ÑANDÚ", "ÁRBOL ÑANDÚ"),
        ],
    )
    def test_nfc_and_whitespace_collapse(self, raw: str, expected: str) -> None:
        """NFC combina diacríticos y split colapsa todo tipo de espacios."""
        assert normalize_text(raw) == expected


class TestSingleImplementation:
    """Los tres servicios apuntan al mismo objeto, no a copias equivalentes."""

    def test_el_engine_usa_la_misma_funcion(self) -> None:
        """guards expone exactamente la función de src/common/text."""
        assert guards.normalize_text is normalize_text

    def test_el_orquestador_usa_la_misma_funcion(self) -> None:
        """game expone exactamente la función de src/common/text."""
        assert game.normalize_text is normalize_text

    def test_la_ui_usa_la_misma_funcion(self) -> None:
        """words expone exactamente la función de src/common/text."""
        assert words.normalize_text is normalize_text
