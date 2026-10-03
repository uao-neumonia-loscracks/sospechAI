# HANDOFF — SospechAI (Módulo 4)

Handoff generado el 2026-10-03 para que un agente fresco retome el proyecto sin
memoria previa. Todo lo que sigue fue verificado contra el repo y los servicios
el día de generación. Los secretos están redactados: se indica DÓNDE viven, no
su valor.

---

## 1. Qué es el proyecto

**SospechAI**: juego de conversación multijugador para medir la detección humana
de texto generado por IA. Humanos y una IA impostora responden las mismas
preguntas de ronda (≤ 15 palabras), debaten, votan al sospechoso, y la partida
termina con revelación obligatoria de quién era la IA, puntajes y tasa de
detección del grupo.

**Contexto académico (crítico)**: trabajo de grado universitario (UAO), Grupo 2.
Hay un runbook que define los pasos pendientes del Módulo 4:

```
C:\Users\juanc\Desktop\DDPIA\SospechAI\modulo4-solo-paso-a-paso.md
```

El repositorio del proyecto está en:

```
C:\Users\juanc\Desktop\DDPIA\SospechAI\impostor-engine\
```

Hoy es 2026-10-03. El Módulo 4 se sustenta el 03/10: los pasos 19–22 del runbook
ya están COMPLETOS (ver sección 9). Solo quedan los opcionales del paso 23.

## 2. Repos y remotes

```bash
# GitLab (fuente: aquí vive el CI/CD y la issue tracker del Módulo 4)
origin  https://gitlab.com/jcmt-group/sospechAI.git
# GitHub (espejo; se empuja igual)
github  https://github.com/uao-neumonia-loscracks/sospechAI.git
```

- Proyecto GitLab numérico: **86933863** (usado en la API REST).
- Rama actual recomendada: `develop`. `main` solo recibe merges desde `develop`
  con MR revisado (regla dura del repo, ver AGENTS.md).
- HEAD de develop: `92f9e19` (merge de `feature/cierre-a22-a30`).

## 3. Estructura del repo

```
impostor-engine/
├── proto/impostor.proto        # contrato gRPC v1, CONGELADO (no tocar sin ADR)
├── src/
│   ├── common/                 # código puro compartido, sin estado
│   ├── orchestrator/           # servidor HTTP del juego (reglas, rondas, votos)
│   │   └── server.py           #   NO puede importar impostor_engine
│   ├── impostor_engine/        # servicio gRPC que llama a la Inference API
│   │   ├── serve.py            #   no conoce rondas/votos/jugadores
│   │   └── inference_client.py #   cliente HTTP resiliente (ADR-008)
│   └── ui/                     # frontend Streamlit
├── tests/                      # 426 tests, nunca llaman HF real
├── scripts/
│   ├── deploy.sh               # deploy + rollback automático (lo corre el CI)
│   ├── smoke.sh                # smoke test pos-deploy (no toca HF)
│   └── validate_proto.py       # checa .proto congelado vs stubs
├── docs/
│   ├── arquitectura.html       # diagrama interactivo de infra
│   ├── arquitectura-secuencia.html
│   ├── CONTRATO_UI_ORQUESTADOR.md   # contrato UI↔orquestador v1.1 congelado
│   ├── ACUERDOS_R2.md          # tabla de parámetros acordada (R2)
│   ├── model_card.md
│   ├── despliegue.md           # TODA la doc de despliegue (fuente primaria)
│   ├── adr/                    # ADR-001, 003, 006, 007, 008
│   └── verificaciones/2026-09-18-piloto-a16.md
├── deploy/droplet-setup.sh     # NO commiteado todavía (untracked)
├── docker-compose.yml          # compose local (3 servicios + mlflow en M3)
├── docker-compose.prod.yml     # compose de producción (4 servicios)
├── .gitlab-ci.yml              # pipeline: test/build/deploy
├── Makefile                    # objetivos dev (ver sección 4)
├── .env.example                # plantilla: HF_TOKEN, SOSPECHAI_MODEL_ID
└── AGENTS.md                   # REGLAS DURAS DEL PROYECTO (leer antes de tocar código)
```

**Reglas duras (AGENTS.md, resumen)**: proto congelado; `orchestrator` NUNCA
importa `impostor_engine`; `engine` no conoce el juego; normalización de texto
en UNA sola función; prohibido .ipynb/Colab/notebooks; solo uv (Python 3.13),
nunca pip directo; cero warnings (pytest con `filterwarnings=["error"]`);
docstrings y type hints; commits convencionales `feat:|fix:|test:|chore:` con
ticket `(A##)`; feature → develop → main; borrar rama feature tras merge.

## 4. Comandos de desarrollo (en `impostor-engine\`)

Requisitos: uv + Python 3.13. Windows + PowerShell en esta máquina.

```bash
# Calidad (equivalente exacto al job "test" del CI)
uv run ruff check src tests scripts
uv run black --check src tests scripts
uv run pytest -q                 # 426 tests en verde, sin warnings
uv run python scripts/validate_proto.py

# Formatear reescribiendo
uv run black .
# Solo timeout fuera de Docker
uv run python -m src.orchestrator.server
```

Desde el Makefile: `make up`, `make down`, `make ps`, `make logs`,
`make logs-ui`, `make logs-orchestrator`, `make pull-engine`, `make test`,
`make test-quick`, `make lint`, `make format`, `make format-check`,
`make proto-check`, `make clean`.

### Levantar local (3 opciones)
- **A — Docker Compose**: `docker compose up --build -d` con `.env` copiado de
  `.env.example`; UI en http://localhost:8501. (Camino documentado, pero el
  piloto real se jugó con la opción B.)
- **B — 3 terminales con uv (la comprobada)**:
  1. `uv run python -m src.impostor_engine.serve --port 50051`
  2. `$env:SOSPECHAI_ENGINE_ADDR="127.0.0.1:50051"; $env:SOSPECHAI_MODEL_ID="Qwen/Qwen2.5-7B-Instruct:featherless-ai"; uv run python -m src.orchestrator.server`
  3. `$env:SOSPECHAI_UI_SOURCE="http"; $env:SOSPECHAI_ORCHESTRATOR_URL="http://127.0.0.1:8080"; uv run streamlit run src/ui/app.py`

Opciones del orquestador: `--rounds` (2), `--max-words` (15),
`--round-timeout` (20 s; el piloto usó 600), `--events-db`.

**Gotcha conocido**: sin `SOSPECHAI_MODEL_ID` el orquestador arranca pero la
partida falla en el primer turno del impostor (valida el model_id). Definir
siempre.

## 5. Arquitectura y servicios

| Servicio | Rol | Puerto |
|---|---|---|
| `impostor-engine` | gRPC; genera respuestas vía Inference API de HF (router → Featherless AI) | 50051 (red interna) |
| `impostor-orchestrator` | HTTP; reglas, rondas, votos, revelación; SQLite + MLflow | 8080 |
| `impostor-mlflow` | tracking: 1 run por partida terminada | 5000 |
| `impostor-ui` | Streamlit; habla solo con el orquestador | 8501 (host) |

El modelo corre SIEMPRE en el proveedor externo (HF router), nunca en local ni
en el Droplet (ADR-001, ADR-007). Parámetros del experimento (registrados en
MLflow): `Qwen/Qwen2.5-7B-Instruct:featherless-ai`, temperature 0.9, top_p 0.9,
system_prompt_version v2, max_words 15, n_players 3, n_rondas 2.

ADRs existentes (docs/adr/): ADR-001 (inferencia por API), ADR-003 (ventanas y
cierres ante fallos), ADR-006 (costo por token — **retira el dato del runbook**:
costo real < USD 0,000059/llamada, no $0,0016), ADR-007 (tamaño del Droplet),
ADR-008 (cliente HTTP resiliente — cierra A22; número 008 porque 007 ya existía).

## 6. Producción (Droplet DigitalOcean)

- App: **http://198.211.107.154** (Streamlit en puerto 80 del host).
- Droplet Ubuntu 22.04, 4 GB, IP `198.211.107.154`, usuario `deploy`.
- Deploy automático desde `main` vía GitLab CI (runner self-hosted con tag
  `droplet`, el mismo Droplet). Pipeline: test → build (solo main) → deploy
  (solo main) con smoke test y rollback automático.
- Los archivos de despliegue viven en `/opt/sospechai/`; el tag bueno se
  recuerda en `/opt/sospechai/LAST_GOOD`.
- Imágenes en el Container Registry de GitLab, tag = `CI_COMMIT_SHORT_SHA`.

### Acceso y operación (ver docs/despliegue.md para el detalle completo)

```bash
# SSH (desde esta máquina Windows funciona con estos flags)
ssh -o ConnectTimeout=10 -o BatchMode=yes deploy@198.211.107.154

# Túnel MLflow (la UI de MLflow escucha solo en 127.0.0.1 del Droplet)
ssh -L 5000:localhost:5000 deploy@198.211.107.154
# luego en el navegador local: http://127.0.0.1:5000

# Dentro del Droplet
docker compose -p sospechai -f /opt/sospechai/docker-compose.prod.yml ps
docker compose -p sospechai -f /opt/sospechai/docker-compose.prod.yml logs -f ui
```

### Consultar MLflow por API (verificado, gotchas incluidos)

```bash
# Listar experimentos — OJO: requiere max_results, GET
curl -s "http://127.0.0.1:5000/api/2.0/mlflow/experiments/search?max_results=100" | python -m json.tool

# Listar runs — OJO: SOLO POST con body JSON (GET da 405)
curl -s -X POST http://127.0.0.1:5000/api/2.0/mlflow/runs/search \
  -H "Content-Type: application/json" \
  -d '{"experiment_ids":["0"],"max_results":1000}' | python -m json.tool
```

Estado medido el 2026-10-02: **7 runs FINISHED** en el experimento default,
tags `modulo=M3`, `ambiente=local`, backend `hf-router`, proveedor
`featherless-ai`. Esos 7 son las "partidas reales" citadas en el reporte final.
El guion de sustentación M3 mencionaba 3 runs (MLflow LOCAL de entonces) — no
confundir con los 7 del Droplet.

Gotcha: si se invoca desde PowerShell con ssh/curl, el flag `-d` con JSON y
llaves puede romperse; camino probado: escribir el script a un .py temporal y
pipear `Get-Content -Raw <archivo> | ssh deploy@198.211.107.154 "python3 -"`.

## 7. GitLab CI/CD (fuente: .gitlab-ci.yml)

- Stages: `test` (todas las ramas) → `build` (solo main) → `deploy` (solo main).
- test corre en contenedor `ghcr.io/astral-sh/uv:python3.13-bookworm-slim`:
  `uv sync --locked && ruff check && black --check && pytest -q`.
- build: 3 imágenes en paralelo con buildx `--push --provenance=false
  --sbom=false` (sin eso, BuildKit produce "blob unknown to registry").
- deploy: `bash scripts/deploy.sh` — pull del tag nuevo, `up -d`, `smoke.sh`;
  si falla, vuelve a `LAST_GOOD` (rollback real probado: pipeline #2908204896,
  revert después en `fix/revertir-prueba-rollback`).

## 8. Issue tracker / GitLab API (MCP GitLab está CAÍDO)

El MCP de GitLab devuelve Unauthorized. Usar REST con PAT:

- PAT en: `C:\Users\juanc\.config\opencode\.secrets\gitlab-token` (REDACTADO:
  no copiar el valor al handoff ni a commits).
- Proyecto: `86933863`. Base: `https://gitlab.com/api/v4/projects/86933863`.

```powershell
$token = (Get-Content -Raw "C:\Users\juanc\.config\opencode\.secrets\gitlab-token").Trim()
# Cerrar un issue (state_event=close SOLO vía PUT; JSON a bytes UTF-8, Windows-1252 rompe acentos)
$utf8 = New-Object System.Text.UTF8Encoding($false)
Invoke-RestMethod -Method Put -Uri "https://gitlab.com/api/v4/projects/86933863/issues/7" `
  -Headers @{ "PRIVATE-TOKEN" = $token } -ContentType "application/json; charset=utf-8" `
  -Body $utf8.GetBytes('{"state_event":"close"}')
# Crear/mergear MR: POST .../merge_requests, PUT .../merge_requests/{iid}/merge
```

Board "Modulo 4": id 11656041 — columnas Backlog / En progreso / Hecho (labels
`modulo-4`, `Backlog`, `En progreso`, `Hecho`). GitLab Free: UN solo assignee →
compañeros via `Participantes: @natalia_a.hernandez @juano2024` en descripción.

Estado de issues: cerrados #1,2,3,4,5,6,8,9,12 (label Hecho). Abiertos:
**#7 (A25 — barrido de configuraciones, En progreso)**, **#10 (A28 — Backlog)**,
**#11 (A29 — Backlog)**.

## 9. Estado del Módulo 4 (qué está hecho, qué falta)

### Completado (verificado)
- PASO 19 — tablero GitLab: issues habilitados, labels, 12 issues A19–A30, board.
- PASO 20 — `docs/despliegue.md` + badge de pipeline y sección Despliegue en
  README; mergeado a develop y main; deploy verificado.
- PASO 21 — `docs/adr/ADR-008-a22-cliente-http.md` (A22 reescrito: timeouts,
  deadline, máx 1 reintento solo pre-envío, sin backoff artificial, tabla de
  errores HTTP auth/credits/rejected/unavailable, 8 tests referenciados).
  Cierra issue #4.
- PASO 22 — `reports/reporte_final.md` (pregunta de investigación, qué se
  construyó, decisiones con ADRs, estado honesto: 7 partidas en MLflow,
  barrido A25 NO hecho, limitaciones, ética, trabajo futuro). Cierra issue #12.
- CI/CD verde en main, app viva (http://198.211.107.154, health OK).

### Pendiente (opcional, PASO 23 del runbook — solo si hay tiempo)
- Sesión corta en la IP pública (A25 reducido) con 2 jugadores humanos.
- Actualizar Archify (docs/diagramas) con Droplet + Runner + Registry + firewall.
- Decisión: si el reporte debe incluir el modo determinista (decisión no tomada).

### Pendientes operativos heredados (no bloquean entrega)
- `deploy/droplet-setup.sh` sigue untracked: decidir si se versiona o se borra.
- Decidir persistencia del PAT de GitLab (hoy: archivo en ~/.config/opencode/.secrets).
- Rotar `HF_TOKEN` (un leak detectado en GitHub en el pasado).

### Untracked que NO se commitean
`Makefile`, `data/`, `deploy/`, `openspec/changes/archive/2026-09-18-fix-ui-votacion-polling/`.

## 10. Secretos y datos sensibles

- `HF_TOKEN`: SOLO por variable de entorno / `.env` (ignorado por git). En
  producción llega al compose por la variable del CI del proyecto GitLab.
- NUNCA versionar: `.env`, `.gguf`, `.h5`, `.pkl`, tokens, PATs.
- `.env` local existe en el repo y NO debe entrar al git. Verificar siempre
  `git status` antes de `git add -A`.

## 11. Skills sugeridas para el agente entrante

- `handoff` — lee este mismo documento como arranque del contexto.
- `sdd-*` — solo si se abre un cambio nuevo con spec/design/tasks (el proyecto
  usa openspec/ en el repo).
- `rdd-defect-workflow` — si aparece un defecto de revisión en el CI.
- `webapp-testing` — para probar la UI desplegada (Streamlit) con Playwright.
- `diagnosing-bugs` — ante cualquier fallo del pipeline o de la app en el Droplet.
- `websearch`/`context7` — para consultar docs de Streamlit/MLflow/uv si se toca
  esa parte.
- `improve-codebase-architecture` (opcional) — si se revisa acoplamiento.

## 12. Fuentes primarias (NO duplicar su contenido en el handoff)

- `impostor-engine\README.md` — arranque, juego, validación, despliegue.
- `impostor-engine\docs\despliegue.md` — doc COMPLETA de despliegue/operación.
- `impostor-engine\AGENTS.md` — reglas duras del proyecto.
- `impostor-engine\docs\adr\ADR-008-a22-cliente-http.md` — cierre de A22.
- `impostor-engine\reports\reporte_final.md` — cierre de A30.
- `C:\Users\juanc\Desktop\DDPIA\SospechAI\modulo4-solo-paso-a-paso.md` — runbook
  del Módulo 4 (pasos 21–22 líneas ~1180–1236; paso 23 al final).
- Engram (memoria persistente, proyecto `impostor-engine`): buscar
  `modulo4/cierre-adr-reporte`, `gitlab-modulo-4-board` para el historial.