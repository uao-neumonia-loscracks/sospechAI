# Apply Progress: R3-1 — Flujo de partida en la UI

**Cambio**: `R3-1-ui-flujo-partida`
**Slice**: PR 1 — Esqueleto navegable (Phase 1, tareas 1.1–1.7)
**Modo**: Strict TDD (`strict_tdd: true` + runner `uv run pytest`)
**Fecha**: 2026-09-16
**Rama**: `feature/r3-1-ui-flujo-partida-p1`
**Merge previo**: no existía `apply-progress.md` (primer batch); merge protocol N/A.

## Tareas completadas

- [x] 1.1 Dependencia `streamlit` vía `uv` (D8, UIF-12) — 2026-09-16
- [x] 1.2 Crear `src/ui/__init__.py` — 2026-09-16
- [x] 1.3 RED — Router: transición y frecuencia (UIF-02/06/09) — 2026-09-16
- [x] 1.4 GREEN — Crear `src/ui/router.py` — 2026-09-16
- [x] 1.5 RED — Smoke de arranque (UIF-01/09) — 2026-09-16
- [x] 1.6 GREEN — Cuatro pantallas placeholder (D2, UIF-08/09) — 2026-09-16
- [x] 1.7 GREEN — Crear `src/ui/app.py` (D1, UIF-02/09) — 2026-09-16

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | — (config) | Config | N/A (new) | ➖ N/A tarea de configuración, sin comportamiento testeable | ✅ `uv sync` OK + probe: streamlit 1.64.0 con `fragment.run_every` y `rerun.scope` | ➖ Single | ➖ None needed |
| 1.2 | `tests/test_ui_router.py` (smoke) | Structural | N/A (new) | ➖ N/A marcador de paquete | ✅ Importado vía `src.ui.app` y screens | ➖ Single | ➖ None needed |
| 1.3 | `tests/test_ui_router.py` | Unit | N/A (new) | ✅ Escrito → `ModuleNotFoundError: No module named 'src.ui.router'` (13 fallos de colección) | ✅ 13 passed (en 1.4) | ✅ 6 estados + 2 bandas de frecuencia | ✅ Constantes extraídas |
| 1.4 | `tests/test_ui_router.py` | Unit | N/A (new) | ✅ (RED cubierto por 1.3) | ✅ `14 passed` total | ✅ Idem 1.3 | ✅ `GAME_STATES`, `GAME_POLL_SECONDS`, `IDLE_POLL_SECONDS` |
| 1.5 | `tests/test_ui_router.py` | Smoke | N/A (new) | ✅ Escrito → `ModuleNotFoundError: No module named 'src.ui.app'` (1 failed, 13 passed) | ✅ 14 passed (en 1.7) | ➖ Single (un escenario de arranque) | ✅ Formato black aplicado |
| 1.6 | `tests/test_ui_router.py` | Smoke | N/A (new) | ✅ (RED cubierto por 1.5) | ✅ 14 passed | ➖ Single | ✅ Docstrings y paquete exportador |
| 1.7 | `tests/test_ui_router.py` | Smoke | N/A (new) | ✅ (RED cubierto por 1.5) | ✅ 14 passed | ➖ Single | ✅ black reformateó `ScreenContext(...)` a una línea |

### Test Summary

- **Total tests written**: 14 (13 de router + 1 smoke)
- **Total tests passing**: 14
- **Layers used**: Unit (13), Smoke (1), Config (0)
- **Approval tests** (refactoring): None — no refactoring tasks
- **Pure functions created**: 2 (`resolve_screen`, `poll_interval_seconds`)

## Work Unit Evidence

| Evidence | Required value |
|---|---|
| Focused test command and exact result | `uv run pytest tests/test_ui_router.py` → **14 passed in 0.64s** |
| Runtime harness command/scenario and exact result | `uv run streamlit run src/ui/app.py --server.headless true --server.port 8601` → servidor Uvicorn arrancó sin traceback. Ejecución real del script vía `streamlit.testing.v1.AppTest.from_file("src/ui/app.py").run()` → **0 excepciones, títulos == ["Consentimiento informado"]** (pantalla inicial = consentimiento, UIF-01/02). |
| Rollback boundary | `git revert` del commit que añade `streamlit` a `pyproject.toml`/`uv.lock` + `uv sync`; eliminar `src/ui/` (9 ficheros) y `tests/test_ui_router.py`. No toca `src/orchestrator/` ni `src/impostor_engine/` (aditivo, UIF-10). |

### Verificación adicional

- `uv run pytest` (suite completa) → **187 passed in 3.58s**, cero warnings con `filterwarnings = ["error"]`.
- `uv run ruff check src/ui tests/test_ui_router.py` → **All checks passed!**
- `uv run black --check` → ver Issues (bloqueo pre-existente del repo); verificación equivalente sobre copia en temp → **10 files would be left unchanged**.
- `git status --short` → ` M pyproject.toml`, ` M uv.lock`, `?? openspec/` (pre-existente), `?? src/ui/`, `?? tests/test_ui_router.py`. **Sin cambios en `src/orchestrator/` ni `src/impostor_engine/`.**

## Ficheros

| File | Action | What Was Done |
|------|--------|---------------|
| `pyproject.toml` | Modified | `streamlit>=1.64.0` en `dependencies` (vía `uv add`) |
| `uv.lock` | Modified | Regenerado por `uv add streamlit` (`streamlit==1.64.0`) |
| `src/ui/__init__.py` | Created | Marca el paquete `src/ui/` con docstring |
| `src/ui/router.py` | Created | Lógica pura: `Screen(StrEnum)`, `resolve_screen`, `poll_interval_seconds` (sin `st`) |
| `src/ui/screens/__init__.py` | Created | Exporta `ScreenContext` y `render` de cada pantalla |
| `src/ui/screens/context.py` | Created | `ScreenContext` (placeholder: `room_identity`/`snapshot`) |
| `src/ui/screens/consent.py` | Created | Placeholder `render(ctx)` del consentimiento |
| `src/ui/screens/lobby.py` | Created | Placeholder `render(ctx)` del lobby |
| `src/ui/screens/chat.py` | Created | Placeholder `render(ctx)` de la sala de chat |
| `src/ui/screens/voting.py` | Created | Placeholder navegable de votación (sin controles ni resultados) |
| `src/ui/app.py` | Created | Entry point: bootstrap de `sys.path`, `main()`, router por `session_state`, guard `__main__` |
| `tests/test_ui_router.py` | Created | 14 pruebas AAA de transición, frecuencia y smoke de arranque |

## Deviations from Design

1. **Fichero extra `src/ui/screens/context.py`** (no listado en `design.md` File Changes: 17 ficheros nuevos en vez de 16). Motivo: el tipo del argumento `ctx` de `render(ctx)` no quedó localizado en el diseño; un módulo compartido mínimo mantiene desacopladas pantallas y raíz de composición (AGENTS: bajo acoplamiento). `room_identity`/`snapshot` son `object | None` hasta que `api.py` defina `RoomIdentity`/`StateSnapshot` (fase 2).
2. **`src/ui/app.py` añade la raíz del proyecto a `sys.path`** en un bootstrap a nivel de módulo, e importa `src.ui.*` de forma local dentro de `main()`. Motivo: `streamlit run` solo inserta la carpeta del script (`src/ui`) en `sys.path` (verificado en `streamlit/web/bootstrap.py:_fix_sys_path` y `runtime/scriptrunner/script_runner.py:modified_sys_path`); la raíz del repo no está en el `sys.path` del console script, por lo que `from src.ui...` fallaría bajo `uv run streamlit run src/ui/app.py`. Los imports locales evitan E402/noqa. Aparte de esto, la implementación coincide con el diseño (D1, D2, D8).

## Issues Found

1. **`uv run black --check` no puede ejecutarse en el repo (pre-existente, no de este cambio).** black 26.5.1 lee `.gitignore` como UTF-8, pero `.gitignore` (5043 bytes) contiene un byte latin-1 `0xE9` en el offset 4993 → `UnicodeDecodeError` en `get_gitignore`. Reproduce igual sobre un fichero no tocado (`tests/test_game.py`). Verificación equivalente: copia de los ficheros nuevos a un directorio temporal sin `.gitignore` + `uv run black --check --target-version py313` → **10 files would be left unchanged**. Recomendación: ticket aparte para normalizar la codificación de `.gitignore`; NO se modificó (fuera de alcance).
2. **Alcance de «navegable end-to-end» en PR 1.** Los placeholders no incluyen controles (el botón de aceptación es la tarea 3.1 y la fuente de estado es la fase 2), por lo que el click-through completo no es demostrable en este slice. El esqueleto queda verificado por: pantalla inicial `CONSENT` (AppTest), gate de consentimiento y transiciones del router (14 pruebas) y ausencia de `st.navigation`/`pages/`.
3. **Log de bare-mode en el harness `AppTest`.** Aparece `missing ScriptRunContext!` por stderr de Streamlit al ejecutar fuera de pytest; es logging interno, no un warning de Python, y no se produce en la suite (el smoke pasa con `filterwarnings=["error"]`).

## Remaining Tasks

- [ ] 2.1–2.9 (fase 2: `words.py`, `api.py`, `sources/`, fake y pruebas)
- [ ] 3.1–3.6 (fase 3: contenido de pantallas y polling)
- [ ] 4.1–4.4 (fase 4: verificación de criterios de éxito)

## Workload / PR Boundary

- Mode: stacked PR slice (`stacked-to-main`)
- Current work unit: PR 1 — esqueleto navegable
- Boundary: empieza con `uv add streamlit` y termina con `src/ui/app.py` placeholder + smoke en verde
- Estimated review budget impact: 9 ficheros nuevos en `src/ui/`, 1 test nuevo, `pyproject.toml` + `uv.lock`; `uv.lock` excluido del presupuesto de riesgo por ser generado
