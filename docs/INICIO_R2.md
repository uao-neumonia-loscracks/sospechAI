# Inicio de R2 con inferencia por API

El controlador conserva las reglas. R2 solicita texto a R1 por gRPC y `impostor-engine` realiza la llamada HTTP. `HF_TOKEN` pertenece al servicio de R1.

## Preparar el computador

Cuando la rama esté publicada, desde un clon del repositorio:

```bash
git fetch origin
git switch R2-Natalia-Hernandez
uv sync --locked
uv run python -m src.orchestrator.demo
```

Si todavía no has clonado el proyecto, usa primero:

```bash
git clone https://github.com/uao-neumonia-loscracks/sospechAI.git
cd sospechAI
```

Necesitas [uv](https://docs.astral.sh/uv/getting-started/installation/). El entorno usa Python 3.13 y `uv.lock` fija las dependencias.

La demo solicita dos respuestas y un voto. Es una práctica con frases simuladas. Desactiva explícitamente la ventana temporal para poder leer y aprender. Guarda simulaciones en `data/practice/partidas_demo.sqlite3`.

```bash
uv run python -m src.orchestrator.demo --auto
```

## Leer y explicar el código

| Archivo | Responsabilidad |
| --- | --- |
| `src/orchestrator/game.py` | Rondas, normalización compartida, votos, puntajes, ventana y revelación. |
| `src/orchestrator/engine_client.py` | RPC con deadline, validación del stream y cierre ante fallos. |
| `src/orchestrator/storage.py` | Resultado final de práctica en SQLite. |
| `proto/impostor.proto` | Mensajes con R1 y configuración aditiva de API. |
| `tests/test_game.py` | Reglas y persistencia. |
| `tests/test_api_boundary.py` | Errores remotos y dos pruebas con transporte gRPC local. |

Primero ejecuta la demo y lee `submit_message()`, `cast_vote()` e `interrupt()`. Luego sigue `apply_ai_turn()`: valida el turno antes de llamar, limita el presupuesto al tiempo restante y entrega la respuesta completa al mismo validador usado por los humanos.

## Conectar con R1

Cuando R1 implemente su servicio, se crea el cliente con un canal a su dirección interna:

```python
import grpc
from proto import impostor_pb2_grpc as rpc
from src.orchestrator.engine_client import EngineClient

with grpc.insecure_channel(
    "impostor-engine:50051", options=[("grpc.enable_retries", 0)]
) as channel:
    client = EngineClient(rpc.ImpostorEngineStub(channel))
    # Usar apply_ai_turn(game, alias_ia, client, request) con una partida activa.
```

El destino se acuerda con R1. La petición debe contener la pregunta, historia, versión del prompt, temperatura, top_p, límite de palabras, `engine_backend="hf-router"` y el modelo/proveedor confirmado. No hay un modelo definitivo preseleccionado en este cliente.

El presupuesto de 8 s y la ventana de 20 s son provisionales hasta A2. El cliente acumula fragmentos antes de publicar y exige un fragmento final vacío con `is_final=True`, seguido del cierre del RPC. No realiza reintentos de aplicación ni cambia a un modelo local.

## Verificar

```bash
uv sync --locked
uv run ruff check src tests scripts
uv run black --check src tests scripts
uv run pytest -q --cov=src --cov-report=term-missing
uv run pytest -q -m "not integration"
uv run pytest -q -m integration
uv run python scripts/validate_proto.py
```

Las pruebas de transporte abren un puerto efímero en loopback, sin consumir Hugging Face. La cobertura anterior incluye la consola, que se verifica también con ejecuciones de demostración.

Los stubs están versionados. Para regenerarlos desde la raíz:

```bash
uv run python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. --pyi_out=. proto/impostor.proto
uv run python -c "from proto import impostor_pb2, impostor_pb2_grpc; print('ok')"
```

## Qué falta

A6 requiere revisar el contrato con R1 y diseñar el de UI-orquestador. A8 requiere servidor, sesiones, concurrencia y persistencia activa; SQLite solo guarda resultados de práctica en este incremento. R3 integrará MLflow y R4 los servicios.

La ventana se comprueba con cada acción o consulta. El servidor futuro debe llamar `check_expiration()` mediante un temporizador aunque nadie consulte. Los plazos de discusión/votación y desconexiones siguen pendientes. Las tareas completas no se dan por cerradas.
