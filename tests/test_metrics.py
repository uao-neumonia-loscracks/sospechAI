"""Pruebas AAA de las funciones puras de métricas y tarifas."""

import pytest

from src.common.metrics import Pricing, estimated_cost_usd, latency_p95, rate


def test_rate_with_zero_total_returns_none() -> None:
    """No se inventa una tasa sobre una muestra vacía."""
    # Arrange
    hits, total = 3, 0
    # Act
    result = rate(hits=hits, total=total)
    # Assert
    assert result is None


def test_rate_is_the_exact_quotient() -> None:
    """La proporción es el cociente entre aciertos y total."""
    # Arrange
    hits, total = 2, 4
    # Act
    result = rate(hits=hits, total=total)
    # Assert
    assert result == pytest.approx(0.5)


def test_rate_with_zero_hits_is_a_real_zero() -> None:
    """Cero aciertos sobre una muestra válida es 0.0, no None."""
    # Arrange
    hits, total = 0, 5
    # Act
    result = rate(hits=hits, total=total)
    # Assert
    assert result == 0.0


def test_latency_p95_with_empty_sequence_returns_none() -> None:
    """Sin latencias no hay percentil que calcular."""
    # Arrange
    latencies: list[float] = []
    # Act
    result = latency_p95(latencies)
    # Assert
    assert result is None


def test_latency_p95_with_single_element_returns_it() -> None:
    """Con una sola muestra el percentil 95 es ese valor."""
    # Arrange
    latencies = [42.0]
    # Act
    result = latency_p95(latencies)
    # Assert
    assert result == pytest.approx(42.0)


def test_latency_p95_interpolates_between_ranks() -> None:
    """Con cinco muestras el P95 interpola y no es ni la mediana ni el máximo.

    Posición (5 - 1) * 0.95 = 3.8: interpola entre 4.0 (índice 3) y 100.0
    (índice 4) con peso 0.8, resultado 80.8.
    """
    # Arrange
    latencies = [1.0, 2.0, 3.0, 4.0, 100.0]
    # Act
    result = latency_p95(latencies)
    # Assert
    assert result == pytest.approx(80.8)


def test_latency_p95_is_order_independent() -> None:
    """El percentil no depende del orden de llegada de las muestras."""
    # Arrange
    latencies = [100.0, 3.0, 1.0, 4.0, 2.0]
    # Act
    result = latency_p95(latencies)
    # Assert
    assert result == pytest.approx(80.8)


def test_estimated_cost_without_pricing_returns_none() -> None:
    """Sin tarifas (ADR-006 pendiente) no hay costo que estimar."""
    # Arrange
    pricing = None
    # Act
    result = estimated_cost_usd(
        prompt_tokens=100,
        completion_tokens=50,
        cached_tokens=25,
        pricing=pricing,
    )
    # Assert
    assert result is None


def test_estimated_cost_bills_cached_tokens_once() -> None:
    """Los cacheados se cobran a su tarifa y no se suman dos veces al prompt.

    El prompt facturable excluye los cacheados: si se cobraran también a
    tarifa de prompt, el total sería mayor (doble cobro).
    """
    # Arrange
    pricing = Pricing(
        prompt_per_1k_usd=10.0,
        completion_per_1k_usd=20.0,
        cached_per_1k_usd=5.0,
    )
    # Act
    result = estimated_cost_usd(
        prompt_tokens=1_000,
        completion_tokens=500,
        cached_tokens=300,
        pricing=pricing,
    )
    # Assert
    prompt_bill = (1_000 - 300) * 10.0 / 1000.0
    completion_bill = 500 * 20.0 / 1000.0
    cached_bill = 300 * 5.0 / 1000.0
    assert result == pytest.approx(prompt_bill + completion_bill + cached_bill)
    assert result == pytest.approx(7.0 + 10.0 + 1.5)
