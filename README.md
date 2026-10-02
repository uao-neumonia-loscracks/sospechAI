# SospechAI

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![uv](https://img.shields.io/badge/uv-ambiente_100%25-7B3FF2?logo=uv)](https://docs.astral.sh/uv/)
[![Tests](https://img.shields.io/badge/tests-426_passing-2ea44f)](https://github.com/uao-neumonia-loscracks/sospechAI)
[![Ruff](https://img.shields.io/badge/ruff-clean-D7FF64?logo=ruff)](https://github.com/astral-sh/ruff)
[![Black](https://img.shields.io/badge/black-formatted-000000?logo=black)](https://black.readthedocs.io/)
[![Docker](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![MLflow](https://img.shields.io/badge/MLflow-tracking-0194E2?logo=mlflow&logoColor=white)](https://mlflow.org/)
[![Licencia](https://img.shields.io/badge/licencia-MIT-yellow)](#licencia)

Juego de conversación multijugador para medir la detección humana de texto generado por inteligencia artificial. En cada partida, humanos y una IA impostora responden las mismas preguntas de ronda con un límite de palabras, debaten, votan a quién consideran el impostor y la partida termina con la revelación de la identidad real de la IA: puntajes y tasa de detección del grupo.

El modelo no se ejecuta en local: la generación de texto sale por HTTP hacia la Inference API de Hugging Face (router a un proveedor externo, hoy Featherless AI) desde el servicio `impostor-engine` (ver ADR-001).

## Arquitectura

[![Diagrama de infraestructura](docs/arquitectura.html)](docs/arquitectura.html) · [![Secuencia de una respuesta del impostor](docs/arquitectura-secuencia.html)](docs/arquitectura-secuencia.html)

Diagramas interactivos generados con la skill [Archify](https://skills.sh/tt-a1i/archify): el de infraestructura muestra servicios, contrato gRPC, Inference API, SQLite y MLflow; el de secuencia muestra la ruta de una respuesta del impostor hasta el chunk final con trailing metadata. Las fuentes JSON viven en `docs/diagramas/` y se regeneran según `docs/diagramas/README.md`.

| Componente | Rol | Puerto |
| --- | --- | --- |
| `impostor-engine` | Servicio gRPC que genera las respuestas del impostor llamando a la Inference API de Hugging Face. No conoce rondas, votos, jugadores ni partidas. | 50051 (solo red interna) |
| `impostor-orchestrator` | Servidor HTTP del contrato UI-orquestador: reglas del juego, rondas, votos, revelación y cierre. Persistencia opcional de eventos en SQLite y tracking MLflow. | 8080 |
| `impostor-mlflow` | Servidor de tracking MLflow: cada partida terminada registra un run con params, métricas, artefactos y tags. | 5000 |
| `impostor-ui` | Frontend Streamlit. Habla únicamente con el orquestador. | 8501 (único puerto expuesto al host junto a MLflow) |

Reglas de acoplamiento (ver `AGENTS.md`):

- La UI nunca habla gRPC directo con el engine; solo se comunica con el orquestador por HTTP+JSON.
- El orquestador nunca importa el engine; la única comunicación es gRPC a través del contrato.
- El contrato gRPC vive en `proto/impostor.proto` (versión v1, congelada: ningún cambio sin ADR aprobado).
- El contrato entre la UI y el orquestador es `docs/CONTRATO_UI_ORQUESTADOR.md` (congelado en versión 1.1).
- El modelo corre en un proveedor externo (router de Hugging Face), nunca en el Droplet ni en local.

## Empezar

Requisitos: [uv](https://docs.astral.sh/uv/getting-started/installation/) y Python 3.13 (`.python-version`). El entorno es exclusivamente uv; no se usa pip directo.

### Opción A — Docker Compose (recomendada)

1. Copia la plantilla de variables y completa tu token de Hugging Face y el modelo del router:

```bash
cp .env.example .env
```

2. Levanta los contenedores:

```bash
docker compose up --build -d
```

3. Abre http://localhost:8501 (la UI es el único servicio expuesto al host).

`docker-compose.yml` levanta los tres servicios: `impostor-engine` (gRPC 50051, solo red interna), `impostor-orchestrator` (HTTP 8080, solo red interna, alcanzado por la UI por el nombre de servicio interno) y `impostor-ui` (Streamlit 8501). El gRPC del engine nunca sale al host. El compose exige `HF_TOKEN` y `SOSPECHAI_MODEL_ID` en `.env` (ver `.env.example`), y valida que el engine esté healthy antes de arrancar el orquestador. La validación integral del compose en una máquina con Docker operativo corresponde al Módulo 4 (ver `docs/R1-6_Docker_Hallazgos.md`); la vía comprobada para jugar una partida completa hoy es la Opción B, que es la que se usó en el piloto del 2026-09-18.

### Opción B — tres terminales con uv (comprobada)

Necesitas `HF_TOKEN` (exportado o en `.env`, que el engine carga al arrancar) y `SOSPECHAI_MODEL_ID`.

Terminal 1 — engine gRPC:

```bash
uv run python -m src.impostor_engine.serve --port 50051
```

Terminal 2 — orquestador HTTP:

```bash
export SOSPECHAI_ENGINE_ADDR=127.0.0.1:50051
export SOSPECHAI_MODEL_ID="Qwen/Qwen2.5-7B-Instruct:featherless-ai"
uv run python -m src.orchestrator.server
```

En PowerShell de Windows, antes del comando: `$env:SOSPECHAI_ENGINE_ADDR="127.0.0.1:50051"` y `$env:SOSPECHAI_MODEL_ID="Qwen/Qwen2.5-7B-Instruct:featherless-ai"`.

Opciones útiles del orquestador: `--rounds` (2 por defecto), `--max-words` (15), `--round-timeout` (20 s por defecto; el piloto del 2026-09-18 usó 600 s para jugar sin apuro) y `--events-db` (o la variable `SOSPECHAI_EVENTS_DB`) para anexar los eventos de ciclo de vida a una base SQLite. El tracking MLflow es opcional vía `MLFLOW_TRACKING_URI`.

Advertencia: sin `SOSPECHAI_MODEL_ID` el orquestador arranca (el valor por defecto es vacío), pero la partida falla al pedir la respuesta de la IA: el cliente gRPC valida el `model_id` antes de llamar al engine (`src/orchestrator/engine_client.py`) y el turno del impostor termina en error interno. Define siempre esta variable.

Terminal 3 — UI Streamlit:

```bash
export SOSPECHAI_UI_SOURCE=http
export SOSPECHAI_ORCHESTRATOR_URL=http://127.0.0.1:8080
uv run streamlit run src/ui/app.py
```

Abre http://localhost:8501. Sin `SOSPECHAI_UI_SOURCE=http`, la UI usa la fuente `fake` (en memoria, sin orquestador): sirve para probar pantallas, no para una partida real.

## Cómo se juega

1. **Consentimiento**: la UI presenta primero la pantalla de consentimiento (uno de los participantes puede ser un modelo de lenguaje y la conversación se registra con fines de investigación). Sin aceptar no se entra; esta pantalla va antes del lobby (regla del proyecto).
2. **Lobby**: el anfitrión crea la sala y obtiene un código corto; las demás personas se unen con ese código. Los alias los asigna el servidor ("Jugador N"). Para iniciar se necesitan al menos 2 humanos.
3. **Ronda**: al iniciar, el servidor registra a la IA (siempre como el último "Jugador N") y publica la pregunta de la ronda. Cada humano responde con un límite de 15 palabras por defecto (un mensaje por jugador y ronda); cuando todos respondieron, el orquestador pide la respuesta del impostor al engine por gRPC, con un presupuesto de a lo sumo 8 segundos dentro de la ventana de la ronda (20 s por defecto).
4. **Discusión**: los jugadores debaten antes de votar; el anfitrión abre la votación o la ventana vence y la fase avanza sola.
5. **Votación**: cada humano vota al sospechoso o se abstiene (sentinel reservado `"__abstain__"`). No se permite votarse a uno mismo; la IA no vota.
6. **Revelación**: se muestra quién era el impostor, los votos, los puntajes y la tasa de detección (`result` embebido en la instantánea). Es un estado terminal de la máquina, no una pantalla configurable.

Hay 2 rondas por defecto (configurable con `--rounds`). Un ejemplo de partida completa se documenta en `docs/verificaciones/2026-09-18-piloto-a16.md`.

## Validación y calidad

```bash
uv run ruff check src tests scripts
uv run black --check src tests scripts
uv run pytest -q
uv run python scripts/validate_proto.py
```

Estado verificado el 19 de septiembre de 2026: 426 pruebas, todas en verde y sin warnings (pytest corre con `filterwarnings` en modo error); ruff y black sin hallazgos; el `.proto` compila. Las pruebas nunca llaman a la API real de Hugging Face.

El tracking con MLflow registra un run por partida terminada cuando `MLFLOW_TRACKING_URI` está definida (en el compose del M3, `http://mlflow:5000`): params (modelo, proveedor, temperatura, max_words, jugadores, rondas), métricas (tasa de detección, latencia p95, tokens, costo estimado), artefactos (transcript anónimo y matriz de votos) y tags de trazabilidad (licencia, equipo, ambiente, módulo).

## Documentación

- Contrato UI-orquestador (fuente única de la interfaz UI-orquestador): `docs/CONTRATO_UI_ORQUESTADOR.md`
- ADR-001 — inferencia por API: `docs/adr/ADR-001-cambio-a-inference-api.md`
- ADR-003 — ventanas y cierre ante fallos de inferencia: `docs/adr/ADR-003-parametros-de-juego.md`
- ADR-006 — costo de la API por token: `docs/adr/ADR-006-costos.md`
- ADR-007 — tamaño del Droplet sin modelo local: `docs/adr/ADR-007-tamano-del-droplet.md`
- Model card del impostor: `docs/model_card.md`
- Hallazgos de Docker Compose (R1-6): `docs/R1-6_Docker_Hallazgos.md`
- Verificaciones (ejemplo: piloto A16 del 2026-09-18): `docs/verificaciones/`
- Checklist de la ronda cruzada: `docs/checklist-ronda-cruzada.md`
- Acuerdos provisionales de R2 (tabla de parámetros): `docs/ACUERDOS_R2.md`

## Licencia

Ver [LICENSE](LICENSE).