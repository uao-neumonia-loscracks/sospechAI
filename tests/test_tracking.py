"""Pruebas AAA del adaptador de tracking a MLflow del orquestador."""

import json
from pathlib import Path

import pytest
from mlflow.tracking import MlflowClient

from src.common.metrics import Pricing
from src.orchestrator.tracking import EngineUsage, RunParams, log_game_run


def _params() -> RunParams:
    """Parámetros típicos de una partida de práctica."""
    return RunParams(
        model_id="Qwen/Qwen2.5-7B-Instruct",
        engine_backend="hf-router",
        provider="featherless",
        temperature=0.7,
        top_p=0.95,
        system_prompt_version="v2",
        max_words=15,
        n_players=4,
        n_rondas=3,
    )


def _result() -> dict[str, object]:
    """Resultado con la forma del contrato de Game.result(), válido."""
    return {
        "state": "REVELACION",
        "impostor_alias": "Jugador 4",
        "rounds": 3,
        "max_words": 15,
        "votes": {
            "Jugador 1": "Jugador 4",
            "Jugador 2": "Jugador 4",
            "Jugador 3": "Jugador 1",
        },
        "vote_counts": {"Jugador 4": 2, "Jugador 1": 1},
        "scores": {"Jugador 1": 1, "Jugador 2": 1, "Jugador 3": 0},
        "valid_game": True,
        "interruption_reason": None,
        "tasa_deteccion": 2 / 3,
        "transcript": [
            {
                "round_number": 1,
                "alias": "Jugador 1",
                "text": "Hola a todos.",
                "is_ai": False,
            },
            {
                "round_number": 1,
                "alias": "Jugador 4",
                "text": "Soy nuevo por acá.",
                "is_ai": True,
            },
            {
                "round_number": 2,
                "alias": "Jugador 2",
                "text": "¿Quién sos?",
                "is_ai": False,
            },
        ],
    }


def _usage() -> EngineUsage:
    """Uso acumulado de cinco llamadas del engine durante la partida."""
    return EngineUsage(
        prompt_tokens=1_000,
        completion_tokens=500,
        cached_tokens=300,
        latencies_ms=(1.0, 2.0, 3.0, 4.0, 100.0),
        attempts=4,
        character_breaks=1,
        calls=5,
        model_id="Qwen/Qwen2.5-7B-Instruct",
    )


def _pricing() -> Pricing:
    """Tarifas de prueba con tarifa de cacheado distinta a la de prompt."""
    return Pricing(
        prompt_per_1k_usd=10.0,
        completion_per_1k_usd=20.0,
        cached_per_1k_usd=5.0,
    )


def test_from_trailing_metadata_parses_complete_metadata() -> None:
    """Una llamada completa del engine produce el acumulado esperado."""
    # Arrange
    pairs = [
        ("x-usage-prompt-tokens", "120"),
        ("x-usage-completion-tokens", "45"),
        ("x-usage-cached-tokens", "60"),
        ("x-latency-total-ms", "123.4"),
        ("x-attempts", "2"),
        ("x-character-break", "1"),
        ("x-model-id", "Qwen/Qwen2.5-7B-Instruct"),
    ]
    # Act
    usage = EngineUsage.from_trailing_metadata(pairs)
    # Assert
    assert usage == EngineUsage(
        prompt_tokens=120,
        completion_tokens=45,
        cached_tokens=60,
        latencies_ms=(123.4,),
        attempts=2,
        character_breaks=1,
        calls=1,
        model_id="Qwen/Qwen2.5-7B-Instruct",
    )


def test_from_trailing_metadata_ignores_unknown_keys() -> None:
    """Claves fuera del contrato (estado, TTFT, regeneraciones) se ignoran."""
    # Arrange
    pairs = [
        ("x-usage-prompt-tokens", "10"),
        ("x-status", "ok"),
        ("x-latency-ttft-ms", "12.3"),
        ("x-regenerations", "0"),
        ("x-model-id", "Qwen/Qwen2.5-7B-Instruct"),
    ]
    # Act
    usage = EngineUsage.from_trailing_metadata(pairs)
    # Assert
    assert usage.prompt_tokens == 10
    assert usage.latencies_ms == ()
    assert usage.calls == 0
    assert usage.model_id == "Qwen/Qwen2.5-7B-Instruct"


def test_from_trailing_metadata_accumulates_repeated_latency() -> None:
    """Dos llamadas suman contadores, acumulan latencias y derivan calls."""
    # Arrange
    first_call = [
        ("x-usage-prompt-tokens", "120"),
        ("x-usage-completion-tokens", "45"),
        ("x-latency-total-ms", "123.4"),
        ("x-attempts", "2"),
        ("x-character-break", "1"),
        ("x-model-id", "Qwen/Qwen2.5-7B-Instruct"),
    ]
    second_call = [
        ("x-usage-prompt-tokens", "80"),
        ("x-usage-completion-tokens", "30"),
        ("x-latency-total-ms", "456.7"),
        ("x-attempts", "1"),
        ("x-character-break", "0"),
        ("x-model-id", "Qwen/Qwen2.5-7B-Instruct"),
    ]
    # Act
    usage = EngineUsage.from_trailing_metadata(first_call + second_call)
    # Assert
    assert usage.prompt_tokens == 200
    assert usage.completion_tokens == 75
    assert usage.latencies_ms == (123.4, 456.7)
    assert usage.attempts == 3
    assert usage.character_breaks == 1
    assert usage.calls == 2


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("x-usage-prompt-tokens", "no-es-un-entero"),
        ("x-latency-total-ms", "rápido"),
        ("x-attempts", "1.5"),
        ("x-character-break", "2"),
    ],
)
def test_from_trailing_metadata_rejects_malformed_values(key: str, value: str) -> None:
    """Un valor malformado en una clave conocida es fail-closed (ValueError)."""
    # Arrange
    pairs = [("x-model-id", "modelo"), (key, value)]
    # Act
    with pytest.raises(ValueError, match=key):
        EngineUsage.from_trailing_metadata(pairs)
    # Assert — la afirmación es la excepción capturada arriba


def test_log_game_run_returns_none_without_tracking_uri(monkeypatch) -> None:
    """Sin URI de tracking (argumento ni entorno) no se abre ningún run."""
    # Arrange
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    # Act
    run_id = log_game_run(params=_params(), result=_result(), usage=_usage())
    # Assert
    assert run_id is None


def test_log_game_run_persists_params_and_status(tmp_path, monkeypatch) -> None:
    """Un run de file store queda FINISHED con todos los params registrados."""
    # Arrange
    monkeypatch.setenv("MLFLOW_ALLOW_FILE_STORE", "true")
    tracking_uri = f"file:{(tmp_path / 'mlruns').as_posix()}"
    # Act
    run_id = log_game_run(
        params=_params(), result=_result(), usage=_usage(), tracking_uri=tracking_uri
    )
    fetched = MlflowClient(tracking_uri=tracking_uri).get_run(run_id)
    # Assert
    assert run_id is not None
    assert fetched.info.status == "FINISHED"
    assert fetched.data.params["model_id"] == "Qwen/Qwen2.5-7B-Instruct"
    assert fetched.data.params["engine_backend"] == "hf-router"
    assert fetched.data.params["provider"] == "featherless"
    assert fetched.data.params["temperature"] == "0.7"
    assert fetched.data.params["top_p"] == "0.95"
    assert fetched.data.params["system_prompt_version"] == "v2"
    assert fetched.data.params["max_words"] == "15"
    assert fetched.data.params["n_players"] == "4"
    assert fetched.data.params["n_rondas"] == "3"


def test_log_game_run_persists_anonymous_artifacts(tmp_path, monkeypatch) -> None:
    """Los artifacts JSON quedan registrados, el transcript sin is_ai."""
    # Arrange
    monkeypatch.setenv("MLFLOW_ALLOW_FILE_STORE", "true")
    tracking_uri = f"file:{(tmp_path / 'mlruns').as_posix()}"
    dl_dir = tmp_path / "descargas"
    dl_dir.mkdir()
    # Act
    run_id = log_game_run(
        params=_params(), result=_result(), usage=_usage(), tracking_uri=tracking_uri
    )
    client = MlflowClient(tracking_uri=tracking_uri)
    artifact_paths = [artifact.path for artifact in client.list_artifacts(run_id)]
    transcript_path = client.download_artifacts(
        run_id, "transcript_anonimo.json", dl_dir
    )
    votes_path = client.download_artifacts(run_id, "matriz_votos.json", dl_dir)
    # Assert
    assert set(artifact_paths) == {
        "transcript_anonimo.json",
        "matriz_votos.json",
    }
    transcript = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
    votes = json.loads(Path(votes_path).read_text(encoding="utf-8"))
    assert all("is_ai" not in message for message in transcript)
    assert [m["alias"] for m in transcript] == ["Jugador 1", "Jugador 4", "Jugador 2"]
    assert votes == _result()["votes"]


def test_log_game_run_records_expected_metrics(tmp_path, monkeypatch) -> None:
    """Las métricas derivadas quedan con los valores calculados del dominio."""
    # Arrange
    monkeypatch.setenv("MLFLOW_ALLOW_FILE_STORE", "true")
    tracking_uri = f"file:{(tmp_path / 'mlruns').as_posix()}"
    # Act
    run_id = log_game_run(
        params=_params(),
        result=_result(),
        usage=_usage(),
        tracking_uri=tracking_uri,
        pricing=_pricing(),
    )
    metrics = MlflowClient(tracking_uri=tracking_uri).get_run(run_id).data.metrics
    # Assert
    assert metrics["tasa_deteccion"] == pytest.approx(2 / 3)
    assert metrics["rondas_sobrevividas"] == 3.0
    assert metrics["tasa_falsa_acusacion"] == pytest.approx(1 / 3)
    assert metrics["tasa_ruptura_personaje"] == pytest.approx(0.2)
    assert metrics["latencia_p95"] == pytest.approx(80.8)
    assert metrics["tokens_totales"] == 1_500.0
    assert metrics["costo_estimado"] == pytest.approx(18.5)


def test_log_game_run_without_usage_omits_usage_metrics(tmp_path, monkeypatch) -> None:
    """Sin uso del engine no se loguean métricas que dependen de él."""
    # Arrange
    monkeypatch.setenv("MLFLOW_ALLOW_FILE_STORE", "true")
    tracking_uri = f"file:{(tmp_path / 'mlruns').as_posix()}"
    # Act
    run_id = log_game_run(
        params=_params(),
        result=_result(),
        usage=None,
        tracking_uri=tracking_uri,
        pricing=_pricing(),
    )
    metrics = MlflowClient(tracking_uri=tracking_uri).get_run(run_id).data.metrics
    # Assert
    assert metrics["tasa_deteccion"] == pytest.approx(2 / 3)
    assert metrics["rondas_sobrevividas"] == 3.0
    assert metrics["tasa_falsa_acusacion"] == pytest.approx(1 / 3)
    assert "tasa_ruptura_personaje" not in metrics
    assert "latencia_p95" not in metrics
    assert "tokens_totales" not in metrics
    assert "costo_estimado" not in metrics


def test_log_game_run_invalid_game_omits_tasa_deteccion(tmp_path, monkeypatch) -> None:
    """Una partida interrumpida no publica tasa_deteccion."""
    # Arrange
    monkeypatch.setenv("MLFLOW_ALLOW_FILE_STORE", "true")
    tracking_uri = f"file:{(tmp_path / 'mlruns').as_posix()}"
    invalid = dict(_result(), valid_game=False, tasa_deteccion=None)
    # Act
    run_id = log_game_run(
        params=_params(),
        result=invalid,
        usage=_usage(),
        tracking_uri=tracking_uri,
        pricing=_pricing(),
    )
    metrics = MlflowClient(tracking_uri=tracking_uri).get_run(run_id).data.metrics
    # Assert
    assert "tasa_deteccion" not in metrics
    assert metrics["rondas_sobrevividas"] == 3.0
    assert metrics["tasa_ruptura_personaje"] == pytest.approx(0.2)
