"""Smoke health: verificar por gRPC que el engine responde sano.

No llama a la Inference API: solo HealthCheck contra el contrato congelado.
"""

from __future__ import annotations

import os

import grpc

from proto import impostor_pb2 as pb
from proto import impostor_pb2_grpc as rpc

DEFAULT_ADDR = "localhost:50051"
TIMEOUT_SECONDS = 10.0
ADDR_ENV = "SMOKE_ENGINE_ADDR"


def health_ok(
    stub: rpc.ImpostorEngineStub, *, timeout: float = TIMEOUT_SECONDS
) -> bool:
    """Devolver True solo si HealthCheck responde con healthy=True."""
    try:
        response = stub.HealthCheck(pb.HealthRequest(), timeout=timeout)
        return bool(response.healthy)
    except grpc.RpcError:
        return False


def main() -> int:
    """Llamar HealthCheck al engine y salir con 0 si está sano; 1 en cualquier otro caso."""
    address = os.environ.get(ADDR_ENV, DEFAULT_ADDR)
    try:
        with grpc.insecure_channel(address) as channel:
            stub = rpc.ImpostorEngineStub(channel)
            healthy = health_ok(stub)
    except grpc.RpcError:
        healthy = False
    print(f"SMOKE engine: addr={address} healthy={healthy}")
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
