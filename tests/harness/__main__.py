"""Jugar una partida de bots desde la consola y registrarla en SQLite.

Uso:
  uv run python -m tests.harness --bots 5
  uv run python -m tests.harness --bots 5 --engine 127.0.0.1:50051   # engine real

Sin `--engine` el impostor usa un engine doble determinista y no se llama a
ninguna API. Con `--engine` habla por gRPC con el engine real y consume la
Inference API: cada ronda cuesta una llamada.
"""

import argparse
import sys
from pathlib import Path

import grpc

from proto import impostor_pb2_grpc as rpc
from src.orchestrator.engine_client import EngineStub
from tests.harness.bots import HarnessConfig, ScriptedEngineStub
from tests.harness.runner import run_and_save

DEFAULT_DB = Path("data/practice/arnes_bots.sqlite3")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Interpretar las opciones del arnés."""
    parser = argparse.ArgumentParser(description="Arnés de jugadores bot (A10).")
    parser.add_argument("--bots", type=int, default=5, help="Bots humanos.")
    parser.add_argument("--rounds", type=int, default=2, help="Rondas.")
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Segundos simulados que tarda cada bot en responder.",
    )
    parser.add_argument("--timeout", type=float, default=20.0, help="Ventana (s).")
    parser.add_argument("--votes", choices=("fixed", "random"), default="fixed")
    parser.add_argument("--seed", type=int, default=0, help="Semilla de votos.")
    parser.add_argument("--prompt-version", default="v2", help="v1, v2 o v3.")
    parser.add_argument("--engine", help="host:puerto del engine real (opcional).")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite.")
    return parser.parse_args(argv)


def _connect(endpoint: str) -> EngineStub:
    """Abrir un canal gRPC al engine real y esperar a que esté listo."""
    channel = grpc.insecure_channel(endpoint)
    grpc.channel_ready_future(channel).result(timeout=5)
    return rpc.ImpostorEngineStub(channel)


def _report(result: dict, session_id: str, database: Path) -> None:
    """Imprimir el resumen de la partida."""
    print(f"Estado final: {result['state']}")
    print(f"Partida válida: {result['valid_game']}")
    if result["interruption_reason"]:
        print(f"Interrumpida por: {result['interruption_reason']}")
    print(f"Impostor: {result['impostor_alias']}")
    print(f"Votos: {result['votes']}")
    print(f"Tasa de detección: {result['tasa_deteccion']}")
    for message in result["transcript"]:
        marker = " [IA]" if message["is_ai"] else ""
        print(f"  R{message['round_number']} {message['alias']}{marker}: ", end="")
        print(message["text"])
    print(f"Registrada: {session_id} en {database}")


def main(argv: list[str] | None = None) -> int:
    """Jugar y registrar una partida; salir con 0 solo si fue válida."""
    options = parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # consola de Windows (cp1252)
    config = HarnessConfig(
        bots=options.bots,
        rounds=options.rounds,
        round_timeout=options.timeout,
        response_delay=options.delay,
        vote_mode=options.votes,
        seed=options.seed,
        prompt_version=options.prompt_version,
    )
    stub = _connect(options.engine) if options.engine else ScriptedEngineStub()
    result, session_id = run_and_save(config, stub, options.db)
    _report(result, session_id, options.db)
    return 0 if result["valid_game"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
