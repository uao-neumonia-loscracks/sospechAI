# Apply Progress — R3-2 / votacion-revelacion

> Ejecución del EXECUTOR de `sdd-apply` sobre la rama
> `feature/r3-2-votacion-revelacion` (base `develop` @ 7608ab0).
> strict_tdd: true — fases RED→GREEN obligatorias. Sin commits ni pushes
> (entrega el orchestrator).

## Fase 1 — Router terminal y dominio de votación (2026-09-18)

- [x] 1.1 RED: test_ui_router.py — `REVELACION → Screen.REVELATION` y
  `test_revelacion_es_terminal_y_nunca_cae_en_voting`. Confirmado RED:
  `AttributeError: type object 'Screen' has no attribute 'REVELATION'`.
- [x] 1.2 GREEN: router.py — `Screen.REVELATION = "revelation"` en el enum +
  rama `REVELACION` en `resolve_screen`. `uv run pytest tests/test_ui_router.py` → 15 passed.
- [x] 1.3 RED: test_ui_api.py — `_voting_room()`, 7 casos de `submit_vote`
  (happy→revela en el siguiente poll, todos los humanos votan sin guion,
  self_vote 400, duplicate_vote 409, not_a_player 403, session_expired 401,
  wrong_state 409). `RESULT_KEYS` actualizado con `prompt_version` (gatillo).
  Confirmado RED: `ImportError: cannot import name 'submit_vote'`; además el
  test existente de revelación caía por `RESULT_KEYS` (dependencia cruzada con 2.2).
- [x] 1.4 GREEN: api.py (Protocol + facade `submit_vote`) y fake.py
  (validación §8 en orden: wrong_state → alias → sospechoso-jugador →
  self_vote → AI-guard → duplicate_vote → registro en `_Room.votes`).
  `_complete_votes` del poll preservado; `test_submit_vote_*` → 6 passed;
  el único fallo restante era `RESULT_KEYS/prompt_version` (se cierra en 2.2).
- [x] 1.5 RED+VERIFY: test_ui_api.py — servidor de prueba (+`votes`, `result`,
  ruta `POST /rooms/{code}/votes` → `_op_votes`) y 3 pruebas de integración
  HTTP (204 registra, self_vote 400, duplicate_vote 409). RED:
  `AttributeError: 'HttpSospechAI' object has no attribute 'submit_vote'`.
- [x] 1.6 GREEN: http.py — `submit_vote` → `POST /rooms/{code}/votes` con
  `{"suspect": ...}`; 204=éxito; errores por `code` (§8). 3 passed. Suite
  api/router: **54 passed** (solo quedaba verde el 2.2 pendiente por RESULT_KEYS).

## Fase 2 — prompt_version y contrato v1.1 (2026-09-18)

- [x] 2.1 RED: test_ui_api.py — `test_result_del_fake_emite_prompt_version_v2`.
  Confirmado RED: `KeyError: 'prompt_version'`.
- [x] 2.2 GREEN: fake.py — `_result` emite `prompt_version: "v2"`. Cierra el
  gatillo `RESULT_KEYS` de 1.3. `uv run pytest tests/test_ui_api.py` → **38 passed**.
- [x] 2.3 VERIFY: test_ui_api.py — `test_get_state_tolera_result_v10_sin_prompt_version`
  (servidor `result` sin la clave) → pasa SIN tocar http.py (passthrough `from_mapping`).
- [x] 2.4 CONTRATO: `git diff docs/CONTRATO_UI_ORQUESTADOR.md` = exactamente 2
  líneas aditivas: fila `prompt_version` en §7.2 + fila `1.1 | 2026-09-18`
  en §15. Cabecera `**Versión**: 1.0` intacta.

## Fase 3 — Pantallas: votación real y revelación (2026-09-18)

- [x] 3.1 RED: tests/test_ui_revelation.py — 10 casos AAA (impostor, votos
  ordenados por votante, recuentos por conteo desc + alias asc, acierto por
  `tasa_deteccion`, interrupción sin tasa inventada, transcript conserve `is_ai`,
  `prompt_version` presente/ausente, claves ausentes no explotan, summary
  compone). RED: `ModuleNotFoundError: No module named 'src.ui.revelation'`.
- [x] 3.2 GREEN: src/ui/revelation.py — helpers puros (sin streamlit, ≤40
  líneas, docstring+type hints, `.get()` siempre): `revelation_impostor`,
  `revelation_votes`, `revelation_vote_counts`, `group_verdict`,
  `revelation_transcript`, `prompt_version_text`, `revelation_summary`.
  10 passed; ruff limpio; black aplicado.
- [x] 3.3 Pantalla de votación real: context.py `on_submit_vote` + voting.py —
  sospechosos de `players`, alias propio excluido, `vote_accepted` desactiva los
  controles tras 204 («voto registrado; esperando al resto»),
  `votes_received` desde la instantánea, rechazos como notice sin presentar el
  voto. Sin regresiones en api/router.
- [x] 3.4 Pantalla de revelación: screens/revelation.py (render con los
  helpers; ÚNICO lugar con `is_ai` §9) + export `render_revelation` en
  `src/ui/screens/__init__.py`. `SCREEN_MODULES` del smoke crece con
  `src.ui.screens.revelation`. Router → **15 passed**.
- [x] 3.5 Wiring: app.py — `_submit_vote` = `_mutate(api.submit_vote, suspect)`,
  renderer `Screen.REVELATION: render_revelation`, `on_submit_vote` en el
  ScreenContext. Smoke de arranque (imports app + screens) en verde.

## Fase 4 — Verificación del incremento (2026-09-18)

- [x] 4.1 Suite completa: `uv run pytest` → **334 passed** en 36.76s, cero
  warnings (pytest con `filterwarnings = ["error"]`).
- [x] 4.2 Ruff + Black: `uv run ruff check .` → All checks passed;
  `uv run black --check .` → 57 files unchanged (nuevos formateados).
- [ ] 4.3 Harness manual (humano): AppTest happy path a REVELACION con un voto
  humano real + narración multi-pestaña (alias no seleccionable, duplicado
  bloqueado, votos registrados, revelación terminal con transcript `is_ai` y
  `prompt_version`, sin ruta alternativa). Comando: `uv run app`.
- [x] 4.4 Additividad: `git status --short` solo con el ámbito del cambio;
  `git diff` vacío en `src/orchestrator/`, `src/impostor_engine/` y
  `src/ui/words.py`; contrato v1.1 con el diff exacto de 2.4.

## TDD Cycle Evidence

| Ciclo | RED (prueba falla) | GREEN (prueba pasa) | Fases |
|---|---|---|---|
| Router REVELACION | `test_resolve_screen_after_consent_maps_state_to_screen` + terminal | `...maps_state...` con REVELATION + terminal | 1.1 → 1.2 |
| submit_vote fake | 6/7 casos `submit_vote` (colección: ImportError) | 6 `test_submit_vote_*` verdes | 1.3 → 1.4 |
| submit_vote http | 3 integración HTTP | 3 integración HTTP verdes | 1.5 → 1.6 |
| prompt_version | `KeyError` en `test_result_del_fake_emite_prompt_version_v2` (y RESULT_KEYS) | 38 passed api | 2.1 → 2.2 |
| Helpers de revelación | colección: `src.ui.revelation` no existe | 10 passed revelation | 3.1 → 3.2 |

**Dependencia cruzada honesta**: la actualización de `RESULT_KEYS` en 1.3
(mandato de tasks.md) dejó el test existente de revelación en rojo hasta 2.2
(fake emite `prompt_version`). Se documentó como fallo esperado en el critario
de 1.3 («`RESULT_KEYS` falla por `prompt_version`») y se cerró en 2.2.

## Work Unit Evidence

| Work Unit | Slices | Estado | Rollback boundary |
|---|---|---|---|
| WU-1 Dominio de votación | 1.1–1.6, 2.1, 2.2 | ✅ aplicado | revertir router (5.1) y submit_vote (5.3) |
| WU-2 Contrato y tolerancia | 2.3, 2.4 | ✅ aplicado | revertir 2.4 junto a WU-1 (5.3) |
| WU-3 Pantallas | 3.1–3.5 | ✅ aplicado | revertir pantallas y helper (5.2) |

## Desviaciones y notas

- La firma del facade es `submit_vote(room_code, session_token, suspect)`
  (patrón del facade existente con claves explícitas). El D2 del design.md
  describía `submit_vote(chat_session, suspect)`, pero la boca `api.py` actual
  usa claves explícitas en todos sus verbos; se siguió el patrón factual del
  código para consistencia. Sin impacto en contrato.
- `ai_cannot_vote` 403: guard defensivo en el fake, estructuralmente
  inalcanzable (la IA no tiene token). Sin prueba dedicada (D3).
- Tras un 204, voting.py marca `session_state["vote_accepted"] = True`; un
  rechazo (`ApiError`) deja la bandera intacta y muestra el notice, de modo que
  el voto nunca se presenta como emitido (UIF-14).
- La UI no cuenta votos localmente: `votes_received` siempre viene de la
  instantánea (UIF-13).

## Issues

- Ninguno bloqueante. Sin llamadas a API real de Hugging Face (fake y
  ThreadingHTTPServer local únicamente).

## Tareas pendientes

- 4.3: harness manual (humano, `uv run app`); el orchestrator decide la
  verificación del PR (harness + narración multi-pestaña).
---

# Verificaci�n del orquestador (2026-09-17, gate de entrega)

## Evidencia re-ejecutada (spot check independiente)

| Criterio | Comando | Resultado |
|---|---|---|
| 4.1 Suite completa, cero warnings | uv run pytest | **334 passed in 35.49s**, cero warnings (filterwarnings=error) |
| 4.2 Estilo limpio | uv run ruff check . | **All checks passed!** |
| 4.2 Estilo limpio | uv run black --check . | **57 files would be left unchanged** (exit 0) |
| Router + helpers | uv run pytest tests/test_ui_router.py tests/test_ui_revelation.py | **25 passed** |
| Aditividad (UIF-10, guard-line 2) | git diff --stat origin/develop -- src/ui/words.py src/orchestrator src/impostor_engine | **vac�o** � words.py byte-id�ntico, orchestrator/engine intactos |
| Contrato v1.1 | git diff origin/develop -- docs/CONTRATO_UI_ORQUESTADOR.md | Exactamente 2 l�neas aditivas: �7.2 prompt_version + �15 fila v1.1 |
| Arranque AppTest | AppTest.from_file('src/ui/app.py').run() | 0 excepciones, t�tulo "Consentimiento informado" |

## Happy path manual (fake, voto humano real)

create ? join (Jugador 2) ? start (IA = Jugador 3, rounds=2) ? 2 rondas de mensaje ?
DISCUSION ? VOTACION (votes_received 0) ? **self_vote ? ApiError(self_vote, 400)** ?
submit_vote("Jugador 2") ? **REVELACION** ? result: impostor "Jugador 3",
prompt_version "v2", votes {Jugador 1: Jugador 2, Jugador 2: Jugador 3} ?
resolve_screen ? **Screen.REVELATION** (nunca VOTING).

Resultado: el voto humano real se registra, el auto-voto se bloquea (UI + fake 400),
todos los humanos votaron ? revelaci�n terminal con transcript is_ai y prompt_version.
La narraci�n multi-pesta�a del navegador queda para el piloto 3.5 (mi�rcoles por la noche).

## 4.3 � nota

La tarea 4.3 (harness manual navegador) queda cubierta en el paso 3.5 del plan
(conducci�n del piloto): guiar jugadores y anotar defectos sin arreglarlos. No se
automatiza navegador (no hay E2E en la suite, decisi�n de R3-1).
