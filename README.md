# SospechAI

Sistema de conversación multijugador para medir la detección humana de texto generado por IA. Esta rama contiene el avance propuesto de R2 para Natalia.

## Arquitectura actual

La interfaz habla con el orquestador. R2 solicita respuestas por gRPC a `impostor-engine`; R1 realiza desde ese servicio la llamada HTTP a Hugging Face. El modelo se ejecuta en el proveedor externo, no en el Droplet.

| Componente | Estado en esta rama |
| --- | --- |
| Orquestador R2 | Dominio, ventanas, cliente gRPC, manejo de fallos y resultados SQLite de práctica. Servidor multijugador pendiente. |
| Contrato con R1 | Borrador ampliado y stubs generados; revisión conjunta pendiente. |
| Engine HTTP R1 | Implementación y benchmark a cargo de R1; no incluidos. |
| UI, MLflow e infraestructura | Integración del equipo pendiente. |

## Empezar

Requiere [uv](https://docs.astral.sh/uv/getting-started/installation/). Desde la raíz:

```bash
uv sync --locked
uv run python -m src.orchestrator.demo
```

La demo de consola usa frases simuladas y guarda resultados de práctica en SQLite. No consume una API ni constituye evidencia experimental con personas.

## Validar

```bash
uv run ruff check src tests scripts
uv run black --check src tests scripts
uv run pytest -q --cov=src --cov-report=term-missing
uv run python scripts/validate_proto.py
```

Hay pruebas unitarias y dos pruebas de transporte gRPC local. Los warnings hacen fallar pytest. A5, A6, A8 y A15 permanecen abiertas hasta completar acuerdos e integración.

## Documentación

- [Guía para comenzar y sustentar R2](docs/INICIO_R2.md)
- [Revisión del cambio a API](docs/REVISION_CAMBIO_API.md)
- [Acuerdos pendientes](docs/ACUERDOS_R2.md)
- [ADR-001: inferencia por API](docs/adr/ADR-001-cambio-a-inference-api.md)
- [ADR-003: parámetros provisionales](docs/adr/ADR-003-parametros-de-juego.md)
- [Bitácora y handoff](docs/bitacora/2026-09-09.md)
- [Verificación de Hugging Face](docs/verificaciones/2026-09-09-inference-api.md)
- [Licencia](LICENSE)
