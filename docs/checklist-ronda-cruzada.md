# Checklist — Ronda cruzada (entrega módulo 3)

_Fecha: sábado 19 de septiembre de 2026 · Autor: R1 (Juan Melendez)_

Uso: cada rol revisa el trabajo del otro rol contra estas verificaciones.
Columna `OK` / `FALLA` / `N/A`. Toda `FALLA` bloquea la entrega hasta resolverla.

## 1. Integración de servicios (lo que otros roles verificarán de R1)

| # | Verificación | Cómo | OK / FALLA / N/A |
|---|---|---|---|
| 1.1 | El engine gRPC arranca con `uv run python -m src.impostor_engine.serve --port 50051` | Ejecutar, `HealthCheck` → `healthy: true` | |
| 1.2 | El orquestador arranca con `--model-id` y `--round-timeout` | Ejecutar, `GET /health` 200 | |
| 1.3 | La UI arranca con fuente HTTP apuntando al orquestador | `SOSPECHAI_UI_SOURCE=http`, `SOSPECHAI_ORCHESTRATOR_URL=http://127.0.0.1:8080`, abrir puerto 8501 | |
| 1.4 | Una partida completa llega a REVELACION con engine real | Partida piloto de 2 rondas (evidencia: `docs/verificaciones/2026-09-18-piloto-a16.md`) | |
| 1.5 | El cliente HTTP de la UI tolera el turno síncrono de la IA (timeout 30 s) | Revisar `src/ui/sources/http.py` (`_timeout = 30.0`) | |
| 1.6 | Los botones de la UI usan callbacks `on_click` (sin doble-click) | Revisar `src/ui/screens/*.py` | |
| 1.7 | La pantalla de consentimiento va antes del lobby (regla dura) | Recorrido en la UI | |
| 1.8 | La revelación es un estado de la máquina, no una bandera (regla dura) | Revisar `src/orchestrator/game.py` | |

## 2. Arquitectura y reglas duras (revisión de código)

| # | Verificación | Cómo | OK / FALLA / N/A |
|---|---|---|---|
| 2.1 | `src/orchestrator/` NO importa a `src/impostor_engine/` | `git grep` de imports cruzados | |
| 2.2 | `src/impostor_engine/` NO conoce rondas/votos/jugadores/partidas | `git grep` de esas palabras en el engine | |
| 2.3 | `src/common/` es código puro sin gRPC/HTTP/estado | Revisar `src/common/` | |
| 2.4 | `src/ui/` NO habla gRPC directo con el engine | Revisar imports de `src/ui/` | |
| 2.5 | `proto/impostor.proto` no fue modificado sin ADR | `git log` del archivo | |
| 2.6 | Normalización de texto en UNA sola función | Revisar normalización (R1-8) | |
| 2.7 | Cero credenciales en el repo; HF_TOKEN solo por env | `git grep "hf_"` / revisar `.env` ausente | |
| 2.8 | Funciones ≤ 40 líneas salvo justificación escrita | Ruff + revisión | |

## 3. Calidad y pruebas

| # | Verificación | Cómo | OK / FALLA / N/A |
|---|---|---|---|
| 3.1 | Suite completa verde | `uv run pytest -q` (hoy: 410 passed) | |
| 3.2 | Cero warnings (filterwarnings=error) | En la corrida de 3.1 | |
| 3.3 | Ruff y black limpios | `uv run ruff check .`, `uv run black --check .` | |
| 3.4 | Sin `.ipynb`, Colab, Kaggle, `notebooks/` | `git ls-files` | |
| 3.5 | Entorno exclusivo uv, Python 3.13, sin pip directo | `pyproject.toml` + `uv.lock` | |
| 3.6 | Las pruebas no llaman a la API real de HF | Revisar tests; monkeypatch de `InferenceClient` | |
| 3.7 | Docstrings y type hints en toda función pública | Ruff + muestra | |
| 3.8 | AAA explícito en pruebas | Muestra de tests | |

## 4. Ramas y entregables

| # | Verificación | Cómo | OK / FALLA / N/A |
|---|---|---|---|
| 4.1 | `main` ⊆ `develop` (invariante) | `git rev-list origin/main --not origin/develop` = vacío | |
| 4.2 | Toda rama feature apunta a `develop`, nunca a `main` | Revisar PRs abiertos | |
| 4.3 | Ramas mergeadas borradas en remoto | `git branch -r` sin ramas muertas | |
| 4.4 | Commits con prefijo y ticket: `feat:/fix:/test:/chore: (A#)` | `git log --oneline` | |
| 4.5 | Commits pequeños, uno por cambio lógico | Revisar PR recientes | |
| 4.6 | Toda tarjeta M3 de R1 cerrada con evidencia | Tablero GitHub (#31..#) | |
| 4.7 | ADR-006 (costos) y ADR-007 (droplet) con estado claro | `docs/adr/` | |
| 4.8 | Model Card actualizado | `docs/model_card.md` (R1 + R4) | |

## 5. Coordinación y ritos del curso

| # | Verificación | Cómo | OK / FALLA / N/A |
|---|---|---|---|
| 5.1 | PRs revisados por el rol asignado en la ronda cruzada | Comentarios en PR / conversación | |
| 5.2 | Métricas y experimentos documentados (A13/A28) | MLflow + `docs/verificaciones/` | |
| 5.3 | Evidencia del piloto A16 en repo | `docs/verificaciones/2026-09-18-piloto-a16.md` | |
| 5.4 | Encuesta/retro del equipo actualizada | Grupo / documento compartido | |
| 5.5 | README y video de demostración (R4) | R4 responde; no bloquea a R1 | |

## Firmas

| Rol | Revisó | Fecha | Veredicto final |
|---|---|---|---|
| R1 | | | |
| R2 | | | |
| R3 | | | |
| R4 | | | |

---

## Notas de uso

- Si una verificación aplica a otro rol (p. ej. 5.5), registrar `N/A` en el
  checklist del revisor y marcarla en la columna de responsable.
- Las `FALLA` no se "arreglan durante la ronda": se listan, se asignan y se
  re-verifican antes del cierre del sábado.
- Este checklist es de R1; cada rol puede tener el suyo. La ronda cruzada debe
  cubrir al menos las filas 1, 2 y 3 por cada par de roles.