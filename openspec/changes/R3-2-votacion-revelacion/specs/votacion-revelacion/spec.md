# votacion-revelacion Specification

## Purpose

La capacidad `votacion-revelacion` es el incremento de R3-2 sobre `ui-flujo-partida` (R3-1,
activa, sin promover): convierte en producto lo que R3-1 reservó explícitamente — los controles
de votación (UIF-08) y la presentación del estado final `REVELACION` (UIF-06). Es una extensión
**aditiva**: no modifica, renombra ni elimina ningún requisito de R3-1 (los bloques UIF-01…UIF-12
quedan intactos); en la práctica sustituye el comportamiento reservado introduciendo controles
reales de votación y una pantalla de revelación terminal y obligatoria, construidos ÚNICAMENTE
contra el contrato `docs/CONTRATO_UI_ORQUESTADOR.md` (v1.0 más la clave aditiva `prompt_version`
de la subida a v1.1).

La UI emite el voto por la única boca `api.py` (`submit_vote`) contra `POST /rooms/{code}/votes`
(contrato §6.6): body `{"suspect": "Jugador N"}`, 204 por éxito, y los rechazos se reciben como
`ApiError` ramificado por `code` (§8: `self_vote` 400, `duplicate_vote` 409, `wrong_state` 409,
`ai_cannot_vote` 403, `not_a_player` 403, `session_expired` 401). La UI deshabilita el clic obvio
(alias propio no seleccionable) y el duplicado visualmente tras emitir, pero **la autoridad de la
votación es el orquestador** (UIF-10): un rechazo se muestra y jamás se presenta como voto
emitido. La revelación se obtiene por **fetch del estado final** en el poll (§14.4, default
aceptado): un poll devuelve `state == "REVELACION"` con `result` embebido.

`REVELACION` es un **estado de la máquina, no una bandera** (AGENTS.md): el router resuelve
`REVELACION` → una pantalla dedicada `Screen.REVELATION` (nunca cae en la pantalla de votación) y
**no existe ninguna ruta de UI que termine una partida sin pasar por la revelación**. La pantalla
de revelación muestra `impostor_alias`, `votes` + `vote_counts`, el acierto del grupo (derivado de
`scores`/`tasa_deteccion`), `interruption_reason` cuando la partida fue interrumpida, el
`transcript` con `is_ai` revelado — **el único lugar del sistema donde se muestra `is_ai`**
(contrato §9) — y la versión del prompt del impostor (`prompt_version`, aditiva v1.1; la UI la
tolera ausente con un texto genérico).

La fuente de datos por defecto sigue siendo `FakeSospechAI` (Plan B, conforme al contrato); el
fake registra el voto humano de verdad y llega a REVELACION cuando **todos** los humanos votaron
(o cuando el llenado scriptado `_complete_votes` corre en el siguiente poll), conservando el
flujo scriptado de R3-1. `HttpSospechAI` envía el voto por HTTP y tolera la ausencia de
`prompt_version` en respuestas de servidores v1.0 (compatibilidad hacia atrás).

## Requirements

### Requirement: Votación real con controles, autoridad del orquestador (UIF-13)

La pantalla de votación MUST mostrar como sospechosos seleccionables a los jugadores de la sala
(`players`, alias "Jugador N") y MUST NO permitir seleccionar el alias propio del usuario
(deshabilitado / no seleccionable): es un bloqueo visual evidente, pero la autoridad real del
rechazo reside en el orquestador (`self_vote`, 400). La UI MUST emitir el voto únicamente por el
facade `submit_vote(room_code, session_token, suspect)`, que MUST llamar a
`POST /rooms/{code}/votes` con body `{"suspect": "Jugador N"}` y considerar éxito el `204`
(contrato §6.6). La UI MUST NOT contar votos localmente: `votes_received` y el resultado decorren
exclusivamente de la instantánea del orquestador.

#### Scenario: Emisión de voto feliz

- GIVEN una partida en `VOTACION` y un humano con control en la pantalla de votación
- WHEN el humano selecciona un sospechoso distinto de su propio alias y lo envía
- THEN `submit_vote` completa con éxito (204)
- AND la instantánea siguiente muestra `votes_received` incrementado
- AND la UI permanece en la votación hasta que votan todos los humanos

#### Scenario: El alias propio no es seleccionable

- GIVEN la pantalla de votación renderizada con la lista `players`
- WHEN la UI construye las opciones de sospechoso
- THEN el alias del usuario actual NO aparece como opción activa (deshabilitado / excluido)
- AND la UI no ofrece en ningún caso votar por el propio alias (el servidor lo bloquea igual con
  `self_vote`, 400)

#### Scenario: La UI no cuenta votos localmente

- GIVEN una votación en curso con distintas instantáneas de `votes_received`
- WHEN la UI re-renderiza tras cada poll
- THEN el recuento mostrado es siempre `snapshot.votes_received` del orquestador
- AND la UI no añade, resta ni recalcula votos por su cuenta

#### Scenario: Persistencia del llenado scriptado del fake

- GIVEN el `FakeSospechAI` como fuente y una votación donde un humano ya votó de verdad
- WHEN el siguiente poll de `VOTACION` se ejecuta
- THEN el llenado scriptado `_complete_votes` completa los votos humanos restantes y llega a
  `REVELACION`
- AND el happy path scriptado de la app (AppTest) sigue terminando en REVELACION sin voto manual
  de todos los jugadores

### Requirement: Bloqueo del voto a uno mismo, UI y servidor (UIF-14)

La UI MUST NOT ofrecer el alias propio como sospechoso (escenario «El alias propio no es
seleccionable»). El servidor/orquestador MUST rechazar un intento de voto a uno mismo con
`self_vote` (400, contrato §6.6/§8). Si la fuente devuelve ese error, la UI MUST mostrarlo y
MUST NOT presentar el voto como emitido.

#### Scenario: El servidor rechaza el auto-voto

- GIVEN una partida en `VOTACION` y la fuente recibe `submit_vote(suspect == propio alias)`
- WHEN el jugador intenta votar por sí mismo
- THEN la fuente lanza `ApiError(code="self_vote", http_status=400)`
- AND el voto NO queda registrado (`votes_received` no cambia)

#### Scenario: La UI muestra el rechazo sin presentar el voto

- GIVEN un `ApiError(code="self_vote")` procedente de la fuente
- WHEN la pantalla de votación renderiza el aviso
- THEN se muestra el motivo del rechazo al usuario
- AND el voto no se presenta como emitido y `votes_received` sigue siendo el de la instantánea

### Requirement: Un solo voto humano por partida (UIF-15)

Cada humano MUST poder votar como máximo una vez al entrar a VOTACION. El servidor/orquestador
MUST rechazar un segundo voto con `duplicate_vote` (409, contrato §6.6/§8). La UI MUST bloquear
visualmente la re-emisión después de que su voto fue aceptado (un voto por jugador): tras
emitir, los controles no permiten volver a enviar y se indica que el voto quedó registrado.

#### Scenario: Segundo voto rechazado por el servidor

- GIVEN un humano que ya votó en la votación en curso
- WHEN la fuente recibe un segundo `submit_vote` del mismo humano
- THEN la fuente lanza `ApiError(code="duplicate_vote", http_status=409)`
- AND el recuento `votes_received` no cambia

#### Scenario: La UI previene el duplicado visualmente

- GIVEN un humano cuyo voto fue aceptado (204)
- WHEN la pantalla se re-renderiza
- THEN los controles de votación ya no permiten una nueva emisión (indica «voto registrado;
  esperando al resto»)
- AND si de todos modos llega un `duplicate_vote` 409, se muestra y no se presenta como emitido

### Requirement: REVELACION, estado terminal obligatorio del router (UIF-16)

El router MUST resolver `state == "REVELACION"` a una pantalla dedicada (`Screen.REVELATION`) y
MUST NOT resolverla a la pantalla de votación ni a ninguna otra. `REVELACION` es un estado de la
máquina, no una bandera ni una opción de UI: MUST NOT existir ninguna acción, botón o ruta de la
UI que termine la partida o cierre la sesión sin pasar por la pantalla de revelación. La
presentación se obtiene por fetch del estado final en el poll (§14.4): un poll devuelve
`REVELACION` con `result` embebido y eso dispara la pantalla de revelación.

#### Scenario: REVELACION resuelve a la pantalla dedicada

- GIVEN un usuario con consentimiento aceptado y un poll que devuelve `state == "REVELACION"`
- WHEN se deriva la pantalla con `resolve_screen`
- THEN el resultado es `Screen.REVELATION`
- AND el resultado NO es `VOTING`, `CHAT` ni `LOBBY`

#### Scenario: VOTACION no adelanta la revelación

- GIVEN un usuario con consentimiento aceptado y `state == "VOTACION"`
- WHEN se deriva la pantalla con `resolve_screen`
- THEN el resultado es `Screen.VOTING` (la votación, no la revelación)

#### Scenario: No existe ruta terminal alternativa

- GIVEN una partida que terminó (`REVELACION`) o cualquier pantalla posterior a la votación
- WHEN se inspecciona la UI en busca de un camino de salida alternativo
- THEN ninguna acción cierra la partida ni salta a lobby/consentimiento sin renderizar primero la
  revelación
- AND la única presentación del final es la pantalla de revelación

### Requirement: Contenido de la revelación (UIF-17)

La pantalla de revelación MUST mostrar, desde `snapshot.result` (§7.2): el alias del impostor
(`impostor_alias`); el detalle de votos (`votes`, `{voter: suspect}`) y el recuento por
sospechoso (`vote_counts`); si el grupo acertó, derivado de `scores`/`tasa_deteccion` (acierto si
la partida es válida y `tasa_deteccion > 0`; fallo si la partida es válida y `tasa_deteccion == 0`);
`interruption_reason` cuando `valid_game == false` (en lugar de la tasa de detección); el
`transcript` completo con `is_ai` revelado — el único lugar donde la UI puede dibujar `is_ai`
(contrato §9) — y `prompt_version` (véase UIF-18). La pantalla MUST NOT derivar datos que el
orquestador no publicó: solo formatea lo que viene en `result()`.

#### Scenario: Revelación completa de partida válida

- GIVEN `state == "REVELACION"` con `result` de partida válida (`valid_game == true`)
- WHEN la pantalla de revelación renderiza
- THEN se muestra `impostor_alias`, los `votes` de cada jugador con sus `vote_counts`
- AND se indica el acierto del grupo según `tasa_deteccion`
- AND el `transcript` se lista marcando qué alias era `is_ai`
- AND se muestra `prompt_version` del prompt del impostor

#### Scenario: Partida interrumpida

- GIVEN `state == "REVELACION"` con `result` de partida interrumpida (`valid_game == false`,
  `tasa_deteccion == null`, `interruption_reason` con código)
- WHEN la pantalla de revelación renderiza
- THEN se muestra el motivo de interrupción
- AND no se muestra una tasa de detección ni un veredicto de acierto inventado

#### Scenario: is_ai solo aparece en revelación

- GIVEN una sesión en cualquier estado anterior a `REVELACION`
- WHEN se renderiza cualquier pantalla (lobby, chat, votación)
- THEN ningún marcador `is_ai` aparece (ni etiqueta de IA ni énfasis de posición, §14.3)
- AND `is_ai` solo se dibuja dentro de la pantalla de revelación

### Requirement: prompt_version, clave aditiva v1.1 (UIF-18)

`result()` MAY incluir la clave aditiva `prompt_version` (string | null, default `"v2"`, contrato
§7.2 en v1.1). El `FakeSospechAI` MUST emitirla (`"v2"`). La pantalla de revelación MUST
mostrarla cuando está presente (SHOULD en el orden de presentación: junto al impostor, como
transparencia del prompt del modelo). La fuente HTTP SHOULD tolerar su ausencia (respuesta de un
servidor v1.0): MUST NOT fallar ni transformar `result()` por la falta de la clave, y MUST
transportarla tal cual cuando está presente.

#### Scenario: prompt_version presente en el fake

- GIVEN `FakeSospechAI` como fuente y una partida en `REVELACION`
- WHEN se obtiene `result()` en la instantánea
- THEN `result["prompt_version"] == "v2"`
- AND la pantalla de revelación muestra la versión del prompt del impostor

#### Scenario: prompt_version ausente tolerado por HTTP

- GIVEN un servidor v1.0 (o local de integración) cuyo `result()` NO incluye `prompt_version`
- WHEN `HttpSospechAI.get_state` devuelve la instantánea de `REVELACION`
- THEN la llamada no falla y `result` se transporta sin modificaciones
- AND la pantalla de revelación muestra un texto genérico equivalente en lugar de la versión
  (SHOULD de compatibilidad hacia atrás)

### Requirement: Calidad del incremento y pruebas nuevas (UIF-19)

El código nuevo MUST pasar la suite con warnings tratados como error (`filterwarnings =
["error"]`), MUST ser compatible con `uv run ruff check` y `uv run black --check`, y MUST contar
con al menos 3 pruebas nuevas de estructura Arrange-Act-Assert que cubran (a) la validación de
mensajes/votos (`submit_vote`, `self_vote`, `duplicate_vote`, `not_a_player`) y (b) la transición
a `REVELACION` (router) y el contenido de la revelación.

#### Scenario: Al menos tres pruebas AAA nuevas en verde

- GIVEN las 3+ pruebas nuevas de la capacidad (validación de votos + transición a REVELACION +
  contenido de revelación)
- WHEN se ejecuta `uv run pytest`
- THEN todas pasan

#### Scenario: Cero warnings

- GIVEN la suite configurada con `filterwarnings = ["error"]`
- WHEN se ejecuta `uv run pytest`
- THEN la suite termina sin emitir ningún warning

#### Scenario: Estilo limpio

- GIVEN el código nuevo del incremento
- WHEN se ejecuta `uv run ruff check` y `uv run black --check`
- THEN no se reportan hallazgos en el código nuevo