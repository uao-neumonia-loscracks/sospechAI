# Contrato UI–Orquestador — sospechAI

**Versión**: 1.0 · **Fecha**: 2026-09-16 · **Estado**: CONGELADO para R2 (cambios exclusivamente aditivos; ver §14)

**Ticket**: R2-1 / A9 — "Contrato UI-orquestador y servidor multijugador"

Este documento es la única fuente de verdad de la interfaz entre el rol UI (R3) y el orquestador. La UI se construye ÚNICAMENTE contra este contrato y habla ÚNICAMENTE con el orquestador (nunca con el motor ni con el dominio `game.py`). Las respuestas de estado son un espejo literal de `public_state()`/`result()` del dominio: el dominio sigue siendo la única fuente de verdad de los datos; el servidor no remodela nada.

---

## 1. Alcance

**Dentro del alcance**

- Transporte HTTP/1.1 + JSON por polling (§3).
- Modelo de identidad por token de sesión opaco (§4).
- Ciclo de vida de sala y evento de cierre (§5).
- Máquina de estados y valores de cable congelados (§6).
- 7 endpoints (§7) y formas de respuesta espejo de `public_state()`/`result()` (§8).
- Catálogo estable de códigos de error (§9).
- Garantías de privacidad (§10), reconexión (§11), turno de la IA (§12) y temporizadores (§13).
- Camino de actualización aditivo (WebSocket/gRPC) (§14).

**Fuera del alcance (explícitamente NO resuelto aquí)**

- Persistencia activa / recuperación de partidas (ticket A8).
- Plazos (deadlines) para DISCUSION/VOTACION (ADR-003 pendiente): VOTACION espera a todos los humanos; sin cuenta atrás.
- El cliente UI en sí (entregable de R3; `src/ui/` no existe).
- Cualquier dependencia Python nueva (runtime: grpcio, protobuf, python-dotenv únicamente).
- Cambios en `src/orchestrator/game.py` (dominio reutilizado SIN cambios) ni `src/orchestrator/storage.py`.
- Cambios de transporte que rompan HTTP+JSON (WebSocket/gRPC solo aditivos).

---

## 2. Transporte y formato

- **Protocolo**: HTTP/1.1, JSON (`Content-Type: application/json` en peticiones y respuestas).
- **Modelo**: *polling* de instantáneas. La UI obtiene el estado con `GET /rooms/{room_code}/state`; las mutaciones devuelven respuestas mínimas (204) y el estado nuevo se refleja en el siguiente poll. No hay push en R2.
- **Coste**: el polling es barato para ventanas de 20 s (una petición por tick recomendada, ver §15.1).
- **Rutas**: siempre bajo `/rooms`; el código de sala va en la ruta; el token de sesión va en la cabecera `X-Session-Token` (§4).
- **Peticiones con cuerpo**: las mutaciones con cuerpo (`messages`, `votes`) requieren JSON válido. JSON malformado → `malformed_request` (400).
- Los valores booleanos/nulos siguen JSON estándar. No hay cabeceras de versión: la versión del contrato se fija en este documento.

---

## 3. Modelo de identidad y sesión

- Cada jugador humano recibe un **token de sesión opaco** emitido por el servidor en el momento de unirse (crear sala o unirse a sala). El token es una cadena opaca generada por el servidor; la UI lo conserva y lo envía en cada petición.
- El token está ligado **1:1 al alias** que el servidor asigna automáticamente: `"Jugador N"` (N = orden de inserción). **El alias nunca lo elige el cliente; no se acepta un alias propuesto por el cliente** (cualquier intento se ignora o se rechaza).
- **Código de sala** (`room_code`): cadena opaca corta generada por el servidor en la creación (alfanumérica, mayúsculas; el servidor normaliza a mayúsculas, entrada insensible a mayúsculas). Agrupa a los jugadores de una partida.
- **Anfitrión (host)**: el creador de la sala. Solo el anfitrión puede ejecutar `start` y `open_voting` (§7). La condición de anfitrión se verifica contra el token en cada petición; el cliente no declara su rol.
- **Vigencia del token**: válido durante toda la vida de la sala (§5). No expira por inactividad dentro de la vida de la sala.
- La **IA no tiene token ni sesión**: es un jugador gestionado por el servidor (§12).

---

## 4. Ciclo de vida de la sala y evento de cierre

```
POST /rooms  →  sala creada (LOBBY, anfitrión = "Jugador 1")
                humanos se unen mientras LOBBY
                anfitrión: start  →  el servidor registra a la IA (siempre en último
                lugar del orden "Jugador N") y arranca RONDA(ronda 1)
RONDA ⇄ RONDA(n+1) → DISCUSION → VOTACION → REVELACION (terminal)
```

- **Creación**: `POST /rooms` crea la sala y une al creador como anfitrión ("Jugador 1"). No hay sala sin creador.
- **Unión**: `POST /rooms/{room_code}/join` solo en LOBBY. Fuera de LOBBY → `wrong_state` (409).
- **Capacidad**: la define la regla de juego: `start()` requiere **≥ 2 humanos y exactamente 1 IA**. No hay tope máximo documentado mientras la sala esté en LOBBY.
- **Cierre**: la sala es **terminal tras REVELACION** (fin de partida; `interrupt` incluido). El evento de cierre se refleja en la instantánea de estado: la UI detecta `state == "REVELACION"` en un poll. Su superficie de presentación es la **Decisión pendiente R3-4** (§15.4). El estado final (con `result` embebido) **permanece consultable mientras el proceso del servidor esté vivo**.
- **Limpieza de memoria**: detalle de implementación del servidor (proceso vivo); no visible al contrato.

---

## 5. Máquina de estados y valores de cable congelados

Los valores de `state` en el cable son **cadenas fijas y CONGELADOS para R2**. No cambiarán; los tests del servidor los verifican exactos.

| `state` (valor de cable) | Significado | Estado terminal |
|---|---|---|
| `"LOBBY"` | Sala creada; unión de humanos; antes de `start` | no |
| `"RONDA"` | Ronda de mensajes; `round_number` distingue rondas (RONDA(n+1)); ventana de 20 s | no |
| `"DISCUSION"` | Debate previo a votación | no |
| `"VOTACION"` | Votación; espera a todos los humanos (sin plazo) | no |
| `"REVELACION"` | Fin de partida; `result` embebido en la instantánea | sí |

- **Nombres de estados**: `LOBBY` (inglés, por dominio) y cuatro valores en español congelados: `RONDA`, `DISCUSION`, `VOTACION`, `REVELACION`. **Estos cuatro valores en español no se traducen ni cambian.**
- **Transiciones**: LOBBY → RONDA (`start`); RONDA(n) → RONDA(n+1) (último mensaje de la ronda); tras la ronda final → DISCUSION; DISCUSION → VOTACION (`open_voting`); VOTACION → REVELACION (último voto humano, o interrupción). Camino de interrupción: {RONDA, DISCUSION, VOTACION} → REVELACION.
- **Razones de interrupción** (aparecen como `interruption_reason` en `result()`, **no** son códigos de error HTTP): `round_timeout` | `engine_timeout` | `engine_unavailable` | `engine_protocol` | `engine_rejected` | `invalid_engine_response`.

---

## 6. Endpoints

Cabecera común: `X-Session-Token: <token opaco>` en **todos** los endpoints salvo `POST /rooms` y `POST /rooms/{room_code}/join` (que emiten token). Ausencia/validez fallida → `session_expired` (401) o `not_a_player` (403).

| # | Método | Ruta | Autenticación | Cuerpo petición | Respuesta éxito | Acción de dominio |
|---|---|---|---|---|---|---|
| 1 | `POST` | `/rooms` | — | — | `201` + §§6.1 | crear sala + unir anfitrión |
| 2 | `POST` | `/rooms/{room_code}/join` | — | — | `201` + §§6.2 | `add_player(is_ai=False)` (humano) |
| 3 | `POST` | `/rooms/{room_code}/start` | host | — | `204` | registrar IA + `start()` |
| 4 | `POST` | `/rooms/{room_code}/messages` | jugador | `{"text": "..."}` | `204` | `submit_message(alias, text, ronda_actual)` |
| 5 | `POST` | `/rooms/{room_code}/voting/open` | host | — | `204` | `open_voting()` |
| 6 | `POST` | `/rooms/{room_code}/votes` | jugador | `{"suspect": "Jugador N"}` | `204` | `cast_vote(voter, suspect)` |
| 7 | `GET` | `/rooms/{room_code}/state` | jugador | — | `200` + §8 (espejo de `public_state()`) | `public_state()` |

Reglas de enrutado: ruta desconocida → `not_found` (404); verbo no soportado en la ruta → `method_not_allowed` (405); cuerpo inválido donde se exige → `malformed_request` (400). El servidor enlaza `alias` y `round` desde el token y el estado actual: **el cliente nunca envía `alias` ni `expected_round`** (se ignoran si se envían).

### 6.1 `POST /rooms` — crear sala (anfitrión)

Petición: sin cuerpo.

Respuesta `201 Created`:

```json
{
  "room_code": "K7Q2P",
  "session_token": "s3_Gk9x…cifrado-opaco…",
  "alias": "Jugador 1"
}
```

Errores: `internal` (500) si el servidor no puede crear la sala.

### 6.2 `POST /rooms/{room_code}/join` — unirse a sala

Petición: sin cuerpo.

Respuesta `201 Created`:

```json
{
  "session_token": "s3_Wm4y…cifrado-opaco…",
  "alias": "Jugador 2"
}
```

Errores: `room_not_found` (404), `wrong_state` (409, sala fuera de LOBBY).

### 6.3 `POST /rooms/{room_code}/start` — iniciar partida (solo anfitrión)

Petición: sin cuerpo. El servidor registra a la IA (último "Jugador N") y ejecuta `start()` bajo el mismo bloqueo.

Respuesta `204 No Content`.

Errores: `session_expired` (401), `not_a_player` (403), `forbidden_host_action` (403, no anfitrión), `wrong_state` (409, no LOBBY), `invalid_roster` (409, menos de 2 humanos en la sala).

### 6.4 `POST /rooms/{room_code}/messages` — enviar mensaje de ronda

Petición:

```json
{
  "text": "Yo creo que el impostor es el Jugador 3."
}
```

El servidor asocia `alias` desde el token y `round_number` desde el estado actual. El texto pasa por el mismo normalizador del dominio (NFC + espacios) y las mismas reglas: no vacío, ≤ `max_words` (default 15), un mensaje por jugador y ronda.

Respuesta `204 No Content`.

Errores: `session_expired` (401), `not_a_player` (403), `wrong_state` (409, no RONDA), `empty_message` (400), `too_many_words` (400), `duplicate_message` (409).

### 6.5 `POST /rooms/{room_code}/voting/open` — abrir votación (solo anfitrión)

Petición: sin cuerpo.

Respuesta `204 No Content`.

Errores: `session_expired` (401), `not_a_player` (403), `forbidden_host_action` (403), `wrong_state` (409, no DISCUSION).

### 6.6 `POST /rooms/{room_code}/votes` — emitir voto

Petición:

```json
{
  "suspect": "Jugador 3"
}
```

El votante se asocia desde el token. El voto dispara el revelado automático cuando **todos los humanos** han votado; nadie puede votar dos veces; la IA no vota; no se permite el voto a uno mismo.

Respuesta `204 No Content`.

Errores: `session_expired` (401), `not_a_player` (403, token o `suspect` no son jugadores de la sala), `wrong_state` (409, no VOTACION), `self_vote` (400), `duplicate_vote` (409), `ai_cannot_vote` (403).

### 6.7 `GET /rooms/{room_code}/state` — instantánea de estado

Petición: sin cuerpo. Cabecera `X-Session-Token` requerida.

Respuesta `200 OK`: **cuerpo literal de `public_state()`** (§8), sin envoltorio y sin claves añadidas.

Errores: `session_expired` (401), `not_a_player` (403), `room_not_found` (404).

---

## 7. Formas de respuesta (espejo de `public_state()` / `result()`)

**Regla de oro**: toda respuesta de estado es el cuerpo de `public_state()` **literal, sin remodelado**; el servidor no añade, renombra ni elimina claves. En REVELACION, `public_state()` incluye `result` embebido, con el cuerpo literal de `result()`. La versión del dominio es la única fuente de verdad de los datos.

### 7.1 `public_state()` — claves (presentes siempre que apliquen)

| Clave | Tipo | Contenido |
|---|---|---|
| `state` | string | Valor congelado (§5) |
| `round_number` | number \| null | Ronda actual; fuera de RONDA según dominio |
| `rounds` | number | Total de rondas configurado |
| `max_words` | number | Límite de palabras por mensaje (default 15) |
| `players` | string[] | **Solo alias** ("Jugador N"), incluyendo a la IA |
| `messages` | object[] | `{round_number, alias, text}` |
| `votes_received` | number | **Solo recuento** (nunca el detalle de votos) |
| `remaining_seconds` | number \| null | Segundos restantes de la ventana de RONDA |
| `result` | object \| null | **Solo en REVELACION**; cuerpo de `result()` (§7.2) |

Ejemplo (RONDA, ronda 1):

```json
{
  "state": "RONDA",
  "round_number": 1,
  "rounds": 3,
  "max_words": 15,
  "players": ["Jugador 1", "Jugador 2", "Jugador 3"],
  "messages": [
    { "round_number": 1, "alias": "Jugador 1", "text": "Hola a todos." }
  ],
  "votes_received": 0,
  "remaining_seconds": 17.4,
  "result": null
}
```

### 7.2 `result()` — claves (solo embebido en REVELACION)

| Clave | Tipo | Contenido |
|---|---|---|
| `state` | string | `"REVELACION"` |
| `impostor_alias` | string | Alias de la IA revelado aquí |
| `rounds` | number | Total de rondas |
| `max_words` | number | Límite de palabras |
| `votes` | object | `{voter: suspect}` — detalle de votos, solo aquí |
| `vote_counts` | object | Recuento por sospechoso |
| `scores` | object | `{alias: 0\|1}`; `{}` si partida interrumpida |
| `valid_game` | boolean | `false` si interrumpida |
| `interruption_reason` | string \| null | Código de interrupción o `null` |
| `tasa_deteccion` | float \| null | `null` si interrumpida |
| `prompt_version` | string \| null | Versión del prompt del impostor; default "v2" |
| `transcript` | object[] | `{round_number, alias, text, is_ai}` — **el único lugar donde se revela `is_ai`** |

Ejemplo (REVELACION, partida válida):

```json
{
  "state": "REVELACION",
  "round_number": 3,
  "rounds": 3,
  "max_words": 15,
  "players": ["Jugador 1", "Jugador 2", "Jugador 3"],
  "messages": [
    { "round_number": 3, "alias": "Jugador 1", "text": "Voto a Jugador 3." }
  ],
  "votes_received": 2,
  "remaining_seconds": null,
  "result": {
    "state": "REVELACION",
    "impostor_alias": "Jugador 3",
    "rounds": 3,
    "max_words": 15,
    "votes": { "Jugador 1": "Jugador 3", "Jugador 2": "Jugador 3" },
    "vote_counts": { "Jugador 3": 2 },
    "scores": { "Jugador 1": 1, "Jugador 2": 1 },
    "valid_game": true,
    "interruption_reason": null,
    "tasa_deteccion": 1.0,
    "transcript": [
      { "round_number": 1, "alias": "Jugador 1", "text": "Hola a todos.", "is_ai": false },
      { "round_number": 1, "alias": "Jugador 2", "text": "Hola.", "is_ai": false },
      { "round_number": 1, "alias": "Jugador 3", "text": "Saludos.", "is_ai": true }
    ]
  }
}
```

> Los valores numéricos de los ejemplos son ilustrativos; **las claves y formas son normativas**. El servidor nunca deriva ni recalcula: serializa la instantánea del dominio.

---

## 8. Catálogo de códigos de error

Formato de error (siempre que el estado HTTP no sea 2xx):

```json
{
  "code": "wrong_state",
  "message": "Operación no válida en el estado actual de la partida"
}
```

- `code`: estándar, **estable y congelado** — el cliente ramifica por `code`, **nunca por `message`**.
- `message`: texto humano legible; conserva el mensaje español del dominio (`RuleViolation`) cuando el error proviene de una regla de negocio, o un texto de transporte en caso contrario.

| `code` | HTTP | Condición |
|---|---|---|
| `malformed_request` | 400 | JSON inválido / cuerpo ausente donde se exige |
| `empty_message` | 400 | Texto vacío tras normalización |
| `too_many_words` | 400 | Supera `max_words` |
| `self_vote` | 400 | Voto a uno mismo |
| `session_expired` | 401 | Token ausente, desconocido o de sala reclamada |
| `not_a_player` | 403 | Token válido pero no ligado a un jugador de la sala; o `suspect`/alias referenciado no es jugador |
| `ai_cannot_vote` | 403 | La IA no vota |
| `forbidden_host_action` | 403 | Acción solo de anfitrión ejecutada por no-anfitrión |
| `room_not_found` | 404 | Sala inexistente |
| `not_found` | 404 | Ruta desconocida |
| `method_not_allowed` | 405 | Verbo no soportado en la ruta |
| `wrong_state` | 409 | Operación no válida en el estado actual |
| `duplicate_message` | 409 | Segundo mensaje del mismo jugador en la misma ronda |
| `duplicate_vote` | 409 | Segundo voto del mismo humano |
| `invalid_roster` | 409 | `start` con menos de 2 humanos en la sala |
| `internal` | 500 | Error inesperado del servidor |

**Aclaración**: los códigos de interrupción (`round_timeout`, `engine_timeout`, `engine_unavailable`, `engine_protocol`, `engine_rejected`, `invalid_engine_response`) **no** son códigos de error HTTP: se transportan como `interruption_reason` dentro del `result` de REVELACION (§7.2).

---

## 9. Garantías de privacidad

El contrato garantiza que, **antes de REVELACION**, ninguna respuesta expone información oculta de la partida:

- **`public_state()` nunca incluye `is_ai`, el detalle de `votes`, ni `impostor_alias`** antes de REVELACION. `votes_received` es solo un recuento.
- **`is_ai` se revela únicamente** en `result().transcript` (solo REVELACION).
- **`impostor_alias`, `votes`, `vote_counts`, `scores`, `tasa_deteccion`** se revelan únicamente en `result()` (solo REVELACION).
- El servidor **no expone ninguna ruta, cabecera ni campo de depuración** que revele estas claves antes de tiempo; sirve `public_state()` sin remodelar, con la privacidad heredada del dominio.
- La instantánea es una **copia defensiva**: mutaciones posteriores del dominio no alteran una respuesta ya serializada.

La UI **debe** tratarlas como secretas: no dibujar `is_ai`/impostor antes de REVELACION y no deducir el impostor por posiciones destacadas de la lista (ver Decisión pendiente R3-3, §15.3).

---

## 10. Política de reconexión y desconexión

- **Vigencia del token**: durante toda la vida de la sala (§3). Sin expiración por inactividad.
- **Reconexión a mitad de partida**: el jugador con su token hace `GET /rooms/{room_code}/state` y vuelve a leer la instantánea actual (ronda, mensajes, recuento de votos). No hay handshake especial.
- **Desconexión de un humano**: NO bloquea la partida; la ronda continúa. Si la ventana de RONDA expira sin su mensaje, el temporizador del servidor dispara `check_expiration()` → `round_timeout` → REVELACION (auto-avance, §13).
- **Sin "marcar y continuar"** (mark-and-continue): requeriría cambio de dominio; diferido salvo que R3 lo exija.
- **Reunirse tras el cierre**: el estado final (REVELACION) sigue consultable mientras el proceso viva (§4); el token sigue siendo válido para leerlo.

---

## 11. Turno de la IA

- **Quién añade a la IA**: solo el servidor. En el arranque de la partida (`start`), el servidor registra exactamente un jugador IA en el **último lugar** del orden "Jugador N" (N = humanos + 1) y ejecuta `start()` a continuación, bajo el mismo bloqueo de escritor único (§13). Los clientes no pueden añadir jugadores IA.
- **Cuándo se dispara el turno**: cuando **todos los humanos han enviado su mensaje de la ronda** (detección en el bucle del servidor sobre la última presentación).
- **Presupuesto**: `min(8 s, tiempo restante de la ventana de 20 s)` de la ronda.
- **Ejecución**: `apply_ai_turn` = validar turno → presupuesto → **UN único intento RPC**; sin reintentos (fallo → `interruption_reason` según código: `engine_timeout`, `engine_unavailable`, `engine_protocol`, `engine_rejected`, `invalid_engine_response`). El texto de la IA pasa por el **mismo** validador `submit_message` (normalización, no vacío, ≤ `max_words`).
- **La IA nunca vota**: un intento de voto de la IA es imposible (no hay token) y el dominio lo rechaza (`ai_cannot_vote`).
- **Orden de alias**: la IA es siempre el último "Jugador N". Esta política está documentada para mitigar la pista de impostor; la presentación en la UI es la Decisión pendiente R3-3 (§15.3).

---

## 12. Temporizadores y avance automático

- **Propietario del temporizador: el servidor.** Un temporizador del propio servidor llama a `check_expiration()` de forma periódica, **incluso con cero consultas de clientes**; la expiración no depende de que la UI haga polling.
- **RONDA** es el único estado con ventana (20 s por defecto, `remaining_seconds` visible en la instantánea). Al expirar sin completarse: `check_expiration()` → interrupción `round_timeout` → REVELACION automática.
- **VOTACION no tiene plazo** (ADR-003 pendiente): espera a que **todos los humanos** voten; el último voto humano dispara el revelado automático en el dominio.
- **Auto-revelado anunciado en la instantánea**: tras la expiración o el último voto, el siguiente `GET /state` devuelve REVELACION con `result` embebido; no hay evento push.
- **Serialización**: todas las mutaciones sobre la partida pasan por un **bloqueo de escritor único** en el servidor (el dominio permanece sin bloqueos); esto garantiza que el revelado por último voto **nunca se dispara dos veces**.

---

## 13. Camino de actualización (aditivo)

HTTP+JSON es el transporte canónico de R2 y **no se retirará**. Mejoras futuras son **aditivas** y nunca rompen el contrato v1.0:

- **WebSocket (futuro)**: un endpoint adicional (p. ej. `/rooms/{room_code}/ws`) empujando las mismas formas JSON de §7 y usando el mismo token de sesión; HTTP+JSON permanece.
- **gRPC (futuro)**: un servicio nuevo (proto nuevo) con los mismos valores de cable y semántica; requiere grpc-web/proxy para navegadores; HTTP+JSON permanece.
- **Claves/códigos/endpoints nuevos**: solo se añaden con subida de versión menor en este documento; añadir nunca elimina ni renombra.
- Cualquier cambio de valores congelados (§5) o del catálogo (§8) exige nueva versión del contrato y notificación a la UI antes de apply.

---

## 14. Decisiones pendientes del rol UI (R3)

Estos cuatro puntos **no se resuelven en este contrato**; quedan asignados al rol UI (R3) para su visto bueno. Cada uno incluye una **recomendación por defecto** para que R2 no se bloquee; el contrato ya es utilizable tal cual.

### 14.1 Ajuste del modelo de refresco por polling
**⚠️ Decisión requerida de R3.** *¿El polling encaja con el modelo de refresco de la UI?*
**Por defecto recomendado**: poll a `GET /rooms/{room_code}/state` cada **1 s** durante RONDA / DISCUSION / VOTACION (ventana de 20 s; coste trivial), y cada **2–3 s** en LOBBY y REVELACION (estados sin temporizador). La UI puede degradar o acelerar libremente; ninguna semántica del contrato depende de la frecuencia de poll.

### 14.2 Overlay de nombre visible elegido por el cliente
**⚠️ Decisión requerida de R3.** *¿Permitir un nombre visible elegido por el cliente?*
**Por defecto recomendado**: **NO** en R2. El alias `"Jugador N"` es obligatorio y nunca lo elige el cliente (§3). Un overlay de sobrenombre local (solo en el cliente, sin enviarlo al servidor) es posible sin cambio de contrato; un overlay con almacenamiento servidor tiene implicaciones de persistencia y se difiere a una versión aditiva.

### 14.3 Display del jugador IA en el lobby
**⚠️ Decisión requerida de R3.** *¿Cómo se muestra el jugador IA dado que su alias es siempre el último "Jugador N" (pista potencial de impostor)?*
**Por defecto recomendado**: **anónimo e idéntico** — el alias de la IA se muestra como cualquier otro "Jugador N", sin etiqueta "IA" ni énfasis visual de posición. **La UI no debe etiquetar a la IA** (revelaría al impostor y rompería el juego). En R2 el lobby previo a `start` lista solo humanos; la IA aparece en `players` desde RONDA como último alias. Un reordenamiento (shuffle) sería un cambio de dominio, fuera de alcance de R2.

### 14.4 Superficie del evento de cierre
**⚠️ Decisión requerida de R3.** *¿Cómo se presenta el cierre: fetch del estado final o bandera explícita de evento?*
**Por defecto recomendado**: **fetch del estado final** — la UI detecta `state == "REVELACION"` en un poll y presenta el final; `result` ya viene embebido en la misma instantánea (cero latencia). Una bandera explícita de evento/cierre sería una clave nueva y **aditiva** (v1.1+ si R3 la exige); no se añade en v1.0.

---

## 15. Registro de versiones

| Versión | Fecha | Cambio |
|---|---|---|
| 1.0 | 2026-09-16 | Congelación inicial para R2 (R2-1 / A9). |
| 1.1 | 2026-09-18 | Clave aditiva prompt_version en result() para transparencia del prompt del impostor (R3-2) |