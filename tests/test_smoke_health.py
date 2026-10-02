"""Smoke health: prueba AAA con dobles, sin servidor gRPC ni red."""

from __future__ import annotations

import grpc
import pytest

from proto import impostor_pb2 as pb
from src.impostor_engine import smoke_health


class FakeHealthStub:
    """Doble del stub generado: responde o lanza un error gRPC."""

    def __init__(
        self, response: pb.HealthResponse | None, *, error: bool = False
    ) -> None:
        """Fijar la respuesta o el modo de error antes de la llamada."""
        self._response = response
        self._error = error

    def HealthCheck(
        self, request: pb.HealthRequest, *, timeout: float
    ) -> pb.HealthResponse:
        """Reproducir la firma del stub real (requisito, error o respuesta)."""
        if self._error:
            raise grpc.RpcError()
        return self._response


class FakeGrpc:
    """Doble que reemplaza canal y stub; `with` para imitar insecure_channel."""

    def __init__(
        self, response: pb.HealthResponse | None = None, *, error: bool = False
    ) -> None:
        """Dejar el stub listo para la llamada de main()."""
        self.stub = FakeHealthStub(response, error=error)

    def __enter__(self) -> FakeGrpc:
        return self

    def __exit__(self, *args: object) -> None:
        return None


@pytest.mark.parametrize(
    ("response", "error", "expected"),
    [
        (pb.HealthResponse(healthy=True), False, 0),
        (pb.HealthResponse(healthy=False), False, 1),
        (None, True, 1),
    ],
    ids=["healthy", "not_healthy", "grpc_error"],
)
def test_main_exit_code_matches_health(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    response: pb.HealthResponse | None,
    error: bool,
    expected: int,
) -> None:
    """Arrange: doble del canal que entrega la respuesta o el error."""
    fake = FakeGrpc(response, error=error)
    monkeypatch.setattr(smoke_health.grpc, "insecure_channel", lambda addr: fake)
    monkeypatch.setattr(
        smoke_health.rpc, "ImpostorEngineStub", lambda channel: channel.stub
    )

    # Act
    code = smoke_health.main()

    # Assert
    output = capsys.readouterr().out
    assert code == expected
    assert output.startswith("SMOKE engine:")
