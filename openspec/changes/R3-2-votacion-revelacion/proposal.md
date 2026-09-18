# Proposal: R3-2 — Votación real y pantalla de revelación en la UI

## Intent

R3-1 entregó el esqueleto navegable: la vista de votación existe como navegación vacía y
`REVELACION` se detecta como cierre sin presentar contenido (UIF-06, UIF-08 reservan esto a
R3-2). R3-2 convierte esa reserva en producto: la pantalla de votación pasa a tener **controles
reales** (seleccionar sospechoso, emitir voto contra `POST /rooms/{code}/votes`, bloqueo visual
contra voto a uno mismo y contra voto duplicado) y la pantalla de **REVELACION es terminal y
obligatoria** — un estado de la máquina, no una bandera ni una página que se pueda saltar. La
revelación muestra quién era el impostor, cómo votó cada jugador, si el grupo acertó, el
transcript con `is_ai` revelado (único lugar permitido, contrato §9) y la **versión del prompt
del impostor** (`prompt_version`, clave aditiva aprobada del contrato v1.1).

El contrato `docs/CONTRATO_UI_ORQUESTADOR.md` sube de 1.0 a **1.1** con exactamente una clave
aditiva en `result()` (`prompt_version`) y una fila en el registro de versiones (§15). El cambio
es 100 % UI: **no toca `src/orchestrator/`** (el servidor real emitirá `prompt_version` en el
futuro desde su `ServerConfig.system_prompt_version` existente; ese trabajo es del servidor de
R2, no de R3-2).

## Scope

### In Scope

- Pantalla de VOTACIÓN con controles reales: lista de sospechosos (los `players` de la sala),
  emisión de voto por el facade `submit_vote(room_code, session_token, suspect)`, alias propio
  deshabilitado/no seleccionable, voto duplicado bloqueado visualmente tras emitir, recuento
  (`votes_received`) siempre leído del orquestador (la UI no cuenta votos localmente).
- Pantalla de REVELACION **terminal y obligatoria**: el router resuelve `REVELACION` → una
  pantalla dedicada (nunca cae en VOTING); no existe ruta de UI que termine una partida sin
  pasar por REVELACION. Contenido: `impostor_alias`, `votes` + `vote_counts`, acierto del grupo
  (derivado de `scores`/`tasa_deteccion`), `transcript` con `is_ai` revelado (solo aquí, §9) y
  `prompt_version` del prompt del impostor.
- `submit_vote` en la boca única `api.py` (Protocol `SospechAI` + facade) y en las dos fuentes:
  `FakeSospechAI` (voto humano REAL, validaciones `self_vote`/`duplicate_vote`/`wrong_state`/
  `session_expired`/`not_a_player`, REVELACION cuando todos los humanos votaron, conservando el
  llenado scriptado `_complete_votes` para el poll) y `HttpSospechAI` (`POST /rooms/{code}/votes`,
  cuerpo `{"suspect": "Jugador N"}`, 204 por éxito, errores por `code`).
- Cambio aditivo de contrato a **v1.1** (solo en apply): clave `prompt_version` en §7.2 y fila en
  §15. El fake emite `prompt_version: "v2"`; el cliente HTTP lo tolera si está ausente (servidor
  v1.0) y lo transporta tal cual si está presente.
- Pruebas: ≥3 nuevas con estructura AAA cubriendo (a) validación de mensajes/votos y
  (b) la transición a REVELACION y el contenido de la revelación; además pruebas del
  `submit_vote` (happy path, `self_vote`, `duplicate_vote`, integración HTTP) y del helper puro
  de revelación.

### Out of Scope

- El servidor HTTP del orquestador (R2): R3-2 no modifica `src/orchestrator/`; la emisión de
  `prompt_version` en el servidor real es trabajo futuro sobre `ServerConfig.system_prompt_version`
  (no R3-2). La fuente por defecto sigue siendo el fake (Plan B).
- Tiempos, plazos de VOTACION (ADR-003 pendiente) y reglas de juego: UI solo muestra y envía
  (UIF-10).
- El movimiento de `normalize_text` a `src/common/text.py` (tarea R1-8 de Juan, avisará luego):
  R3-2 no crea una cuarta copia ni la mueve ahora; **R3-2 no toca `src/ui/words.py`**
  (`count_words`/`within_limit` quedan byte-idénticos).
- MLflow (R1) y Docker (R4); persistencia de partidas en la UI; E2E de navegador automatizado
  (la suite no automatiza navegador; el harness es AppTest + manual).
- La pantalla de revelación como bandera configurable o salteable: prohibido (ver requisito).

## Capabilities

> Esta sección es el CONTRATO entre proposal y specs.
> `openspec/specs/` contiene `ui-orchestrator-contract/` y `game-server/` (archivadas);
> `ui-flujo-partida/` sigue activa en `openspec/changes/R3-1-ui-flujo-partida/` (sin promover).

### New Capabilities

- `votacion-revelacion`: votación con controles reales contra `POST /rooms/{code}/votes`
  (bloqueo visual de auto-voto y de duplicado, autoridad del servidor en los códigos de error
  §8), REVELACION como estado terminal obligatorio del router con pantalla dedicada, y el
  contenido de la revelación desde `result()` (§7.2 incl. `prompt_version` v1.1): impostor,
  votos y recuentos, acierto del grupo, transcript con `is_ai` (único lugar, §9).

### Modified Capabilities

- `ui-orchestrator-contract` (documento, no spec): adición aditiva v1.1 — clave `prompt_version`
  en `result()` (§7.2) y fila en el registro de versiones (§15). **No se genera delta spec** para
  esta capacidad: su fuente de verdad es el archivo `docs/CONTRATO_UI_ORQUESTADOR.md`, que se
  edita una sola vez en apply (su propio task) y se referencia con precisión desde spec/design/
  tasks. El cambio es puramente aditivo (camino §13) y no rompe v1.0.
- `ui-flujo-partida` (activa en R3-1): NINGÚN requisito se modifica, renombra ni elimina; R3-2
  es un incremento que en la práctica sustituye los contenidos reservados por UIF-08 (controles
  de votación) y UIF-06 (presentación de REVELACION) con una capacidad nueva, dejando intactos
  los bloques de requisitos de R3-1.

## Approach

Entregar en cuatro fases dentro del mismo cambio (estrecho a un solo PR a `develop`):

1. **Router terminal y dominio de votación**: `Screen.REVELATION` dedicado en `router.py`
   (`REVELACION` → `REVELATION` explícito; `VOTACION` → `VOTING`; nunca cae en la pantalla de
   votación) y `submit_vote` real en `api.py` + `FakeSospechAI` (RED→GREEN, strict TDD).
2. **prompt_version y contrato v1.1**: el fake emite `prompt_version: "v2"` en `result()`;
   `HttpSospechAI` lo tolera ausente (passthrough ya garantizado por `from_mapping`); edición
   única del doc del contrato (§7.2 + §15) como tarea propia de apply.
3. **Pantallas**: votación con controles reales (callback `on_submit_vote`, alias propio
   deshabilitado, bloqueo visual tras emitir) y pantalla de revelación con contenido, apoyadas
   en un helper puro `src/ui/revelation.py` (testeable sin Streamlit, patrón de R3-1).
4. **Verificación**: suite completa, ruff/black, harness AppTest del happy path hasta
   REVELACION con voto humano real, y comprobación de que el cambio es aditivo.

La autoridad de la votación es el orquestador: la UI deshabilita el clic obvio (alias propio) y
bloquea el duplicado visualmente tras emitir, pero los rechazos reales (`self_vote` 400,
`duplicate_vote` 409) los impone la fuente y la UI los muestra sin presentar el voto como
emitido (contrato §8). REVELACION es un estado de la máquina, no una bandera (AGENTS), y la
revelación se obtiene por fetch del estado final en el poll (§14.4, default aceptado por R3).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/ui/router.py` | Modified | Añade `Screen.REVELATION` y mapea `REVELACION` → `REVELATION` (terminal; nunca VOTING). Frecuencias de polling intactas. |
| `src/ui/api.py` | Modified | Añade `submit_vote` al Protocol `SospechAI` y al facade. |
| `src/ui/sources/fake.py` | Modified | `submit_vote` real (validaciones §8, registra el voto humano, REVELACION cuando votan todos los humanos) y `prompt_version: "v2"` en `_result`. |
| `src/ui/sources/http.py` | Modified | `submit_vote` → `POST /rooms/{code}/votes` con `{"suspect": ...}` (204); `prompt_version` tolerado si ausente (sin nuevo código). |
| `src/ui/revelation.py` | New | Helper puro (sin `st`) que deriva el contenido de `result()`: impostor, votos, acierto, interruption_reason, prompt_version. |
| `src/ui/screens/voting.py` | Modified | Controles reales: sospechosos `players`, alias propio deshabilitado, emisión de voto, bloqueo visual de duplicado, `votes_received`, avisos de rechazo. |
| `src/ui/screens/revelation.py` | New | Pantalla de revelación con todo el contenido (UIF-17/18); único lugar con `is_ai`. |
| `src/ui/screens/context.py` | Modified | Añade callback `on_submit_vote`. |
| `src/ui/screens/__init__.py` | Modified | Exporta `render_revelation`. |
| `src/ui/app.py` | Modified | Wiring `_submit_vote`, renderer `REVELATION` en el mapa de pantallas. |
| `docs/CONTRATO_UI_ORQUESTADOR.md` | Modified (apply) | v1.1: §7.2 fila `prompt_version`; §15 fila `1.1 \| 2026-09-18`. |
| `tests/test_ui_router.py` | Modified | `REVELACION` → `REVELATION`; escenarios de terminal obligatorio. |
| `tests/test_ui_api.py` | Modified | `submit_vote` (fake + integración HTTP), `prompt_version` (RESULT_KEYS + tolerancia). |
| `tests/test_ui_revelation.py` | New | Pruebas AAA del helper de revelación. |

Resumen: **2 archivos nuevos** (`revelation.py` x2: helper + pantalla), **10 modificados**,
**0 eliminados**. `src/orchestrator/`, `src/impostor_engine/` y `src/ui/words.py` no se tocan.

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| La UI y el servidor pueden divergir en la autoridad de la votación (self_vote/duplicate) | Med | El servidor es autoritativo (§8): la UI hace bloqueo visual obvio (alias propio deshabilitado, botón tras emitir), pero propaga y muestra los rechazos reales sin presentar el voto como emitido; el fake replica los códigos exactos. |
| Dependencia del contrato v1.1 `prompt_version` | Low | Clave aditiva aprobada (§13): http nunca falla si el servidor v1.0 no la emite (SHOULD de tolerancia); el fake la emite con el default `"v2"`. |
| Doble clic / voto duplicado | Med | La UI bloquea la re-emisión visualmente tras el 204; el duplicado defensor es `duplicate_vote` 409 mostrado. |
| `REVELACION` saltable o re-caída en VOTING | Low | Estado de máquina (AGENTS): router con `Screen.REVELATION` explícito + tests de transición (`REVELACION` nunca → VOTING); sin acción de UI que cierre la partida fuera de la revelación. |
| R1-8 (mover `normalize_text`) en paralelo | Low | R3-2 no toca `words.py` ni crea una cuarta copia; si algún task tocara `words.py`, debe mantener `count_words`/`within_limit` byte-idénticos y coordinar con Juan. |
| Presupuesto de revisión (≈400 líneas) | Med | Un solo PR a `develop` decidido; tareas agrupadas en fases revisables; estimación reportada como Medium en tasks. |

## Rollback Plan

El cambio es aditivo y no toca `src/orchestrator/` ni `src/impostor_engine/`, por lo que
revertir no afecta al motor ni al orquestador (los árboles quedan intactos):

1. Revertir el router: `git revert` del commit que añade `Screen.REVELATION` y el mapeo
   `REVELACION → REVELATION` (vuelve a caer en `VOTING` como R3-1).
2. Eliminar la pantalla de revelación: borrar `src/ui/screens/revelation.py`, `src/ui/revelation.py`
   y `tests/test_ui_revelation.py`; revertir `voting.py` al placeholder de R3-1, el callback
   `on_submit_vote` de `context.py` y el wiring en `app.py`.
3. Revertir el dominio de votación: quitar `submit_vote` del Protocol/facade en `api.py` y de
   `fake.py`/`http.py` y sus pruebas en `tests/test_ui_api.py`; revertir el doc del contrato a
   v1.0 (§7.2 y §15) en el mismo commit de la edición.
4. Verificar con `git status --short` que solo quedan cambios no deseados revertidos, que
   `src/orchestrator/`, `src/impostor_engine/` y `src/ui/words.py` quedan intactos, y que
   `uv run pytest` pasa en verde.

No hay migración de datos: ninguna pantalla persiste estado de partida.

## Dependencies

- Contrato `docs/CONTRATO_UI_ORQUESTADOR.md` v1.0 (fuente de verdad) + v1.1 aprobada (clave
  aditiva `prompt_version`, 2026-09-18) — la edición del archivo ocurre solo en apply.
- R3-1 mergeado en `develop` (esqueleto navegable, `src/ui/*`, `FakeSospechAI` y
  `HttpSospechAI` ya existentes) — base de este incremento.
- Servidor HTTP real (R2): NO necesario para R3-2 (fuente default `fake`); el contrato del
  cliente HTTP se prueba contra un `ThreadingHTTPServer` local (mismo patrón R3-1).
- R1-8 (mover `normalize_text` a `src/common/text.py`): independiente y diferido por Juan;
  R3-2 no la bloquea ni depende de ella.

## Success Criteria

- [ ] Desde la pantalla de votación, un humano elige un sospechoso (el propio alias está
      deshabilitado), el voto se registra (204) y, cuando votan todos los humanos, la UI llega a
      REVELACION.
- [ ] El router resuelve `REVELACION` → una pantalla dedicada (`Screen.REVELATION`) y no existe
      ninguna ruta de UI que termine la partida sin pasar por la revelación.
- [ ] La revelación muestra impostor, votos/recuentos, acierto del grupo, transcript con `is_ai`
      (único lugar, §9) y `prompt_version`; con servidor v1.0 (sin `prompt_version`) la UI no
      falla (SHOULD de tolerancia).
- [ ] `self_vote` (400) y `duplicate_vote` (409) se rechazan y se muestran sin presentar el voto
      como emitido.
- [ ] `docs/CONTRATO_UI_ORQUESTADOR.md` queda en v1.1 con `prompt_version` en §7.2 y la fila en §15.
- [ ] ≥3 pruebas nuevas AAA (validación de mensajes/votos + transición a REVELACION) en verde;
      suite completa sin warnings con `filterwarnings = ["error"]`.
- [ ] `uv run ruff check` y `uv run black --check` limpios en el código nuevo.
- [ ] `git status --short` sin cambios no deseados; cero cambios en `src/orchestrator/`,
      `src/impostor_engine/` y `src/ui/words.py` (aditivo, UIF-10).