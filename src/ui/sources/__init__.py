"""Fuentes de datos intercambiables de la UI (contrato UI-orquestador, UIF-07)."""

from src.ui.sources.fake import FakeSospechAI
from src.ui.sources.http import HttpSospechAI

__all__ = ["FakeSospechAI", "HttpSospechAI"]
