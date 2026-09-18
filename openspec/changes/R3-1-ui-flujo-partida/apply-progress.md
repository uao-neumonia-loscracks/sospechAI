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

---

# Slice PR 2 — Contenido + FakeSospechAI (tareas 2.1–2.6, 2.9, 3.1–3.6)

**Cambio**: `R3-1-ui-flujo-partida`
**Slice**: PR 2 — contenido contra `api.py` con `FakeSospechAI` + contenido de pantallas y polling
**Modo**: Strict TDD (`strict_tdd: true` + runner `uv run pytest`)
**Fecha**: 2026-09-17
**Rama**: `feature/r3-1-ui-flujo-partida-p2` (base `develop` @ 07ecadc, regla A3: ramas feature apuntan a develop)
**Merge previo**: PR 1 mergeado a `main` vía #41; `develop` sincronizado con `main` (invariante main ⊆ develop en 07ecadc).

## Tareas completadas

- [x] 2.1 RED — Contador y límite (D5, UIF-04/11) — 2026-09-17
- [x] 2.2 GREEN — Crear `src/ui/words.py` (D5) — 2026-09-17
- [x] 2.3 RED — Formas y máquina del fake (UIF-07) — 2026-09-17
- [x] 2.4 GREEN — `src/ui/sources/__init__.py` y `src/ui/sources/fake.py` (D3) — 2026-09-17
- [x] 2.5 GREEN — Crear `src/ui/api.py` (D3, UIF-07/10) — 2026-09-17
- [x] 2.6 RED — Bloqueo por límite combinado (UIF-04/05) — 2026-09-17
- [x] 2.9 REFACTOR — Conteo sin duplicados (UIF-11, AGENTS) — 2026-09-17
- [x] 3.1 Pantalla de consentimiento (D2, UIF-02) — 2026-09-17
- [x] 3.2 Lobby (D2, UIF-03) — 2026-09-17
- [x] 3.3 Sala de chat (D2, UIF-04/05) — 2026-09-17
- [x] 3.4 Votación vacía y placeholder REVELACION (D2, UIF-08) — 2026-09-17
- [x] 3.5 Polling no bloqueante con frecuencias por estado (D4, UIF-06) — 2026-09-17
- [x] 3.6 IA anónima e idéntica (D6, UIF-03) — 2026-09-17

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 2.1 | `tests/test_ui_words.py` | Unit | N/A (new) | ✅ escrito → falla (módulo ausente) | ✅ 5 passed | ✅ vacío/acentos/espacios/límites | ✅ — |
| 2.2 | `tests/test_ui_words.py` | Unit | N/A (new) | ✅ (2.1) | ✅ 5 passed | ✅ Idem 2.1 | ✅ `count_words`/`within_limit` separados |
| 2.3 | `tests/test_ui_api.py` | Unit | N/A (new) | ✅ escrito → falla (fake ausente) | ✅ (en 2.4) | ✅ claves exactas + orden máquina + alias | ✅ máquina congelada |
| 2.4 | `tests/test_ui_api.py` | Unit | N/A (new) | ✅ (2.3) | ✅ (en 2.6) | ✅ catálogo §8 | ✅ store compartido por módulo |
| 2.5 | `tests/test_ui_api.py` | Unit | N/A (new) | ➖ estructural (smoke facade) | ✅ 41 passed total UI | ✅ frozen dataclasses | ✅ `_source()` selector |
| 2.6 | `tests/test_ui_api.py` | Unit | N/A (new) | ✅ escrito → `too_many_words` no lanzado | ✅ 41 passed | ✅ 400 + mensaje ausente | ✅ ApiError por `code` |
| 2.9 | — | Refactor | 🔧 suite completa | ➖ | ✅ 217 passed | ✅ grep `count_words` único | ✅ 0 duplicados |
| 3.1–3.6 | `tests/test_ui_router.py` + `AppTest` | Smoke/Unit | suite | ➖ (reutilizan RED previos) | ✅ AppTest: 0 excepciones | ✅ happy path fake manual | ✅ — |

### Test Summary

- **Total tests UI**: 41 (words 5 + api 27 + router 9) — suite completa **217 passed**
- **Layers used**: Unit, Smoke, Refactor (grep único)

## Work Unit Evidence

| Evidence | Required value |
|---|---|
| Focused test command | `uv run pytest tests/test_ui_words.py tests/test_ui_api.py tests/test_ui_router.py` → **41 passed in 1.28s** |
| Full suite | `uv run pytest` → **217 passed in 4.14s**, cero warnings (`filterwarnings=error`) |
| Runtime harness | `AppTest.from_file("src/ui/app.py").run()` → **0 exceptions, título "Consentimiento informado"**; happy path manual vía facade fake: create→join→start→RONDA (IA Jugador 3 último) → mensaje dentro del límite visible → sobre el límite `ApiError(too_many_words, 400)` y NO en conversación |
| ruff / black | `uv run ruff check src/ui tests/test_ui_*.py` → All checks passed; `uv run black --check .` → **43 files would be left unchanged** (exit 0 — `.gitignore` ya UTF-8 tras fix de R1 en develop/main) |
| git status | `M` tasks.md + screens/app.py/context.py; `??` api.py, words.py, sources/, test_ui_api.py, test_ui_words.py — **sin cambios en `src/orchestrator/` ni `src/impostor_engine/`** |
| Rollback | Work Unit 2: eliminar `src/ui/api.py`, `src/ui/sources/`, `src/ui/words.py`, `tests/test_ui_words.py`, `tests/test_ui_api.py` y revertir screens/app.py a los stubs de PR 1; PR 1 intacto. |

## Deviations from Design

1. **Selector de anfitrión por `alias == "Jugador 1"`** en `lobby.py` (task 3.2): `RoomIdentity` del contrato no expone un flag `is_host`, así que el botón «Iniciar partida» se muestra al `Jugador 1`. Válido para el fake (alias por orden de inserción); si el orquestador HTTP futuro asigna aliases distinto, el PR 3 debe revisar esto.
2. **`app.py` importa `from src.ui.screens import ScreenContext, render_*` dentro de `main()`** (imports locales) — heredado del bootstrap `sys.path` del PR 1 (evita E402). El resto coincide con el diseño (D2, D3, D4, D5, D6).

## Issues Found

1. **Ninguno bloqueante.** El ejecutor del slice fue cancelado por el usuario a mitad de la persistencia; el código ya estaba completo y verde. La verificación del orquestador (suite, ruff, black, AppTest, happy path fake) confirmó el estado antes de persistir. Nota: `st.fragment(run_every=...)` y `st.rerun(scope="app")` soportados en streamlit 1.64.0 (verificado en PR 1).

## Remaining Tasks

- [ ] 2.7, 2.8 (PR 3: `HttpSospechAI` + integración `-m integration`) — **no incluidas en este slice**
- [ ] 4.1–4.4 (fase 4: verificación final de criterios de éxito, orquestador)

## Workload / PR Boundary

- Mode: stacked PR slice (`stacked-to-develop`, regla A3)
- Current work unit: PR 2 — contenido + FakeSospechAI
- Boundary: empieza con `words.py`/`api.py` RED y termina con pantallas completas + polling `st.fragment` + happy path fake en verde

---

# Slice PR 3 — HttpSospechAI (tareas 2.7, 2.8)

**Cambio**: `R3-1-ui-flujo-partida`
**Slice**: PR 3 — `HttpSospechAI` con stdlib `urllib` + integración contra un `ThreadingHTTPServer` local
**Modo**: Strict TDD (`strict_tdd: true` + runner `uv run pytest`)
**Fecha**: 2026-09-18
**Rama**: `feature/r3-1-ui-flujo-partida-p3` (base `develop` @ a081bb9; PR 1 mergeado #41, PR 2 mergeado #46; regla A3 `stacked-to-develop`)
**Merge previo**: PR 1 y PR 2 ya integrados en `develop`; merge protocol = leer los ficheros actuales, sin operaciones git.

## Tareas completadas

- [x] 2.7 RED — Integración `HttpSospechAI` contra servidor local (UIF-06/07) — 2026-09-18
- [x] 2.8 GREEN — Crear `src/ui/sources/http.py` (D3) — 2026-09-18

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 2.7 | `tests/test_ui_api.py` (+ `ThreadingHTTPServer` local) | Integration | ✅ 18/18 (`uv run pytest tests/test_ui_api.py`) | ✅ escrito → `ModuleNotFoundError: No module named 'src.ui.sources.http'` (1 error de colección) | ✅ (en 2.8) | ✅ 8 casos cable: 201 identidad ×2, 204 acciones + 200 estado, cabecera AUSENTE en create/join y PRESENTE en el resto, `too_many_words`, `session_expired`, `wrong_state`, error sin JSON → `malformed_request` | ✅ constantes del servidor de prueba extraídas |
| 2.8 | `tests/test_ui_api.py` (mismos tests) | Integration | ✅ 18/18 (baseline, seguridad) | ✅ (RED cubierto por 2.7) | ✅ `9 passed, 18 deselected in 6.48s` (`-m integration`) | ✅ Idem 2.7 + selector `_source()` con `SOSPECHAI_UI_SOURCE=http` + `SOSPECHAI_ORCHESTRATOR_URL` | ✅ black reformateó `http.py`/`test_ui_api.py`; re-run verde (27 passed) |

### Test Summary

- **Total tests escritos en este slice**: 9 (todos `@pytest.mark.integration`, AAA)
- **Total tests pasando**: 9 (+ 18 unit previos de `test_ui_api.py`; 27 en el fichero)
- **Layers usados**: Integration (9) sobre `ThreadingHTTPServer` stdlib en `127.0.0.1:<puerto efímero>`
- **Approval tests** (refactoring): None — no hubo tarea de refactor en el slice
- **Pure functions created**: 6 métodos del facade del Protocol de `HttpSospechAI` + `_request`/`_raise_error`/`_code`

## Work Unit Evidence

| Evidence | Required value |
|---|---|
| Focused test command and exact result | `uv run pytest tests/test_ui_api.py -m integration` → **9 passed, 18 deselected in 6.48s** |
| Runtime harness command/scenario and exact result | **N/A** — el servidor HTTP real del orquestador (R2) no existe aún en `main` (tasks.md, Work Unit 3); la verificación de cable (cabecera `X-Session-Token`, códigos 201/200/204, errores parseados por `code`) queda cubierta por el `ThreadingHTTPServer` local de la prueba de integración. |
| Rollback boundary | Work Unit 3 (tasks.md): eliminar `src/ui/sources/http.py` y revertir el wiring `http` en `src/ui/api.py` (y la exportación en `src/ui/sources/__init__.py`); PR 1/PR 2 intactos. |

### Verificación adicional

- `uv run pytest tests/test_ui_api.py` → **27 passed in 6.55s** (unit + integration).
- `uv run pytest` (suite completa) → **226 passed in 10.88s**, cero warnings con `filterwarnings = ["error"]`.
- `uv run ruff check src/ui tests/test_ui_*.py` → **All checks passed!**
- `uv run black --check .` → **44 files would be left unchanged** (exit 0; black aplicado solo a los ficheros tocados).
- `git status --short` → `M` `tasks.md`, `src/ui/api.py`, `src/ui/sources/__init__.py`, `tests/test_ui_api.py`; `??` `src/ui/sources/http.py`. **Sin cambios en `src/orchestrator/` ni `src/impostor_engine/`.**

## Ficheros

| File | Action | What Was Done |
|------|--------|---------------|
| `src/ui/sources/http.py` | Created | `HttpSospechAI` con `urllib`: 6 endpoints del contrato, `X-Session-Token`, `room_code` en mayúsculas, 2xx/error → `ApiError` por `code`, red → `ApiError("internal", 500)` sin detalle del proveedor |
| `src/ui/sources/__init__.py` | Modified | Exporta `HttpSospechAI` junto a `FakeSospechAI` |
| `src/ui/api.py` | Modified | `_source()` cablea `SOSPECHAI_UI_SOURCE=http` → `HttpSospechAI(environ["SOSPECHAI_ORCHESTRATOR_URL"])`; swap localizado (UIF-07), pantallas intactas |
| `tests/test_ui_api.py` | Modified | +9 pruebas `@pytest.mark.integration` (AAA) contra `ThreadingHTTPServer` local (harness `_ContractHandler` en el propio fichero) |
| `openspec/changes/R3-1-ui-flujo-partida/tasks.md` | Modified | 2.7 y 2.8 marcadas `[x]` (líneas de guardia ya estaban actualizadas, no tocadas) |
| `openspec/changes/R3-1-ui-flujo-partida/apply-progress.md` | Modified | Sección "Slice PR 3" añadida; PR 1 y PR 2 intactos |

## Deviations from Design

None — la implementación coincide con el diseño (D3): `HttpSospechAI` con stdlib `urllib`, las 6 operaciones del contrato, cabecera `X-Session-Token` salvo crear/unirse, `room_code` normalizado a mayúsculas, respuestas no-2xx por `code` (con cuerpo JSON malformado → `malformed_request`, 400) y error de red → `ApiError("internal", 500, ...)` sin detalle del proveedor. El swap queda localizado en `api._source()`; las pantallas no cambian (UIF-07).

## Issues Found

1. **Selector de anfitrión `alias == "Jugador 1"` frente al contrato HTTP (heredado del PR 2, sin arreglar en este slice).** `RoomIdentity` (contrato §§6.1-6.2) no transporta un flag explícito de anfitrión: la cabecera solo declara que «la condición de anfitrión se verifica contra el token en cada petición; el cliente no declara su rol» (§3). El `lobby.py` infiere el botón de `start`/`open_voting` (este último llega en R3-2) por `identity.alias == "Jugador 1"`. Bajo el servidor HTTP real esto se cumple (el creador siempre es «Jugador 1», orden de inserción, contrato §4), por lo que el comportamiento actual es correcto; sin embargo, es un acoplamiento implícito: si el orquestador (R2) cambiara el orden de asignación de alias o R3-2 necesitara detectar anfitrión fuera del creador (reconexión de no-anfitrión), la UI induciría a error. Recomendación para seguimiento R3-2/R2: flag aditivo `is_host` en las respuestas 201 (camino aditivo del contrato §13) o tratar `forbidden_host_action` (403) como autoridad. **No se modifican pantallas en este slice.**
2. **`@pytest.mark.integration` reutiliza el marcador ya registrado en `pyproject.toml`** (`markers = ["integration: ..."]`); su descripción menciona gRPC, pero el marcador es único en el proyecto y cubre la integración local sin servicios externos. No se añadió `pytest.ini` (configuración ya suficiente).

## Remaining Tasks

- [ ] 4.1–4.4 (fase 4: verificación final de criterios de éxito) → verificación del orquestador al cierre.

## Workload / PR Boundary

- Mode: stacked PR slice (`stacked-to-develop`, regla A3)
- Current work unit: PR 3 — «HttpSospechAI»
- Boundary: empieza con los tests de integración RED y termina con `http.py` cableado en `_source()` + integración en verde
- Estimated review budget impact: `src/ui/sources/http.py` (~120 líneas) + `tests/test_ui_api.py` (+~330 líneas de harness y pruebas) + 2 modificaciones mínimas; PR 1/PR 2 fuera del diff de este slice

---

# Fase 4 — Verificación final de criterios de éxito (orquestador, 2026-09-18)

**Modo**: verificación del orquestador sobre el cambio completo (PR 1 + PR 2 + PR 3 aplicados en cadena stacked-to-develop).

## Evidencia

| Criterio | Comando | Resultado |
|---|---|---|
| 4.1 Suite completa, cero warnings (UIF-11) | `uv run pytest` | **226 passed in 10.60s**, cero warnings (`filterwarnings = ["error"]`) |
| 4.2 Estilo limpio (UIF-11) | `uv run ruff check src/ui tests/test_ui_*.py` | **All checks passed!** |
| 4.2 Estilo limpio (UIF-11) | `uv run black --check .` | **44 files would be left unchanged** (exit 0) |
| 4.3 Harness manual del piloto | `AppTest.from_file("src/ui/app.py").run()` | **0 excepciones, título "Consentimiento informado"** |
| 4.3 Happy path del fake | create → join → start (RONDA, IA última) → msg bajo límite visible → msg sobre límite `ApiError(too_many_words, 400)` no entra | **Correcto** (ejecutado en PR 2) |
| 4.4 Aditivo (UIF-10) | `git status --short` | Solo `src/ui/` nuevos + `tests/` nuevos + `openspec/` + `src/ui/api.py`/`sources/__init__.py` modificados; **cero cambios en `src/orchestrator/` ni `src/impostor_engine/`** |
| Spot check subagente PR 3 | `uv run pytest tests/test_ui_api.py -m integration` | **9 passed, 18 deselected** (re-ejecutado por el orquestador) |

## Estado del cambio

- **26/26 tareas completas** (1.1–1.7 PR 1, 2.1–2.6 + 2.9 + 3.1–3.6 PR 2, 2.7–2.8 PR 3, 4.1–4.4 Fase 4).
- Entregas: PR #41 (esqueleto, a `main` antes de A3) · PR #46 (contenido + fake, a `develop`) · PR 3 (HttpSospechAI, a `develop`, pendiente de abrir).
- Pendiente de entrega: abrir el PR 3 y mergear `develop → main` (regla A3) para completar el flujo.
- Issue documentado para R3-2/R2: selector de anfitrión por `alias == "Jugador 1"` (flag `is_host` aditivo o autoridad de `forbidden_host_action`).
