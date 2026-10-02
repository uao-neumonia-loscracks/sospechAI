# Design: R3-2 — Votación real y pantalla de revelación en la UI

## Context

R3-1 dejó la app navegable con polling (CONSENT → LOBBY → CHAT → VOTING) y `FakeSospechAI` /
`HttpSospechAI` intercambiables bajo un Protocol. `resolve_screen` devuelve actualmente
`Screen.VOTING` para `state == "REVELACION"` (placeholder que muestra el texto duro de UIF-06), y
la pantalla de votación es un placeholder que no emite votos. El contrato
`docs/CONTRATO_UI_ORQUESTADOR.md` (v1.0) ya define `POST /rooms/{code}/votes` (§6.6), los códigos
de error (§8), el contenido de `result()` (§7.2) y la prohibición de exponer `is_ai` fuera del
estado final (§9). La v1.1 aprobada añade la clave aditiva `prompt_version` a `result()`.

## Goals

- Controles reales de votación contra `POST /rooms/{code}/votes`, con autoridad del servidor.
- `REVELACION` como estado terminal de la máquina: pantalla dedicada e ineludible.
- Contenido de revelación completo desde `result()` (impostor, votos, acierto, transcript con
  `is_ai` — único lugar §9 —, `prompt_version`).
- Compatibilidad hacia atrás: cliente HTTP tolera servidor v1.0 sin `prompt_version`.
- Fake como fuente por defecto (Plan B) registrando el voto humano y llegando a REVELACION.
- Cero cambios en `src/orchestrator/`, `src/impostor_engine/` y `src/ui/words.py`.

## Non-Goals

- Modificar el servidor real del orquestador (R2) ni su `ServerConfig.system_prompt_version`.
- Reglas de juego, plazos de VOTACION (ADR-003 pendiente) ni tiempos.
- Mover `normalize_text` (R1-8, tarea de Juan) ni tocar `src/ui/words.py`.
- E2E de navegador automatizado; el harness es AppTest + manual.

## Decisions

### Decision 1: `REVELACION` → pantalla dedicada `Screen.REVELATION` (terminal)

- **Opción A (elegida)**: añadir `Screen.REVELATION` al enum y mapear `REVELACION` explícitamente
  a él en `resolve_screen`. Es un estado de la máquina.
- **Opción B (rechazada)**: seguir cayendo en `VOTING` y mostrar un banner de «partida terminada».
  Viola AGENTS.md («La pantalla de revelacion es un estado de la maquina, no una bandera») y
  UIF-16 (votar después del fin de partida o enmascararlo como votación).
- **Opción C (rechazada)**: redirigir `REVELACION` a `LOBBY`. Pierde la revelación y permite
  cerrar la partida sin ver el resultado (terminal obligatorio violado).

Consecuencia: `resolve_screen(state, phase, has_consent)` devuelve `Screen.REVELATION` cuando
`state == "REVELACION"`, sin importar `phase`. Las frecuencias de polling no cambian; el mapa de
pantallas de `app.py` registra el renderer `REVELATION`.

### Decision 2: `submit_vote` en la boca única `api.py` (Protocol + facade)

- **Opción A (elegida)**: `submit_vote(chat_session, suspect) -> None` en el Protocol `SospechAI`
  (recibe el `ChatSession` con `session_token`/`room_code` ya gestionados por el facade actual) y
  despacho facade `_submit_vote` hacia la fuente activa, devolviendo la señal de éxito por la
  presencia de `api` (patrón del facade existente).
- **Opción B (rechazada)**: lógica de emisión dentro de `screens/voting.py` con `st.session_state`.
  Rompe la «boca única» api→fuentes, no testeable, acopla Streamlit al protocolo.
- **Opción C (rechazada)**: clase cliente HTTP separada para votos. Duplica el facade.

El facade traduce la excepción de la fuente en `notice` para la pantalla y marca el éxito sin
contar votos (la UI nunca suma; solo lee `votes_received`).

### Decision 3: Protección de auto-voto y duplicado: UI evidente + servidor autoritativo

- UI (evidencia clic): el alias propio se excluye de las opciones activas (deshabilitado) y, tras
  un 204, los controles se desactivan («voto registrado; esperando al resto»).
- Servidor (autoridad real): el fake replica los códigos exactos del contrato — `self_vote` 400,
  `duplicate_vote` 409, `wrong_state` 409, `not_a_player` 403, `session_expired` 401,
  `ai_cannot_vote` 403 (guard defensivo en el fake, estructuralmente inalcanzable porque la IA no
  tiene token; sin prueba dedicada).
- UI frente a rechazo: todo `ApiError` de emisión se muestra como aviso SIN presentar el voto
  como emitido (UIF-14/15).

### Decision 4: Fake con voto humano real, sin romper el happy path scriptado

`FakeSospechAI._vote(session_token, suspect)` valida contra reglas internas en orden: UUID del
jugador activo (de la sala del token), `wrong_state`, `self_vote`, `duplicate_vote`,
`not_a_player`. Si todo pasa, registra en `_Room.votes[player_id] = suspect` (autoridad única).
`_room_status` codifica `REVELACION` cuando **todos** los `_Player` humanos de la sala votaron;
el llenado scriptado `_complete_votes` del poll de `VOTACION` sigue completando a los humanos que
faltan para que el AppTest de R3-1 (voto de un solo humano) llegue a REVELACION sin interacción.

### Decision 5: contrato v1.1, edición aditiva única en apply

Una sola edición del archivo `docs/CONTRATO_UI_ORQUESTADOR.md` (tarea propia de apply):
incrementar `§7.2 result()` con la fila `prompt_version | string | null | Version del prompt del
impostor; default "v2"` y añadir la fila `1.1 | 2026-09-18 | Clave aditiva prompt_version en
result() para transparencia del prompt del impostor (R3-2)` en `§15`. Cambio por el camino §13
(aditivo, compatible); el archivo sigue siendo la fuente de verdad de la capacidad
`ui-orchestrator-contract`. El fake emite `prompt_version: "v2"`.

### Decision 6: contenido de revelación desde un helper puro `src/ui/revelation.py`

La derivación de la pantalla vive en un módulo puro (sin `import streamlit`), patrón del helper de
R3-1, testeable: responde 1 función por bloque (impostor, votos/recuentos, acierto +
`interruption_reason`, transcript con `is_ai`, `prompt_version`). Cada función ≤40 líneas, usa
`.get()` (nunca `[]`) para degradar sin excepción cuando faltan claves (soporta UIF-18). La
pantalla `screens/revelation.py` solo formatea lo derivado. `is_ai` se dibuja exclusivamente aquí
(§9).

### Decision 7: no se toca `src/ui/words.py` (R1-8)

R3-2 no crea una cuarta copia de `normalize_text` ni la mueve a `src/common/text.py` (R1-8, de
Juan). El contador de mensajes sigue usando `words.py` sin cambios: `count_words` y
`within_limit` quedan byte-idénticos, y el CHAT vuelve a limitarse cuando el total del transcript
lo exige, ahora con el resultado real del engine/impostor de aplicación (no con el cli).

### Decision 8: testabilidad — helpers puros + integración HTTP local

- `tests/test_ui_revelation.py`: AAA contra `src/ui/revelation.py` (válida, interrumpida, claves
  ausentes, orden de `votes`/`vote_counts`, detección de `is_ai`, `prompt_version`).
- `tests/test_ui_api.py`: `submit_vote` contra el fake (happy, `self_vote`, `duplicate_vote`,
  `not_a_player`, `wrong_state`) y contra un `ThreadingHTTPServer` local (mismo patrón de R3-1)
  que responde 204 / 400 / 409 y `result()` SIN `prompt_version` (tolerancia).
- `tests/test_ui_router.py`: `REVELACION` → `REVELATION`; `VOTACION` → `VOTING`; terminal
  obligatorio (sin ruta alternativa). `RESULT_KEYS` en `test_ui_api.py` se actualiza con
  `prompt_version` como gatillo RED del test existente de revelación.

### Decision 9: límites de arquitectura — sin orquestador ni engine

El router, la boca `api.py`, las fuentes, `revelation.py` y las pantallas conforman el único
ámbito de R3-2. Se verifica que el diff no toca `src/orchestrator/**`, `src/impostor_engine/**` ni
`src/ui/words.py` (guard del apply). Sin import gRPC en pantallas; el estado llega solo por
`StateSnapshot`/`result`.

## Sequence Diagrams

### Diagrama 1 — Voto feliz con `FakeSospechAI` (fuente por defecto)

```mermaid
sequenceDiagram
    autonumber
    actor H as Humano
    participant V as Screens/voting (UI)
    participant A as api.py (fal con fuente = fake)
    participant F as FakeSospechAI
    H->>V: elige sospechoso (!= propio) y envía
    V->>A: submit_vote(chat_session, "Jugador N")
    A->>F: fake.submit_vote(session_token, "Jugador N")
    F->>F: valida wrong_state|self_vote|duplicate_vote|not_a_player
    F->>F: _Room.votes[player] = "Jugador N"
    F-->>A: ok (token)
    A-->>V: éxito -> notice «voto registrado»
    V->>V: controles desactivados; solo muestra votes_received
    loop poll VOTACION
        A->>F: get_state; _complete_votes completa humanos faltantes
        F-->>A: REVELACION + result {impostor_alias, votes, vote_counts, transcript(is_ai), prompt_version:"v2"}
    end
    A-->>V: snapshot.result (fetch del estado final, §14.4)
    V->>R: router.resolve_screen(REVELACION,…) = Screen.REVELATION
    V->>P: render_revelation(result) (helpers puros)
    P-->>H: impostor, votos, acierto, transcript con is_ai, prompt_version
```

### Diagrama 2 — Voto feliz con `HttpSospechAI` (contra el contrato)

```mermaid
sequenceDiagram
    autonumber
    actor H as Humano
    participant V as Screens/voting (UI)
    participant A as api.py (fal con fuente = http)
    participant X as HttpSospechAI
    participant S as Orquestador (HTTP real / local de test)
    H->>V: elige sospechoso (!= propio) y envía
    V->>A: submit_vote(chat_session, "Jugador N")
    A->>X: http.submit_vote(session_token, "Jugador N")
    X->>S: POST /rooms/{code}/votes {"suspect": "Jugador N"}
    S-->>X: 204
    X-->>A: ok
    A-->>V: éxito -> notice «voto registrado»; controles desactivados
    loop poll VOTACION → REVELACION
        A->>X: get_state()
        X->>S: GET /rooms/{code}/state
        S-->>X: REVELACION + result (v1.0 sin prompt_version, o v1.1 con él)
        X-->>A: StateSnapshot (result transporta tal cual)
    end
    A-->>V: snapshot.result (fetch del estado final, §14.4)
    V->>R: router.resolve_screen(REVELACION,…) = Screen.REVELATION
    V->>P: render_revelation(result) (get() degrada prompt_version ausente)
    P-->>H: revelación completa; prompt_version ausente -> texto genérico (SHOULD UIF-18)
```

### Diagrama 3 — Rechazos de voto (auto-voto y duplicado), servidor autoritativo

```mermaid
sequenceDiagram
    autonumber
    actor H as Humano
    participant V as Screens/voting (UI)
    participant A as api.py
    participant F as Fuente (fake / HTTP)
    H->>V: intenta votar por su propio alias (bypass visual)
    V->>A: submit_vote(chat_session, propio)
    A->>F: submit_vote(…)
    F-->>A: ApiError(code="self_vote", http_status=400)
    A-->>V: notice de rechazo (nunca éxito)
    V-->>H: muestra el motivo; NO presenta el voto; votes_received intacto
    H->>V: intenta un segundo voto (voto ya registrado)
    V->>A: submit_vote(chat_session, otro)
    A->>F: submit_vote(…)
    F-->>A: ApiError(code="duplicate_vote", http_status=409)
    A-->>V: notice de rechazo (nunca éxito)
    V-->>H: muestra el motivo; recuento intacto
```

## Risks and Trade-offs

| Riesgo | Mitigación |
|--------|------------|
| Divergencia UI/servidor en la autoridad (self_vote/duplicate) | Servidor autoritativo (§8); UI solo bloqueo visual obvio + muestra rechazos sin presentar el voto. |
| `prompt_version` ausente en servidores v1.0 | Clave aditiva (§13); helpers con `.get()`; SHOULD de tolerancia en http y pantalla. |
| Doble clic → duplicado | Controles desactivados tras 204 + `duplicate_vote` 409 mostrado. El fake replica el código exacto. |
| Quebrar el happy path scriptado del AppTest | `_complete_votes` preservado en el poll de VOTACION; la suite completa se ejecuta antes de entregar. |
| `REVELACION` saltable (bandera vs estado) | Estado de máquina (D1) + tests de transición y de ruta terminal obligatoria. |
| Presupuesto de revisión (~400 líneas) | Un solo PR a develop decidido (guard-lines en tasks); fases revisables. |

## Threat Matrix

| Amenaza | ¿Aplica? | Explicación |
|---------|----------|-------------|
| Contrato gRPC modificado | N/A | `proto/impostor.proto` congelado; R3-2 no lo toca (el del contrato UI es aditivo v1.1 vía §13). |
| Orchestrator importa engine | N/A | `src/orchestrator/` sin cambios. |
| `src/common` con conocimiento de partida/gRPC | N/A | `src/common/` no se modifica. |
| Engine conoce rondas/votos/jugadores | N/A | `src/impostor_engine/` sin cambios. |
| UI habla gRPC directo con el engine | N/A | Solo api.py → fuentes (fake/http) contra el contrato. |
| Acceso a atributos privados de otro módulo | N/A | Facades y helpers respetan `_`; las pruebas negras no inspeccionan privados de `chat.py`/`engine`. |
| Nueva vía de normalización de texto | N/A | `src/ui/words.py` byte-idéntico; ninguna vía nueva (en las rutas que participan del experimento). |
| `is_ai` expuesto fuera del estado final | N/A | Solo se renderiza en la pantalla de revelación; el resto de pantallas no tocan `is_ai` (diagrama y UIF-17 tienen expectativas). |
| Secretos / HF_TOKEN filtrados | N/A | R3-2 no introduce red ni credenciales; urllib solo a `localhost` en tests. |

## Constraint Analysis / Performance

- El contenido de revelación deriva de un dict por poll único (cuando `REVELACION` aparece); sin
  cómputos por mensaje. `votes`/`vote_counts`/`transcript` se ordenan 1 vez.
- El helper puro de revelación es O(tamaño de transcript) y ≤40 líneas por función (AGENTS).
- Sin nueva serialización ni red por pantalla: el voto usa el mismo canal urllib del cliente
  existente y el poll no cambia su cadencia.

## Backward Compatibility

- La clave `prompt_version` es aditiva (v1.1); los servidores v1.0 no la emiten y el cliente HTTP
  la tolera (UIF-18). El fake la emite siempre con `"v2"`.
- `FakeSospechAI` mantiene su contrato visual: nuevo `submit_vote` + `_result` con
  `prompt_version`; `_complete_votes` y el AppTest de R3-1 siguen funcionando.
- `HttpSospechAI` añade `submit_vote`; `get_state` no cambia su firma.
- El router añade un miembro al enum `Screen` (aditivo; `SCREEN_MODULES` del smoke crece con
  `revelation`). Ningún call site de `foo.bar` se rompe con el cambio de `REVELACION`.

## Alternative Designs Considered

1. **Banner «partida terminada» sobre VOTING** (D1-B): rechazado por bandera y no-terminal.
2. **Lógica de voto dentro de la pantalla** (D2-B): rechazado por acoplar Streamlit y romper la
   boca única.
3. **Verificación local del duplicado en la UI por `votes`** (counter local): rechazado, la UI no
   cuenta (UIF-13); el estado llega por `votes_received`.
4. **Derivación de revelación inline en `app.py`**: rechazado por testabilidad (D6).
5. **Editar `words.py` para unificar normalización aquí**: rechazado, es R1-8 de Juan; R3-2 no
   duplica ni mueve.

## Scope Decisions (explícitas)

- **Incluido**: votación real, pantalla de revelación, `submit_vote` en api.py/fuentes,
  `prompt_version` (fake emite, http tolera, contrato v1.1), pruebas nuevas, helper puro.
- **Diferido**: tiempos/plazos de VOTACION (ADR-003), prompt_version real del servidor (R2),
  R1-8 (mover `normalize_text`), service de autenticación real (sigue contrato v1.0),
  persistencia de partidas en la UI, E2E de navegador.
- **Decisión pendiente antes de aplicar: NO.** Todos los puntos abiertos de la v1.0 (§14) que
  afectan a R3-2 ya están resueltos: tiempo de votación ad-hoc (UIF-10), fetch del estado final
  (§14.4, default), no preferencia posicional (UIF-N).

## Testing Strategy

- **Unidad**: `tests/test_ui_revelation.py` (helpers puros AAA: válida, interrumpida, claves
  ausentes, orden, `is_ai`, `prompt_version`) y `tests/test_ui_api.py` (`submit_vote` fake +
  RESULT_KEYS con `prompt_version`).
- **Integración**: `tests/test_ui_api.py` con `ThreadingHTTPServer` local en `subTest` (patrón
  R3-1) para 204/400(`self_vote`)/409(`duplicate_vote`) y `result()` v1.0 sin `prompt_version`
  (tolerancia). El servidor de prueba NO llama a la API real de Hugging Face.
- **Router**: `tests/test_ui_router.py` — `REVELACION`→`REVELATION`, `VOTACION`→`VOTING`,
  terminal obligatorio; smoke `SCREEN_MODULES` con `revelation`.
- **Harness** (verificación humana, no automatiza navegador): `AppTest` de R3-1 hasta REVELACION
  con un solo voto humano (gracias a `_complete_votes`) + manual multi-pestaña narrando:
  alias no seleccionable, duplicado bloqueado, votos registrados, revelación terminal con
  transcript `is_ai` y `prompt_version`.
- **Reglas del curso**: cero warnings (`filterwarnings=["error"]`), `ruff`/`black` limpios,
  AAA explícito, una prueba que no puede fallar no cuenta, docstrings + type hints en funciones
  públicas, funciones ≤40 líneas.

## File Change Table

| Archivo | Tipo | Cambio |
|---------|------|--------|
| `src/ui/router.py` | Modified | `Screen.REVELATION`; `REVELACION` → `REVELATION` (terminal). |
| `src/ui/api.py` | Modified | Protocol + facade `submit_vote`. |
| `src/ui/sources/fake.py` | Modified | `submit_vote` real (validaciones §8), `_complete_votes` preservado, `prompt_version:"v2"` en `_result`. |
| `src/ui/sources/http.py` | Modified | `submit_vote` → `POST /rooms/{code}/votes` (204); tolerancia en `prompt_version` (passthrough). |
| `src/ui/revelation.py` | New | Helper puro de derivación de la revelación (impostor, votos, acierto, interruption_reason, transcript `is_ai`, `prompt_version`). |
| `src/ui/screens/voting.py` | Modified | Controles reales (suspects, alias propio deshabilitado, emisión, bloqueo visual de duplicado, `votes_received`, notices). |
| `src/ui/screens/revelation.py` | New | Render de la revelación (único lugar con `is_ai`). |
| `src/ui/screens/context.py` | Modified | Callback `on_submit_vote`. |
| `src/ui/screens/__init__.py` | Modified | Exporta `render_revelation`. |
| `src/ui/app.py` | Modified | Wiring `_submit_vote` + renderer `REVELATION`. |
| `docs/CONTRATO_UI_ORQUESTADOR.md` | Modified (apply) | v1.1: fila `prompt_version` en §7.2; fila `1.1 \| 2026-09-18` en §15. |
| `tests/test_ui_router.py` | Modified | Casos `REVELACION`→`REVELATION` + terminal; `SCREEN_MODULES` con `revelation`. |
| `tests/test_ui_api.py` | Modified | `RESULT_KEYS` + `prompt_version`; tests `submit_vote` (fake + HTTP). |
| `tests/test_ui_revelation.py` | New | AAA del helper de revelación. |

Estimación de líneas autoradas: **≈420–470** → riesgo de presupuesto **Medium** (guard-lines en
tasks: un solo PR a `develop`).

## Definition of Done

- [ ] `scenario_happy_end.pw` del AppTest (y manual multi-pestaña) termina en REVELACION tras un
      voto humano real; ningún camino terminal alternativo ofrece salida sin la revelación.
- [ ] `submit_vote` contra fake y HTTP implementado y probado (204/happy, `self_vote`,
      `duplicate_vote`, `not_a_player`, `wrong_state`).
- [ ] `docs/CONTRATO_UI_ORQUESTADOR.md` en v1.1 (`prompt_version` §7.2 + fila §15).
- [ ] Revelación muestra impostor, votos/recuentos, acierto, `interruption_reason` (si aplica),
      transcript con `is_ai` (único lugar) y `prompt_version` (o texto genérico si ausente).
- [ ] ≥3 pruebas AAA nuevas en verde; suite completa sin warnings con `filterwarnings=["error"]`.
- [ ] `uv run ruff check` y `uv run black --check` limpios.
- [ ] `git status --short` sin cambios fuera del ámbito; diff sin tocar `src/orchestrator/`,
      `src/impostor_engine/` ni `src/ui/words.py`.