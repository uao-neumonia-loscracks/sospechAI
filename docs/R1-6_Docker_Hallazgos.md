# R1-6 · Docker Compose (A12) — Hallazgos

_Fecha: miércoles 16 de septiembre de 2026 · Autor: R1 (Juan Melendez)_

## Criterio de éxito

> Los tres contenedores healthy y la UI accesible en el navegador.

**NO VALIDABLE HOY** — bloqueado por dependencias de R2/R3, no por el Dockerfile.

## Estado real del entorno

- Docker Desktop está instalado pero el daemon no arranca: el hypervisor
  está desactivado en la máquina por un problema con las máquinas virtuales
  (decisión del usuario: NO reiniciar por esto).
- El CLI local no tiene el plugin `docker compose`.
- El orquestador NO tiene servidor: `src/orchestrator/` solo contiene
  `game.py`, `engine_client.py`, `demo.py` (consola) y `storage.py`. El
  servidor HTTP del contrato UI-orquestador (A9) lo implementa R2, aún no
  existe.
- La UI NO existe: no hay `src/ui/` (R3 no entregó nada todavía).

## Lo que se dejó listo (R1)

| Archivo | Rol |
|---|---|
| `Dockerfile` | Engine real, Python 3.13 + uv, lock congelado, `HF_TOKEN` por env a runtime, entrypoint `python -m src.impostor_engine.serve` |
| `docker-compose.yml` | Los tres servicios declarados; `impostor-engine` operativo, `orchestrator`/`ui` comentados con `PENDIENTE R2/R3`; red interna `sospechai-net`; volumen `sqlite-data`; **ningún puerto gRPC expuesto al host** |
| `.env.example` | Plantilla sin valores; `.env` ya está en `.gitignore` |
| `.dockerignore` | Excluye `.env`, `.venv`, datos, tests, docs y scripts del contexto de build |

## Hallazgo adicional de tooling (arreglado, cosmético)

- `.gitignore` estaba guardado en latin-1 en un comentario ("Caché local",
  byte `E9`), lo que rompía `black` en TODO el repo con
  `UnicodeDecodeError: 'utf-8'`. Se normalizó a UTF-8 (mismo contenido,
  solo codificación) y el toolchain vuelve a correr: ruff + black OK.
- El script `scripts/e2e_real_engine.py` quedó formateado por black y pasa
  `ruff check` + `black --check`.

## Plan B (demo del 19, tal como prevé el plan de cierre)

La partida se muestra con tres terminales:
1. Engine: `uv run python -m src.impostor_engine.serve --port 50051`
2. Orquestador: conector E2E (`scripts/e2e_real_engine.py`) o la demo
   trabajada con R2 cuando tenga servidor.
3. UI: cuando R3 entregue; mientras tanto, consola.

## Pendientes

- [ ] R2: entregar el servidor HTTP del orquestador (contrato A9) para
      poder descomentar su servicio en el compose.
- [ ] R3: entregar `src/ui` y su Dockerfile para descomentar `impostor-ui`.
- [ ] R1: validar `docker compose up --build -d` en una máquina con
      Docker operativo (Módulo 4, donde el Dockerfile se afina igual).