"""Adaptador de MLflow para registrar partidas terminadas como runs.

Vive en src/orchestrator porque sí conoce el dominio del juego (partidas,
votos, rondas): traduce el resultado de Game.result() y el uso reportado
por el engine a params, métricas y artifacts de MLflow. El engine nunca
importa MLflow ni sabe que existe.
"""

import json
import os
import tempfile
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from types import ModuleType

from src.common.metrics import Pricing, estimated_cost_usd, latency_p95, rate


@dataclass(frozen=True)
class EngineUsage:
    """Uso acumulado que el engine reporta por trailing metadata.

    Se construye concatenando los pares de todas las llamadas de una
    partida: los contadores escalares se suman, las latencias se acumulan
    (una por llamada, calls deriva de su cantidad) y model_id conserva la
    última ocurrencia porque la configuración del servidor no cambia a
    mitad de partida.
    """

    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    latencies_ms: tuple[float, ...]
    attempts: int
    character_breaks: int
    calls: int
    model_id: str

    @classmethod
    def from_trailing_metadata(cls, pairs: Sequence[tuple[str, str]]) -> "EngineUsage":
        """Parsear la metadata del engine con semántica fail-closed.

        Claves conocidas: x-usage-prompt-tokens, x-usage-completion-tokens,
        x-usage-cached-tokens, x-latency-total-ms (repetible, una por
        llamada), x-attempts, x-character-break (0/1) y x-model-id. Las
        claves desconocidas se ignoran en silencio; una clave conocida
        malformada lanza ValueError: nunca un default silencioso que
        contamine el experimento.
        """
        prompt_tokens = completion_tokens = cached_tokens = 0
        attempts = character_breaks = 0
        latencies: list[float] = []
        model_id: str | None = None
        for key, value in pairs:
            if key == "x-usage-prompt-tokens":
                prompt_tokens += cls._parse_int(key, value)
            elif key == "x-usage-completion-tokens":
                completion_tokens += cls._parse_int(key, value)
            elif key == "x-usage-cached-tokens":
                cached_tokens += cls._parse_int(key, value)
            elif key == "x-latency-total-ms":
                latencies.append(cls._parse_float(key, value))
            elif key == "x-attempts":
                attempts += cls._parse_int(key, value)
            elif key == "x-character-break":
                character_breaks += cls._parse_flag(key, value)
            elif key == "x-model-id":
                model_id = value
        return cls(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            latencies_ms=tuple(latencies),
            attempts=attempts,
            character_breaks=character_breaks,
            calls=len(latencies),
            model_id=model_id or "",
        )

    @staticmethod
    def _parse_int(key: str, value: str) -> int:
        """Convertir un entero de metadata o reportar el valor malformado."""
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"Valor malformado para {key}: {value!r}") from exc

    @staticmethod
    def _parse_float(key: str, value: str) -> float:
        """Convertir una latencia de metadata o reportar el valor malformado."""
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError(f"Valor malformado para {key}: {value!r}") from exc

    @staticmethod
    def _parse_flag(key: str, value: str) -> int:
        """Convertir una bandera 0/1 o reportar el valor malformado."""
        if value not in ("0", "1"):
            raise ValueError(f"Valor malformado para {key}: {value!r}")
        return int(value)


@dataclass(frozen=True)
class RunParams:
    """Parámetros fijos de una partida, registrados como params del run."""

    model_id: str
    engine_backend: str
    provider: str
    temperature: float
    top_p: float
    system_prompt_version: str
    max_words: int
    n_players: int
    n_rondas: int


def log_game_run(
    *,
    params: RunParams,
    result: Mapping[str, object],
    usage: EngineUsage | None,
    tracking_uri: str | None = None,
    pricing: Pricing | None = None,
) -> str | None:
    """Registrar una partida terminada en MLflow y devolver el id del run.

    Abre un run, registra params, métricas y artifacts, y lo cierra. Sin
    URI de tracking (argumento ni variable MLFLOW_TRACKING_URI) no hace
    nada y devuelve None: la suite de pruebas y la demo funcionan sin
    servidor MLflow. Las métricas que dependen de usage solo se registran
    si usage llega, y tasa_deteccion solo si la partida fue válida.
    """
    uri = tracking_uri or os.environ.get("MLFLOW_TRACKING_URI")
    if uri is None:
        return None
    mlflow = _import_mlflow()
    mlflow.set_tracking_uri(uri)
    run = mlflow.start_run()
    try:
        for name, value in asdict(params).items():
            mlflow.log_param(name, value)
        _log_metrics(mlflow, result, usage, pricing)
        _log_artifacts(mlflow, result)
        return run.info.run_id
    finally:
        mlflow.end_run()


def _import_mlflow() -> ModuleType:
    """Importar mlflow recién cuando hay una URI de tracking configurada.

    Importarlo de forma diferida mantiene la suite rápida y evita efectos
    secundarios del import cuando no se usa tracking. Verificado: mlflow
    3.16.1 importa sin warnings bajo filterwarnings=error; si una
    dependencia transitiva emitiera advertencias al importar, este es el
    único punto a ajustar, con un filtro acotado a esta importación.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        import mlflow

    return mlflow


def _log_metrics(
    mlflow: ModuleType,
    result: Mapping[str, object],
    usage: EngineUsage | None,
    pricing: Pricing | None,
) -> None:
    """Registrar las métricas del run, omitiendo las que no aplican.

    Nunca se inventan ceros: tasa_deteccion solo si la partida fue válida,
    las tasas solo si su denominador es válido y las métricas de uso solo
    si usage llegó.
    """
    metrics: dict[str, float] = {}
    if result.get("valid_game") is True and isinstance(
        result.get("tasa_deteccion"), (int, float)
    ):
        metrics["tasa_deteccion"] = float(result["tasa_deteccion"])
    if isinstance(result.get("rounds"), int):
        metrics["rondas_sobrevividas"] = float(result["rounds"])
    falsas = _false_accusation_rate(result)
    if falsas is not None:
        metrics["tasa_falsa_acusacion"] = falsas
    if usage is not None:
        metrics.update(_usage_metrics(usage, pricing))
    for nombre, valor in metrics.items():
        mlflow.log_metric(nombre, valor)


def _false_accusation_rate(result: Mapping[str, object]) -> float | None:
    """Calcular la tasa de votos dirigidos a alguien que no es el impostor."""
    impostor = result.get("impostor_alias")
    votes = result.get("votes")
    if not isinstance(impostor, str) or not isinstance(votes, Mapping):
        return None
    falsas = sum(1 for suspect in votes.values() if suspect != impostor)
    return rate(falsas, len(votes))


def _usage_metrics(usage: EngineUsage, pricing: Pricing | None) -> dict[str, float]:
    """Calcular las métricas derivadas del uso del engine, sin ceros falsos."""
    metrics: dict[str, float] = {}
    tasa_ruptura = rate(usage.character_breaks, usage.calls)
    if tasa_ruptura is not None:
        metrics["tasa_ruptura_personaje"] = tasa_ruptura
    p95 = latency_p95(usage.latencies_ms)
    if p95 is not None:
        metrics["latencia_p95"] = p95
    metrics["tokens_totales"] = float(usage.prompt_tokens + usage.completion_tokens)
    costo = estimated_cost_usd(
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        cached_tokens=usage.cached_tokens,
        pricing=pricing,
    )
    if costo is not None:
        metrics["costo_estimado"] = costo
    return metrics


def _log_artifacts(mlflow: ModuleType, result: Mapping[str, object]) -> None:
    """Registrar el transcript anonimizado y la matriz de votos como JSON.

    La clave is_ai se quita del transcript para que el artefacto no revele
    el rol del impostor. Los JSON se escriben en un directorio temporal
    (ensure_ascii=False, indent=2) y se adjuntan con mlflow.log_artifact;
    el directorio se limpia al salir del contexto.
    """
    transcript = result.get("transcript")
    votes = result.get("votes")
    with tempfile.TemporaryDirectory() as tmp_dir:
        if isinstance(transcript, list):
            anonymous = [
                {key: value for key, value in message.items() if key != "is_ai"}
                for message in transcript
                if isinstance(message, Mapping)
            ]
            _write_artifact(
                mlflow, Path(tmp_dir) / "transcript_anonimo.json", anonymous
            )
        if isinstance(votes, Mapping):
            _write_artifact(mlflow, Path(tmp_dir) / "matriz_votos.json", votes)


def _write_artifact(mlflow: ModuleType, path: Path, payload: object) -> None:
    """Escribir un artefacto JSON con formato estable y adjuntarlo al run."""
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    mlflow.log_artifact(str(path))
