"""Derivación pura del contenido de la pantalla de revelación (D6).

Este módulo NO importa `streamlit`: cada bloque del resultado (impostor,
votos/recuentos, acierto, transcript con `is_ai`, `prompt_version`) se deriva
con 1 función y se degrada por `.get()` si el servidor v1.0 no trae la clave
(UIF-18). `is_ai` solo se renderiza en la pantalla de revelación (§9).
"""

from collections.abc import Mapping
from typing import Any


def revelation_impostor(result: Mapping[str, Any]) -> str:
    """Alias del impostor desde la clave autoritativa del resultado."""
    return result.get("impostor_alias", "")


def revelation_votes(result: Mapping[str, Any]) -> list[dict[str, str]]:
    """Votos `{voter: suspect}` ordenados por alias del votante."""
    votes = result.get("votes", {})
    return [
        {"voter": voter, "suspect": suspect} for voter, suspect in sorted(votes.items())
    ]


def revelation_vote_counts(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Recuentos por sospechoso: conteo descendente y desempate alfabético."""
    counts = result.get("vote_counts", {})
    return [
        {"suspect": suspect, "count": count}
        for suspect, count in sorted(
            counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]


def group_verdict(result: Mapping[str, Any]) -> tuple[bool | None, str | None]:
    """Acierto del grupo y motivo de cierre: `(verdict, interruption_reason)`.

    Interrupción presente → `(None, interruption_reason)`; sin tasa (v1.0 o
    interrumpida) no se inventa acierto; con `tasa_deteccion > 0` → `(True, None)`.
    """
    interruption = result.get("interruption_reason")
    if interruption:
        return None, interruption
    tasa = result.get("tasa_deteccion")
    if tasa is None:
        return None, None
    return tasa > 0, None


def revelation_transcript(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Transcript preservando `round_number`, `alias`, `text` e `is_ai` (§9)."""
    return [dict(message) for message in result.get("transcript", [])]


def prompt_version_text(result: Mapping[str, Any]) -> str:
    """Texto visible de la versión del prompt; genérico si v1.0 no la emite."""
    version = result.get("prompt_version")
    if version is None:
        return "Versión del prompt del impostor: no informada"
    return f"Prompt del impostor: {version}"


def revelation_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    """Componer todo el contenido derivado de la revelación en un único dict."""
    return {
        "impostor": revelation_impostor(result),
        "votes": revelation_votes(result),
        "vote_counts": revelation_vote_counts(result),
        "verdict": group_verdict(result),
        "transcript": revelation_transcript(result),
        "prompt_version": prompt_version_text(result),
    }
