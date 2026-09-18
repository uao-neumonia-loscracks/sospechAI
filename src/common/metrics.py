"""Métricas puras sobre números, sin estado ni dependencias del dominio.

Este módulo pertenece a src/common: recibe números y devuelve números.
No conoce votos, partidas, HTTP ni gRPC (regla de AGENTS.md).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass


def rate(hits: int, total: int) -> float | None:
    """Calcular la proporción de aciertos sobre el total de eventos.

    Devuelve None cuando total es 0, en lugar de inventar un 0.0 o lanzar
    ZeroDivisionError: una proporción sobre cero eventos no está definida.
    """
    if total == 0:
        return None
    return hits / total


def latency_p95(latencies_ms: Sequence[float]) -> float | None:
    """Calcular el percentil 95 de latencias por rango más próximo.

    Criterio del plan: ordenar la muestra y tomar el índice ceil(0.95 * n) - 1
    en base 0 (con 30 muestras, el índice 28). Documentado en
    docs/verificaciones/2026-09-09-benchmark-r1.md y REVISION_CAMBIO_API.md.
    Devuelve None si la secuencia está vacía.
    """
    if not latencies_ms:
        return None
    ordered = sorted(latencies_ms)
    index = math.ceil(0.95 * len(ordered)) - 1
    return ordered[index]


@dataclass(frozen=True)
class Pricing:
    """Tarifas del proveedor en USD por cada mil tokens.

    Los valores por defecto son las tarifas publicadas convertidas a USD por
    1K, fijadas por el ADR-006 (docs/adr/ADR-006-costos.md): prompt 0,00017,
    completion 0,0002 y cached 0,000136. Por eso Pricing() ya representa las
    tarifas canónicas sin argumentos.
    """

    prompt_per_1k_usd: float = 0.00017
    completion_per_1k_usd: float = 0.0002
    cached_per_1k_usd: float = 0.000136


def estimated_cost_usd(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int,
    pricing: Pricing | None,
) -> float | None:
    """Estimar el costo en USD de una generación según las tarifas recibidas.

    Los tokens cacheados se facturan a su propia tarifa y no se suman dos
    veces al prompt: el prompt facturable excluye los cacheados, que van a
    su tarifa separada. Devuelve None si no hay tarifas definidas.
    """
    if pricing is None:
        return None
    billable_prompt = prompt_tokens - cached_tokens
    return (
        billable_prompt * pricing.prompt_per_1k_usd
        + completion_tokens * pricing.completion_per_1k_usd
        + cached_tokens * pricing.cached_per_1k_usd
    ) / 1000.0
