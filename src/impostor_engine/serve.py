"""Punto de entrada del engine: `python -m src.impostor_engine.serve [--port 50051]`."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor

import grpc
from dotenv import load_dotenv

from proto import impostor_pb2_grpc as rpc
from src.impostor_engine.inference_client import InferenceClient
from src.impostor_engine.servicer import ImpostorEngineServicer

DEFAULT_PORT = 50051


def build_server(*, port: int = DEFAULT_PORT) -> grpc.Server:
    """Construir y devolver un servidor gRPC listo para escuchar."""
    client = InferenceClient()
    servicer = ImpostorEngineServicer(client, round_timeout=8.0)
    server = grpc.server(ThreadPoolExecutor(max_workers=4))
    rpc.add_ImpostorEngineServicer_to_server(servicer, server)
    server.add_insecure_port(f"[::]:{port}")
    return server


def main() -> int:
    """Arrancar el engine y bloquear hasta una interrupción."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    load_dotenv()
    server = build_server(port=args.port)
    server.start()
    print(f"engine escuchando en [::]:{args.port}")
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("apagando engine...")
        server.stop(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
