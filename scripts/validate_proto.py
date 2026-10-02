"""Validar la sintaxis del contrato congelado de Protocol Buffers."""

from pathlib import Path
from tempfile import TemporaryDirectory

from grpc_tools import protoc


def main() -> int:
    """Compilar un descriptor temporal y devolver el resultado del compilador."""
    source = Path(__file__).resolve().parents[1] / "proto" / "impostor.proto"
    with TemporaryDirectory() as temporary:
        output = Path(temporary) / "impostor.pb"
        status = protoc.main(
            [
                "grpc_tools.protoc",
                f"-I{source.parent}",
                f"--descriptor_set_out={output}",
                str(source),
            ]
        )
    if status == 0:
        print(
            "El contrato .proto v1 compila (CONGELADO: no modificar sin ADR aprobado)."
        )
    return status


if __name__ == "__main__":
    raise SystemExit(main())
