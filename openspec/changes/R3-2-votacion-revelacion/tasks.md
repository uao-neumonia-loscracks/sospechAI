# Tasks: R3-2 — Votación real y pantalla de revelación en la UI

> Guard-lines (defining what this change IS):
> 1. **PR único a `develop`**: este cambio se entrega como UN solo PR apuntando a `develop`
>    (nunca a `main`; prohibido por AGENTS). NO es una cadena de PRs; las fases son slices de
>    REVISIÓN dentro del mismo PR, con commits por unidad lógica (prefijo feat:/fix:/test:/chore:
>    y cada commit referencia su ticket `(R3-2)`).
> 2. **No toca `src/orchestrator/`, `src/impostor_engine/` ni `src/ui/words.py`** — el diff del
>    PR lo verifica; `words.py` queda byte-idéntico (no habrá 4ª copia de `normalize_text`,
>    R1-8 es de Juan).
> 3. **Contrato `docs/CONTRATO_UI_ORQUESTADOR.md`**: una sola edición (apply, tarea 2.4) aditiva
>    a v1.1 (clave `prompt_version` §7.2 + fila en §15). Nada más del contrato se modifica.
> 4. **REVELACION es un estado de la máquina**: router con `Screen.REVELATION` dedicado; ninguna
>    ruta termina la partida sin pasar por la revelación.
> 5. **Presupuesto de revisión ~400 líneas, riesgo Medium** (estimación ≈420–470 líneas
>    autoradas). Grupos de trabajo (Work Units) abajo delimitan slices de revisión con su
>    estrategia y límites de rollback.
> 6. **strict_tdd: true** (openspec/config.yaml) — las fases RED→GREEN son obligatorias en los
>    pasos que lo marcan; no hay tarea que aplique código de producción sin su prueba roja primero.

## Estado

Nada de este cambio está aplicado todavía. Todas las casillas de tareas de fases 1 a 4 quedan sin
marcar (`- [ ]`). No existe `apply-progress.md` (lo genera la fase de apply del orchestrator).

## Fase 1 — Router terminal y dominio de votación (submit_vote)

Objetivo: `REVELACION` nunca cae en VOTING, y el voto empieza a existir de verdad (fake) y por
HTTP (cliente), sin pantallas nuevas aún.

| # | Tarea | Comando / Harness | Criterio de aceptación |
|---|-------|-------------------|------------------------|
| [x] 1.1 | RED: `tests/test_ui_router.py` — `REVELACION` resuelve a `Screen.REVELATION` (nuevo miembro); `VOTACION` → `VOTING`; escenario «no existe ruta terminal alternativa». | `uv run pytest tests/test_ui_router.py -k "revelaci"` | Fallan por `Screen.REVELATION` inexistente y por el mapeo actual `REVELACION→VOTING`. |
| [x] 1.2 | GREEN: `src/ui/router.py` — añade `Screen.REVELATION` al enum y mapea `REVELACION → REVELATION`. Frecuencias y firma intactas. | `uv run pytest tests/test_ui_router.py` | Casos en verde. |
| [x] 1.3 | RED: `tests/test_ui_api.py` — `submit_vote` contra fake: happy (204→ok y `votes_received` al re-poll), `self_vote` 400, `duplicate_vote` 409, `not_a_player` 403, `wrong_state` 409. Actualiza `RESULT_KEYS` con `prompt_version` (gatillo del test de revelación existente). | `uv run pytest tests/test_ui_api.py -k "submit or prompt_version"` | Fallan: `submit_vote` no existe; `RESULT_KEYS` falla por `prompt_version`. |
| [x] 1.4 | GREEN: `src/ui/api.py` (Protocol + facade `submit_vote`) y `src/ui/sources/fake.py` (validación §8 en orden, registro real en `_Room.votes`, `_complete_votes` preservado, REVELACION cuando todos los humanos votaron). Facade devuelve señal de éxito/`ApiError`. | `uv run pytest tests/test_ui_api.py`; `uv run pytest tests/test_ui_router.py` | Verde; regresiones de R3-1 en suite de api/router sin fallos. |
| [x] 1.5 | RED+VERIFY: `tests/test_ui_api.py` — cliente HTTP `submit_vote` funiona contra `ThreadingHTTPServer` local: 204 feliz, `self_vote` 400, `duplicate_vote` 409. | `uv run pytest tests/test_ui_api.py -k "http"` | Fallan sin `HttpSospechAI.submit_vote`. |
| [x] 1.6 | GREEN: `src/ui/sources/http.py` — `submit_vote` → `POST /rooms/{code}/votes` con `{"suspect": "Jugador N"}`; 204=éxito; errores por `code` (§8); sin nuevo código para `prompt_version` (passthrough). | `uv run pytest tests/test_ui_api.py -k "http"` | Integración HTTP local verde. |

## Fase 2 — prompt_version y contrato v1.1

Objetivo: el fake emite `prompt_version:"v2"`, el cliente tolera servidores v1.0, y el archivo
del contrato se edita UNA vez (aditivo).

| # | Tarea | Comando / Harness | Criterio de aceptación |
|---|-------|-------------------|------------------------|
| [x] 2.1 | RED: `tests/test_ui_api.py` — `result()` del fake contiene `prompt_version == "v2"`; `RESULT_KEYS` ya actualizado en 1.3. | `uv run pytest tests/test_ui_api.py -k "prompt_version"` | Falla: fake aún no emite `prompt_version`. |
| [x] 2.2 | GREEN: `src/ui/sources/fake.py` — `_result` emite `prompt_version: "v2"` (Y en el transcript, la revelación lo muestra sin cambio extra). | `uv run pytest tests/test_ui_api.py -k "prompt_version"` | Verde. |
| [x] 2.3 | Prueba de tolerancia: `tests/test_ui_api.py` — integración HTTP con `result()` SIN `prompt_version` (servidor v1.0) no falla y transporta `result` sin mutación. | `uv run pytest tests/test_ui_api.py -k "toleranc or v1_0"` | Verde sin tocar `http.py` (passthrough por `from_mapping`). |
| [x] 2.4 | Apply (edición única del contrato): `docs/CONTRATO_UI_ORQUESTADOR.md` → v1.1. En §7.2 añadir fila `prompt_version \| string \| null \| Versión del prompt del impostor; default "v2"`. En §15 añadir `1.1 \| 2026-09-18 \| Clave aditiva prompt_version en result() para transparencia del prompt del impostor (R3-2)`. | `git diff docs/CONTRATO_UI_ORQUESTADOR.md` | El diff es EXACTAMENTE esas 2 líneas (más la línea de versión del pie si la hubiera), nada más. |

## Fase 3 — Pantallas: votación real y revelación

Objetivo: la UI emite votos con controles reales y presenta la revelación terminal.

| # | Tarea | Comando / Harness | Criterio de aceptación |
|---|-------|-------------------|------------------------|
| [x] 3.1 | RED: `tests/test_ui_revelation.py` — helpers puros AAA: revelación válida (impostor, votos+`vote_counts` ordenados, acierto por `tasa_deteccion`, transcript con `is_ai`, `prompt_version`), partida interrumpida (`interruption_reason`, sin tasa inventada), claves ausentes (`.get()` no explota), `prompt_version` ausente→texto genérico. | `uv run pytest tests/test_ui_revelation.py` | Falla: `src/ui/revelation.py` no existe. |
| [x] 3.2 | GREEN: `src/ui/revelation.py` — helper puro (sin `streamlit`), 1 función por bloque, ≤40 líneas, docstring + type hints, `.get()` siempre. | `uv run pytest tests/test_ui_revelation.py`; `uv run ruff check src/ui/revelation.py`; `uv run black --check src/ui/revelation.py` | Verde + estilo limpio. |
| [x] 3.3 | Pantalla de votación real: `src/ui/screens/voting.py` — sospechosos `players`, alias propio deshabilitado, emisión vía `context.on_submit_vote`, controles desactivados tras 204 («voto registrado; esperando al resto»), `votes_received` desde la instantánea, notices de rechazo (§8) sin presentar el voto. Callback `on_submit_vote` en `src/ui/screens/context.py`. | `uv run pytest tests/test_ui_revelation.py` + suite de api/router (sin regresiones) | Pantalla humana correcta; sin contador local. |
| [x] 3.4 | Pantalla de revelación: `src/ui/screens/revelation.py` (render, ÚNICO lugar con `is_ai`) + export en `src/ui/screens/__init__.py`. | `uv run pytest tests/test_ui_router.py -k "screen_modules"` (smoke crece con `revelation`) | Export y smoke verdes. |
| [x] 3.5 | Wiring: `src/ui/app.py` — `_submit_vote` (nuevo) + renderer `REVELATION` en el mapa de pantallas; `session_state.router` maneja `Screen.REVELATION`. | `uv run app` (harness manual; AppTest de R3-1) | App arranca; REVELACION renders la revelación sin caer en VOTING. |

## Fase 4 — Verificación del incremento

| # | Tarea | Comando / Harness | Criterio de aceptación |
|---|-------|-------------------|------------------------|
| [x] 4.1 | Suite completa, cero warnings. | `uv run pytest` (con `filterwarnings = ["error"]`) | **Verificado por el orquestador 2026-09-17: 334 passed, cero warnings.** |
| [x] 4.2 | Ruff + Black. | `uv run ruff check .`; `uv run black --check .` | **Verificado por el orquestador 2026-09-17: ruff All checks passed; black 57 files unchanged.** |
| [x] 4.3 | Harness manual (no automatiza navegador): AppTest happy path a REVELACION con un voto humano real + narración multi-pestaña: alias no seleccionable, duplicado bloqueado, votos registrados, revelación terminal con transcript `is_ai` y `prompt_version`; sin ruta alternativa de cierre. | `uv run app` + manual | **Verificado por el orquestador 2026-09-17: AppTest 0 excepciones; happy path fake con voto humano real llega a REVELACION (impostor Jugador 3, prompt_version v2, self_vote 400 bloqueado, router → Screen.REVELATION). La narración multi-pestaña del navegador se cubre en el piloto 3.5 (miércoles por la noche).** |
| [x] 4.4 | ADDITIVIDAD: `git status --short` y `git diff --stat` del PR. | `git status --short; git diff --stat (vs develop)` | **Verificado por el orquestador 2026-09-17: diff vs origin/develop vacío en words.py/orchestrator/impostor_engine; contrato v1.1 con las 2 líneas aditivas exactas.** |

## Fase 5 — Rollback (contingencia, NO programada)

| # | Tarea | Comando / Harness | Criterio de aceptación |
|---|-------|-------------------|------------------------|
| 5.1 | Revertir el router a `REVELACION → VOTING` de R3-1. | `git revert <commit del paso 1.2>` | Router vuelve a R3-1; suite de router en verde. |
| 5.2 | Quitar pantalla de revelación: borrar `src/ui/revelation.py`, `src/ui/screens/revelation.py`, `tests/test_ui_revelation.py`; revertir `voting.py` a placeholder, callback `on_submit_vote` y wiring de `app.py`. | `git revert <commits de 3.2/3.3/3.4/3.5>` | App arranca sin revelación; `marks` de `__init__.py` coherentes. |
| 5.3 | Quitar dominio de votación: `submit_vote` fuera de api/fake/http y sus pruebas; contrato de vuelta a v1.0 (edición 2.4 revertida en el mismo commit). | `git revert <commits de 1.x/2.x>` | No queda referencia a `submit_vote`/`prompt_version`; `git status` limpio. |
| 5.4 | Verificación post-rollback. | `git status --short; uv run pytest; uv run ruff check .; uv run black --check .` | Verde; `src/orchestrator/`, `src/impostor_engine/` y `src/ui/words.py` intactos. |

## Work Units (grupos de trabajo y revisión)

| Work Unit | Slices / tareas | Estrategia de PR | Harness de ejecución | Rollback boundary |
|-----------|-----------------|------------------|----------------------|-------------------|
| WU-1 Dominio de votación | 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2 | Slice de revisión 1 del PR único a `develop` (guard-line 1); el router terminal y la boca `submit_vote` se revisan juntos porque el dominio no se usa aún sin pantallas. | `uv run pytest tests/test_ui_api.py tests/test_ui_router.py` | Revertir router (5.1) y `submit_vote` (5.3) sin que las pantallas se vean afectadas. |
| WU-2 Contrato y tolerancia | 2.3, 2.4 | El diff de 2.4 viaja con WU-1 en el mismo PR (edición única); la prueba de tolerancia 2.3 demuestra compatibilidad v1.0. | `uv run pytest tests/test_ui_api.py -k "toleranc or v1_0"`; `git diff docs/CONTRATO_UI_ORQUESTADOR.md` | Revertir 2.4 en el mismo commit → contrato vuelve a v1.0 (5.3). |
| WU-3 Pantallas | 3.1, 3.2, 3.3, 3.4, 3.5 | Último slice del PR único; solo aquí se dibujan controles y revelación; la revisión se enfoca en UI y en que `is_ai` solo aparece en REVELATION. | `uv run pytest tests/test_ui_revelation.py tests/test_ui_router.py`; harness manual (4.3) | Revertir pantallas y helper (5.2) sin tocar dominio. |

Presupuesto: ≈420–470 líneas autoradas → riesgo Medium; guard-line 5 en el header. NO se abre una
cadena de PRs (guard-line 1).

## Slices y dependencias

- Las fases 1→2→3 dependen en orden (submit_vote antes que pantallas; contrato antes de la
  verificación). La fase 4 es la puerta de entrega.
- Ninguna tarea depende de trabajo externo (R2, R1-8, ADR-003).
- El AppTest de R3-1 se re-ejecuta en 3.5/4.3 como regresión (voto scriptado aún funciona con
  `_complete_votes`).