# Design: R3-1 — Flujo de partida en la UI (consentimiento, lobby, sala de chat, votación)

**Cambio**: `R3-1-ui-flujo-partida`
**Especificación**: capacidad `ui-flujo-partida`, requisitos UIF-01…UIF-12
**Contrato**: `docs/CONTRATO_UI_ORQUESTADOR.md` v1.0 (única fuente de verdad de la interfaz)
**Entrada**: `openspec/changes/R3-1-ui-flujo-partida/specs/ui-flujo-partida/spec.md`

## Technical Approach

La UI (`src/ui/`) es una capa nueva y **aditiva**: nunca importa `src/orchestrator/` ni
`src/impostor_engine/`; se comunica únicamente por HTTP+JSON contra el contrato a través de
una sola boca (`api.py`). El orquestador no se modifica. La entrega sigue las dos fases de la
propuesta:

1. **Fase 1 — Esqueleto navegable**: `src/ui/app.py` con router por `session_state`
   (prohibidos `st.navigation` y `pages/`) y cuatro pantallas como funciones finas de
   presentación en `src/ui/screens/` (`consent.py`, `lobby.py`, `chat.py`, `voting.py`).
   La lógica pura que decide la pantalla vive separada (`src/ui/router.py`) y es testeable
   sin Streamlit.
2. **Fase 2 — Contenido**: cada pantalla muestra y envía contra `src/ui/api.py`, la única
   boca con el orquestador. `api.py` expone un facade público y dos fuentes de datos detrás
   de la misma interfaz (`SospechAI` Protocol): `FakeSospechAI` in-memory (Plan B hasta que
   exista el servidor HTTP de R2) y `HttpSospechAI` con stdlib `urllib`. El polling corre en
   un fragment no bloqueante con frecuencias por estado (UIF-06). El contador de palabras es
   una estimación local en vivo que **bloquea el envío** al superar `max_words`; la autoridad
   del límite reside en el orquestador (`too_many_words`, 400) y la UI no presenta nunca un
   mensaje rechazado como entregado (UIF-04, UIF-05).

La máquina de estados y los valores de cable se toman literalmente del contrato §5–§8:
`LOBBY → RONDA → DISCUSION → VOTACION → REVELACION` y las claves exactas de
`public_state()`/`result()`. R3-2 cubre votación y revelación con contenido; en R3-1 la vista
de votación existe solo como navegación y el estado `REVELACION` se detecta como cierre sin
renderizar el cuerpo de `result` (UIF-06, UIF-08).

## Architecture Decisions

### Decision: Router por `session_state` (sin `st.navigation` ni `pages/`)

**Choice**: `src/ui/app.py` es el único archivo de arranque. La pantalla activa se deriva con
la función pura `router.resolve_screen(consent_agreed, state)`, y los datos de sesión viven
en `st.session_state` bajo tres claves: `consent_accepted` (bool), `room_identity`
(`RoomIdentity | None`) y `snapshot` (`StateSnapshot | None`). No existe ruta de URL para
ninguna pantalla posterior al consentimiento.

**Alternatives considered**:
- `st.navigation` + carpeta `pages/`: ruteo declarativo por URL por archivo; Streamlit permite
  acceder a cualquier página por URL, lo que permitiría saltar el consentimiento.
- Router basado en la URL (query params de Streamlit).
- Cabecera única con un `if/elif` sobre `st.session_state` dentro de `chat.py`/`lobby.py`.

**Rationale**: UIF-09 obliga a derivar la pantalla de `session_state` y prohíbe
`st.navigation`/`pages/`; UIF-02 obliga a que el consentimiento no se pueda saltar por URL.
Con `session_state` no hay superficie de ruteo por URL que eludir: cada sesión de navegador
(nueva pestaña) re-arranca desde el consentimiento. Deriva directamente del requisito UIF-09
(escenario «Router por session_state»), no de una preferencia de estilo.

### Decision: Pantallas como funciones finas de presentación + lógica pura separada

**Choice**: cada pantalla es un módulo `src/ui/screens/*.py` que expone `render(ctx)` — una
función de presentación que recibe sus datos como argumentos (contexto con identidad,
instantánea y callbacks) y no contiene reglas de juego. La lógica computable vive en dos
módulos puros: `src/ui/router.py` (derivación de pantalla y frecuencia de polling) y
`src/ui/words.py` (conteo de palabras). `app.py` es la raíz de composición: dueño de
`session_state`, decide la pantalla con `resolve_screen`, declara el fragment de polling y
conecta los callbacks de las pantallas con el facade de `api.py`.

**Alternatives considered**:
- Clases de página con estado propio (estilo «page object») dentro de cada módulo.
- Todo el render en un solo `app.py` grande.
- Pantallas como funciones que importan `st` y leen `st.session_state` directamente.

**Rationale**: UIF-11 exige pruebas AAA sobre contador y transición sin levantar Streamlit;
separar la lógica pura de la presentación hace esas pruebas triviales con pytest estándar.
Cumple la regla de AGENTS «un módulo, una responsabilidad» y mantiene cada pantalla en
~30–40 líneas (si una supera 40, se justifica por escrito como datos fijos de texto, p. ej.
los dos avisos de consentimiento). Las pantallas reciben datos por parámetro, por lo que el
cambio de fuente de datos (UIF-07) y las pruebas con dobles no requieren tocar el render.

### Decision: `api.py` como única boca; doble fuente (fake/HTTP) con swap localizado

**Choice**: `src/ui/api.py` es la única superficie pública que las pantallas conocen. Expone
funciones de módulo (`create_room`, `join_room`, `start`, `open_voting`, `submit_message`,
`get_state`) implementadas por un `SospechAI` Protocol interno. Hay dos implementaciones del
Protocol en un subpaquete interno `src/ui/sources/`:
- `FakeSospechAI` (`sources/fake.py`): fuente in-memory conforme al contrato (máquina de
  estados congelada, formas de `public_state()`/`result()`, catálogo de códigos de error §8).
- `HttpSospechAI` (`sources/http.py`): cliente HTTP con stdlib `urllib` que serializa cabecera
  `X-Session-Token`, cuerpos JSON y traduce respuestas 2xx/errores a `ApiError`.

El selector es una única función privada `_source() -> SospechAI` que lee la variable de
entorno `SOSPECHAI_UI_SOURCE` (`fake` por defecto; `http` cuando existe el servidor de R2,
con la base URL en `SOSPECHAI_ORCHESTRATOR_URL`). **El swap fake→HTTP es cambiar una
configuración de fuente en `api.py`; las pantallas no cambian** (UIF-07, escenario «El swap
a HTTP real no toca las pantallas»).

**Alternatives considered**:
- Los `screens/*` llaman a `urllib` o a requests directamente: viola «una boca» (UIF-07) y
  rompería el swap.
- Un fake que importa `src.orchestrator.game.Game`: prohibido por AGENTS (`src/ui/` nunca
  importa de `src/orchestrator/`) y por UIF-10.
- Dependencia `requests` o `httpx`: dependencia extra fuera del alcance (UIF-12).
- Mantener fake y cliente HTTP en el mismo archivo `api.py` (literal de la propuesta): dos o
  tres responsabilidades en un módulo (Protocol + facade + fake + HTTP); se refina con un
  subpaquete `sources/` conservando la boca pública `api.py` idéntica.

**Rationale**: UIF-10 exige que la UI hable solo con el orquestador por HTTP+JSON y que no
exista acceso directo a `src/orchestrator/` ni a `src/impostor_engine/`; `api.py` garantiza
un único punto de contacto. `urllib` es stdlib (UIF-12: ninguna dependencia nueva más allá de
`streamlit`). El Protocol `SospechAI` hace intercambiables las fuentes sin cambios en el
render (UIF-07) y permite probar `api.py` con un doble (las pruebas nunca llaman a la API
real de Hugging Face). Los errores se ramifican por `code`, nunca por `message` (contrato §8).

### Decision: Polling no bloqueante con `st.fragment` y frecuencias por estado

**Choice**: el ciclo de polling se aloja en un único fragment de Streamlit,
`st.fragment(run_every=poll_interval_seconds(state))`, envuelto en un wrapper local dentro de
`app.py` para aislar la API de Streamlit. Cada tick: `api.get_state(room_code, token)` (con
cabecera `X-Session-Token`), guarda la instantánea en `session_state["snapshot"]`, recalcula
`resolve_screen` y, si la ruta cambió, dispara `st.rerun(scope="app")`; si no, re-renderiza
las partes dependientes de la instantánea (mensajes, contador) en su lugar. Frecuencias
(UIF-06 / contrato §14.1): **1 s** en `RONDA`, `DISCUSION`, `VOTACION`; **2–3 s** (se adopta
2,5 s) en `LOBBY` y `REVELACION`. El cierre se detecta cuando un poll devuelve
`state == "REVELACION"` con `result` embebido; la presentación del contenido es R3-2.

**Alternatives considered**:
- Bucle `while + time.sleep() + st.rerun()` a nivel de script: bloquea el script entero,
  viola «el polling MUST NOT bloquear la interacción» (UIF-06).
- `st_autorefresh` de `streamlit-extras`: dependencia extra prohibida (UIF-12).
- Inyección de JavaScript con `st.components.v1.html` + `postMessage`: frágil y no idiomática.
- Solo refresco manual (botón «actualizar»): degradación por defecto, no la primaria.

**Rationale**: `st.fragment` con `run_every` re-ejecuta solo la región declarada sin bloquear
la interacción del resto (UIF-06). La frecuencia es un `SHOULD` y la degradación está
permitida expresamente por §14.1: si la versión de `streamlit` instalada no expone
`run_every` (o `st.rerun(scope="app")`), el wrapper local degrada al ciclo de refresco
manual (la transición de pantalla ocurre en el siguiente artefacto del usuario), sin cambiar
las pantallas. El `run_every` se re-declara cada ciclo con la frecuencia derivada de la
última instantánea, por lo que el cambio de estado ajusta la frecuencia automáticamente
(UIF-06, escenarios de frecuencia). Se verifica el requisito de versión de Streamlit en
apply (ver Decision «streamlit vía uv»).

### Decision: Contador de palabras en vivo con bloqueo local; autoridad en el orquestador

**Choice**: `src/ui/words.py` aporta `count_words(text)` — una estimación local que replica el
algoritmo del dominio (NFC + unificar espacios + `split`, igual que `normalize_text` en
`src/orchestrator/game.py:49`) — y `within_limit(words, max_words)`. En `chat.py`, el
contador en vivo se actualiza con cada cambio de texto sin enviar (UIF-04) y el botón de
enviar queda **deshabilitado y con aviso evidente** cuando `count_words(text) > snapshot.max_words`.
El límite se lee siempre de la última instantánea del orquestador (`max_words` en
`public_state()`), de modo que un cambio de límite publicado se refleja en el bloqueo local
(UIF-05, escenario «Límite local alineado con la instantánea»). La UI **nunca agrega mensajes
localmente**: la conversación mostrada es siempre `snapshot.messages`. Si el orquestador
rechaza un envío con `too_many_words` (400), el facade levanta `ApiError(code="too_many_words")`,
la pantalla muestra el motivo y el mensaje no aparece como entregado (UIF-05): simplemente no
existe en la conversación, porque la conversación es el reflejo del servidor.

**Alternatives considered**:
- Contar sin normalizar (conteo por `text.split()` crudo): diverge de la cuenta real del
  servidor y el bloqueo local fallaría en casos límite (acentos descompuestos, espacios
  dobles).
- Hacer la autoridad del límite en la UI (bloquear para siempre con el valor local): viola
  UIF-05; el servidor es la única autoridad.
- Append optimista del mensaje antes de confirmar: viola «MUST NOT presentar el mensaje como
  entregado» (UIF-05) si el servidor lo rechaza.

**Rationale**: UIF-04 y UIF-05 piden explícitamente un bloqueo local «evidente» con autoridad
del orquestador. Replicar la normalización del dominio en `count_words` mantiene la
estimación alineada con la cuenta real del servidor. Esto **no** viola la regla de AGENTS
«la normalización vive en UNA sola función»: esa función es la ruta del experimento (humanos
y modelo pasan por `normalize_text` del dominio); la UI jamás normaliza ni guarda datos — solo
cuenta palabras para mostrar, y si su estimación diverge de la autoridad, el servidor rechaza
con `too_many_words` y la UI lo muestra (ese es exactamente el contrato, UIF-05).

### Decision: IA anónima e idéntica; privacidad antes de REVELACION

**Choice**: la lista de jugadores se renderiza plana y homogénea: el alias de la IA es un
«Jugador N» más, sin etiqueta «IA» ni énfasis visual de posición (contrato §14.3, default
aceptado por R3). La UI no dibuja `is_ai`, `impostor_alias`, `votes`, `scores` ni
`tasa_deteccion` antes de REVELACION — de hecho no los dibuja nunca en R3-1 porque la vista de
revelación es un placeholder que **no renderiza ninguna clave de `result`** (UIF-08).

**Alternatives considered**:
- Etiquetar al último jugador como «IA» en el lobby: revela al impostor, rompe el juego
  (contrato §14.3 lo prohíbe explícitamente).
- Mostrar datos de `result` en el placeholder de R3-1: adelanta contenido de R3-2 y arriesga
  fugas de privacidad (contrato §9).
- Orden aleatorio de jugadores en la UI: requeriría cambio de dominio; fuera de alcance.

**Rationale**: el contrato §9 y los defaults §14.3 son la fuente de verdad del anonimato del
impostor. La UI solo muestra el estado como viene; la posición del alias la decide el
servidor. La introducción de la IA como último «Jugador N» ocurre en `start` (contrato §6.3)
y la UI lo refleja sin interpretarlo (UIF-03, escenario «Posición de la IA»).

### Decision: Testabilidad — lógica pura sin levantar Streamlit

**Choice**: la lógica testeable se aísla de Streamlit en tres lugares:
- `src/ui/words.py` (conteo y límite) — pura, sin imports de `st`.
- `src/ui/router.py` (derivación de pantalla y frecuencia de polling) — pura, sin `st`.
- `src/ui/sources/fake.py` (formas del contrato y máquina congelada) — pura, sin `st`.

Las pruebas (≥3, todas AAA, UIF-11) viven en `tests/test_ui_words.py`,
`tests/test_ui_router.py` y `tests/test_ui_api.py` y se ejecutan con `uv run pytest` sin
iniciar ningún servidor Streamlit. `app.py` y `screens/*` solo se importan en una prueba
smoke (confirmando que `src.ui.app` y los cuatro módulos de pantalla importan limpio y que la
pantalla inicial es `CONSENT`) — la ejecución interactiva real se verifica manualmente
(`uv run streamlit run src/ui/app.py`), ya que la suite del proyecto no automatiza E2E de
navegador.

**Alternatives considered**:
- Probar a través de la app Streamlit con `AppTest` de `streamlit.testing`: acopla las
  pruebas a la API de testing de Streamlit, más frágil y más lento; se descarta como
  mecanismo principal aunque puede usarse como smoke adicional.
- Probar los renders de pantalla con dobles de `st`: poco valor (assert invisible) y
  dependencia implícita de la API de widgets.

**Rationale**: UIF-11 exige al menos 3 pruebas AAA sobre contador y transición; probar la
función de conteo y la función de derivación de pantalla directamente es la vía más simple,
determinista y sin dependencias de framework. Además permite probar la máquina congelada del
fake (UIF-07) y el bloqueo por límite (UIF-04) sin red.

### Decision: `streamlit` en `pyproject.toml` + `uv.lock` vía `uv` únicamente

**Choice**: se añade `streamlit` con `uv add streamlit` (ejecuta el resolvedor sobre
Python 3.13, actualiza `dependencies` en `pyproject.toml` y regenera `uv.lock`). Prohibido
`pip` directo (UIF-12, escenario «Prohibido pip directo»). No se añade ninguna otra
dependencia de entorno.

**Alternatives considered**:
- `pip install streamlit` en el `.venv`: prohibido por regla del curso y por UIF-12 (el
  entorno solo se gestiona con uv).
- `streamlit` + `streamlit-extras` (para autorefresh): dependencia extra fuera de alcance.
- No fijar el alcance y permitir cualquier dependencia nueva no listada: UIF-12 restringe.

**Rationale**: el entorno exclusivo uv con Python 3.13 es una regla dura de AGENTS; `uv add`
es el único mecanismo autorizado. Durante apply se verifica que la versión instalada soporte
`st.fragment(run_every=...)` y `st.rerun(scope="app")`; si no la soportara, se eleva la
restricción mínima en `pyproject.toml` (o se degrada polling según §14.1, ver Decisión de
polling). Se avisa al grupo el mismo día de la nueva dependencia (mitigación del riesgo
«streamlit es dependencia nueva», propuesta §Risks).

## Data Flow

### Flujo principal (una sola boca, dos fuentes)

```
+---------------------+   llamada    +------------------------+   HTTP / in-memory   +-----------------------+
| pantalla activa     | -----------> | src/ui/api.py facade   | -------------------> | FakeSospechAI         |
| src/ui/screens/*    |              | (única boca pública)   | <------------------- | (sources/fake.py)     |
|                    | <----------- | _source() elige fuente |                      | HttpSospechAI         |
+---------------------+  respuesta   +------------------------+                      | (sources/http.py, R2) |
        ^                                 |                 |                        +-----------------------+
        |  snapshot + identity guardados  |                 +-- siempre StateSnapshot
        |  en st.session_state            |                    y raises ApiError (code)
        +---------------------------------+
```

- Cada llamada de la UI pasa por `api.py`; la UI jamás habla directo con el orquestador ni
  con el engine (UIF-10).
- El token de sesión se conserva en `session_state["room_identity"].session_token` desde el
  `create_room`/`join_room` y se adjunta en cada petición posterior como cabecera
  `X-Session-Token` (contrato §3, §6.7; UIF-06).
- El fake vive en memoria a nivel de módulo (compartido entre sesiones del mismo proceso),
  por lo que dos pestañas/navegadores de una misma máquina pueden jugar la misma sala por
  `room_code` durante el piloto.

### Secuencia del ciclo de polling (UIF-06)

```
UI fragment (run_every=interval)   api.py            fuente (fake|HTTP)
        |-- get_state(room, token) -->|                    |
        |    cabecera X-Session-Token |-- public_state() --|
        |<-- StateSnapshot -----------|   (200, espejo)    |
        |    guarda session_state["snapshot"]              |
        |    new_screen = resolve_screen(snapshot.state)   |
        |    ¿new_screen != actual? -> st.rerun(scope="app") -> main() re-encamina
        |    ¿igual? -> re-renderiza la pantalla con datos frescos
        |    intervalo = poll_interval_seconds(state)     (1 s en juego, 2.5 s fuera)
        |              (REVELACION: 2.5 s; solo placeholder, contenido R3-2)
```

### Secuencia de envío de mensaje y rechazo (UIF-04, UIF-05)

```
chat.render(on_send=text) -> within_limit(count_words(text), snapshot.max_words)?
   NO  -> botón deshabilitado + aviso "Límite superado (N/máx)"
   SÍ  -> api.submit_message(room, token, text)
           ok (204)                    -> el siguiente poll muestra el mensaje en snapshot.messages
           too_many_words (400)        -> ApiError(code="too_many_words") -> la pantalla muestra el
                                          rechazo; el texto NO aparece en la conversación
           wrong_state / session_expired -> ApiError -> aviso a la pantalla
La UI nunca agrega mensajes localmente: la conversación es snapshot.messages.
```

### Secuencia de arranque y consentimiento (UIF-01, UIF-02)

```
arranque: uv run streamlit run src/ui/app.py
  -> session_state vacío -> consent_accepted = False
  -> resolve_screen(consent_agreed=False, state=None) = CONSENT
  -> se renderiza consent.png (los dos avisos fijos + botón)
Aceptar -> consent_accepted = True -> resolve_screen(...) = LOBBY
Acceso por URL a lobby/chat/voting: imposible (no hay rutas; st.navigation/pages no se usan)
  -> cualquier render empieza por resolve_screen -> CONSENT si no hay aceptación
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/ui/__init__.py` | Create | Marca `src/ui/` como paquete. |
| `src/ui/app.py` | Create | Entry point de Streamlit: router por `session_state`, composición de pantallas, fragment de polling y callbacks que conectan pantallas con `api.py`. Guardado `if __name__ == "__main__": main()`. |
| `src/ui/router.py` | Create | Lógica pura: `Screen`, `resolve_screen`, `poll_interval_seconds` (sin `st`). |
| `src/ui/words.py` | Create | Lógica pura: `count_words`, `within_limit` (estimación local; autoridad en orquestador). |
| `src/ui/api.py` | Create | Única boca pública: `StateSnapshot`, `ChatMessage`, `RoomIdentity`, `ApiError`, `SospechAI` Protocol, facade de módulo y `_source()`. |
| `src/ui/sources/__init__.py` | Create | Exporta `FakeSospechAI` y `HttpSospechAI`. |
| `src/ui/sources/fake.py` | Create | `FakeSospechAI` in-memory conforme al contrato: máquina congelada, formas de `public_state()`/`result()`, códigos de error §8, almacén compartido por `room_code`. |
| `src/ui/sources/http.py` | Create | `HttpSospechAI` con `urllib`: cabecera `X-Session-Token`, JSON, mapeo 2xx/error → `ApiError` por `code`. |
| `src/ui/screens/__init__.py` | Create | Exporta `render` de cada pantalla. |
| `src/ui/screens/consent.py` | Create | Consentimiento obligatorio previo al lobby (UIF-02): dos avisos fijos + botón; sin aceptar no se avanza. |
| `src/ui/screens/lobby.py` | Create | Lobby (UIF-03): alias «Jugador N» del servidor, `room_code`, unirse por código, `start` si es anfitrión; cero datos personales. |
| `src/ui/screens/chat.py` | Create | Sala de chat (UIF-04/05): mensajes por alias desde `snapshot.messages`, campo de entrada, contador en vivo y bloqueo local + manejo de rechazo `too_many_words`. |
| `src/ui/screens/voting.py` | Create | Vista de votación vacía y placeholder de REVELACION (UIF-08): navegable, sin controles ni resultados (R3-2). |
| `tests/test_ui_words.py` | Create | Pruebas AAA del contador y el límite (UIF-04, UIF-11). |
| `tests/test_ui_router.py` | Create | Pruebas AAA de transición de pantalla y frecuencia de polling (UIF-02/06/09/11). |
| `tests/test_ui_api.py` | Create | Pruebas AAA de formas del fake, máquina congelada y errores (UIF-05/07/11). |
| `pyproject.toml` | Modify | Añade `streamlit` a `dependencies` (vía `uv add`). |
| `uv.lock` | Modify | Regenerado por `uv add streamlit` (UIF-12). |

Resumen: **16 archivos nuevos** (`src/ui/` 13 + tests 3), **2 modificados** (`pyproject.toml`,
`uv.lock`), **0 eliminados**. `src/orchestrator/` y `src/impostor_engine/` no se tocan
(UIF-10).

## Interfaces / Contracts

### Contrato interno de `api.py` (firma mínima)

```python
# src/ui/api.py — única boca pública; las pantallas solo importan este módulo.
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class RoomIdentity:
    """Respuesta 201 de POST /rooms y POST /rooms/{code}/join (contrato §§6.1-6.2)."""

    room_code: str
    session_token: str
    alias: str


@dataclass(frozen=True)
class ChatMessage:
    """Un elemento de `messages` en public_state() (contrato §7.1)."""

    round_number: int
    alias: str
    text: str


@dataclass(frozen=True)
class StateSnapshot:
    """Espejo de `public_state()` (contrato §7.1); en REVELACION incluye `result` (§7.2)."""

    state: str
    round_number: int | None
    rounds: int
    max_words: int
    players: list[str]
    messages: list[ChatMessage]
    votes_received: int
    remaining_seconds: float | None
    result: dict | None

    @classmethod
    def from_mapping(cls, raw: dict) -> "StateSnapshot":
        """Construir desde el JSON del cable, sin remodelar claves."""
        ...


class ApiError(Exception):
    """Falla de la fuente de datos; el cliente ramifica por `code`, nunca por `message`
    (contrato §8). `code` pertenece al catálogo estable (p. ej. `too_many_words`, 400)."""

    def __init__(self, code: str, http_status: int, message: str) -> None:
        self.code = code
        self.http_status = http_status
        self.message = message
        super().__init__(f"{code} ({http_status}): {message}")


class SospechAI(Protocol):
    """Contrato interno de fuente de datos; FakeSospechAI y HttpSospechAI lo cumplen."""

    def create_room(self) -> RoomIdentity: ...
    def join_room(self, room_code: str) -> RoomIdentity: ...
    def get_state(self, room_code: str, session_token: str) -> StateSnapshot: ...
    def start(self, room_code: str, session_token: str) -> None: ...
    def open_voting(self, room_code: str, session_token: str) -> None: ...
    def submit_message(self, room_code: str, session_token: str, text: str) -> None: ...


# Facade de módulo (las pantallas usan estas funciones; nunca el Protocol directamente)
def create_room() -> RoomIdentity: ...
def join_room(room_code: str) -> RoomIdentity: ...
def get_state(room_code: str, session_token: str) -> StateSnapshot: ...
def start(room_code: str, session_token: str) -> None: ...
def open_voting(room_code: str, session_token: str) -> None: ...
def submit_message(room_code: str, session_token: str, text: str) -> None: ...


def _source() -> SospechAI:
    """Selector de fuente (swap localizado, UIF-07): env SOSPECHAI_UI_SOURCE.

    "fake" (por defecto) -> FakeSospechAI; "http" -> HttpSospechAI con base URL en
    SOSPECHAI_ORCHESTRATOR_URL. Las pantallas no cambian al cambiar la fuente.
    """
    ...
```

Notas de alcance R3-1: el facade cubre las acciones que la navegación del esqueleto
necesita (crear/unirse, contar estado, `start`, `open_voting`, enviar mensaje). Los
endpoints de votos (`POST /rooms/{code}/votes`) y la presentación de `result` llegan con
R3-2; el fake puede simular votos internamente para recorrer la máquina, pero la UI no emite
ninguno en R3-1.

### `HttpSospechAI` (stdlib `urllib`) — comportamiento de cable

| Operación | Llamada HTTP | Cabeceras / cuerpo |
|---|---|---|
| `create_room` | `POST /rooms` | sin cabecera ni cuerpo → 201 + body §6.1 |
| `join_room` | `POST /rooms/{code}/join` | sin cabecera ni cuerpo → 201 + body §6.2 |
| `start` | `POST /rooms/{code}/start` | `X-Session-Token` | 204 |
| `open_voting` | `POST /rooms/{code}/voting/open` | `X-Session-Token` | 204 |
| `submit_message` | `POST /rooms/{code}/messages` | `X-Session-Token` + `{"text": str}` | 204 |
| `get_state` | `GET /rooms/{code}/state` | `X-Session-Token` | 200 + `public_state()` |

- `room_code` se normaliza a mayúsculas en el cliente (el servidor lo normaliza; contrato §3).
- Respuesta no-2xx: parsea `{"code", "message"}` (contrato §8) y lanza `ApiError(code,
  http_status, message)`. Códigos de error JSON malformado → `ApiError("malformed_request", 400, ...)`
  y red → `ApiError` de transporte (para R3-1, `internal`, 500) sin exponer detalles del proveedor.

### `FakeSospechAI` (in-memory, Plan B) — formas y reglas

- Estado compartido a nivel de módulo (`_ROOMS: dict[str, _Room]`), clave por `room_code`
  normalizada a mayúsculas; permite que varias sesiones del mismo proceso (pestañas) jueguen
  la misma sala durante el piloto.
- Máquina congelada (contrato §5): `LOBBY → RONDA → DISCUSION → VOTACION → REVELACION`, con
  los valores de cable exactos `LOBBY`/`RONDA`/`DISCUSION`/`VOTACION`/`REVELACION`.
- Alias por orden de inserción: `add`/`create_room` → «Jugador N»; en `start` se registra la
  IA como último «Jugador N» (N = humanos + 1) y la ronda arranca en `RONDA`.
- Las respuestas de `get_state` son el espejo literal de `public_state()`/`result()`
  (contrato §7): claves `state`, `round_number`, `rounds`, `max_words`, `players`,
  `messages`, `votes_received`, `remaining_seconds` y `result` solo en `REVELACION`.
- Catálogo de errores aplicable a acciones R3-1 (contrato §8): `session_expired` (401, token
  desconocido), `not_a_player` (403), `forbidden_host_action` (403, no anfitrión en
  `start`/`open_voting`), `room_not_found` (404), `wrong_state` (409), `invalid_roster` (409,
  `start` sin ≥2 humanos), `empty_message` (400), `too_many_words` (400), `duplicate_message`
  (409), `internal` (500). Los códigos de votación (`self_vote`, `duplicate_vote`,
  `ai_cannot_vote`) llegan con R3-2.
- Escenario scriptado para el piloto: al enviar un mensaje humano, el fake registra turnos
  de guion para los demás participantes (mismos recursos que `demo.py`), avanza las rondas
  hasta `DISCUSION`; `open_voting` del anfitrión lleva a `VOTACION`; y un poll dentro de
  `VOTACION` completa los votos restantes internamente para llegar a `REVELACION` (el
  `result` queda embebido). La UI nunca emite votos en R3-1.

### Lógica pura testeable (sin Streamlit)

```python
# src/ui/words.py
import unicodedata


def count_words(text: str) -> int:
    """Estimar las palabras como las contaría el dominio (NFC + espacios unificados)."""
    normalized = " ".join(unicodedata.normalize("NFC", text).split())
    return len(normalized.split())


def within_limit(words: int, max_words: int) -> bool:
    """Aceptar el envío solo si el conteo local no supera el límite del orquestador."""
    return words <= max_words


# src/ui/router.py
from enum import StrEnum


class Screen(StrEnum):
    """Pantallas del esqueleto R3-1 (UIF-09)."""

    CONSENT = "consent"
    LOBBY = "lobby"
    CHAT = "chat"
    VOTING = "voting"


def resolve_screen(*, consent_agreed: bool, state: str | None) -> Screen:
    """Derivar la pantalla activa; el consentimiento nunca se salta por estado (UIF-02)."""
    if not consent_agreed:
        return Screen.CONSENT
    if state in (None, "LOBBY"):
        return Screen.LOBBY
    if state in ("RONDA", "DISCUSION"):
        return Screen.CHAT
    return Screen.VOTING  # VOTACION y REVELACION (contenido en R3-2)


def poll_interval_seconds(state: str | None) -> float:
    """Frecuencia SHOULD del contrato §14.1: 1 s en juego, 2-3 s en LOBBY/REVELACION."""
    return 1.0 if state in ("RONDA", "DISCUSION", "VOTACION") else 2.5
```

Los valores de cable (`LOBBY`, `RONDA`, `DISCUSION`, `VOTACION`, `REVELACION` y las claves de
`public_state()`/`result()`) se copian del contrato §5 y §7 tal cual, sin renombrar.

## Testing Strategy

| Nivel | Qué se prueba | Cómo |
|-------|--------------|------|
| Unit | Contador y límite (UIF-04, UIF-11): texto vacío → 0; acentos NFC (`cafe\u0301` → 1); múltiples espacios/puntuación; límite `max_words=15` (15 pasa, 16 bloquea) | pytest AAA directo sobre `words.count_words` / `words.within_limit`, sin Streamlit (`tests/test_ui_words.py`) |
| Unit | Transición de pantalla (UIF-02/09/11): sin consentimiento siempre `CONSENT` aunque haya `state`; tras aceptar, `None`/`LOBBY` → `LOBBY`, `RONDA`/`DISCUSION` → `CHAT`, `VOTACION`/`REVELACION` → `VOTING`; frecuencia 1.0 s en estados de juego y 2.5 s en LOBBY/REVELACION | pytest AAA directo sobre `router.resolve_screen` / `router.poll_interval_seconds` (`tests/test_ui_router.py`) |
| Unit | Formas del fake (UIF-07): `public_state()` con las claves exactas del contrato; `result` embebido solo en `REVELACION`; máquina congelada recorrida en orden exacto; alias «Jugador N» y IA en último lugar; códigos de error (`too_many_words`, `wrong_state`, `invalid_roster`, `forbidden_host_action`…) | pytest AAA sobre `FakeSospechAI` directo, sin red (`tests/test_ui_api.py`) |
| Unit | Bloqueo/desbloqueo por límite (UIF-04) como comportamiento combinado del chat vía función pura y del fake: envío dentro del límite aceptado (204); sobre el límite, `ApiError("too_many_words", 400)`; el mensaje rechazado no aparece en la conversación | pytest AAA sobre fake + `within_limit` |
| Integration | `HttpSospechAI` contra un `ThreadingHTTPServer` stdlib local que responde las formas del contrato: verifica cabecera `X-Session-Token`, cuerpos JSON, 204/201/200 y parseo de errores por `code` | pytest (fuente `http` apuntando a `127.0.0.1:<puerto efímero>`), marcado `integration` |
| Smoke | Arranque de módulos: `import src.ui.app` y los cuatro `screens/*` importan limpio; `resolve_screen` inicial = `CONSENT` (UIF-01) | pytest (Streamlit instalado por el entorno uv) |
| Manual (piloto) | `uv run streamlit run src/ui/app.py` arranca sin errores; las 4 pantallas navegables; el contador bloquea sobre el límite; dos pestañas comparten sala por código | Criterios de éxito de la propuesta; no automatizado (sin E2E de navegador) |

La suite corre con `filterwarnings = ["error"]` (del proyecto) y el código nuevo pasa
`uv run ruff check` y `uv run black --check` (UIF-11): arranque limpio sin warnings de
Streamlit, imports ordenados y estilo PEP 8.

## Threat Matrix

`N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary.`

El "ruteo" de este cambio es lógica de aplicación (derivar la pantalla activa desde
`session_state` dentro del mismo proceso Streamlit); no introduce rutas de red, comandos de
shell, subprocesos, automatización de VCS/PR, clasificación de ejecutables ni integración de
procesos. La única red es el cliente HTTP saliente de `api.py` hacia el orquestador, que es
la integración de datos que el propio contrato define (con pruebas de doble, sin llamadas a
la API real de Hugging Face). No se fabrican filas applicables.

## Migration / Rollout

No hay migración de datos: la UI no persiste estado de partida (propuesta §Rollback Plan).
La capa es **aditiva** (no toca `src/orchestrator/` ni `src/impostor_engine/`). El rollout es:

1. **Fase 1** — esqueleto navegable (app + pantallas vacías) ya usable para revisar flujo.
2. **Fase 2** — contenido contra `api.py` con `FakeSospechAI` (Plan B para el piloto del 16).
3. **Swap a HTTP real**: cuando exista el servidor de R2, cambiar la fuente en `api._source()`
   (variable de entorno `SOSPECHAI_UI_SOURCE=http` + `SOSPECHAI_ORCHESTRATOR_URL`) sin tocar
   las pantallas (UIF-07).
4. **Rollback**: `git revert` del commit de dependencia + `uv sync`; eliminar `src/ui/` y
   `tests/test_ui_*.py`; verificar `git status --short` y `uv run pytest` en verde.

## Open Questions

None.

## Requirement Traceability

| Requisito | Elemento de diseño que lo satisface |
|-----------|--------------------------------------|
| UIF-01 — Arranque sin errores; primera pantalla consentimiento | Decisión «Router por session_state» + «Pantallas como funciones»; `app.py` con `main()` y guard `__main__`; smoke en Testing Strategy |
| UIF-02 — Consentimiento obligatorio antes del lobby, no saltable por URL | Decisión «Router por session_state»; `resolve_screen` (gate de consentimiento) + Data Flow «Arranque y consentimiento» |
| UIF-03 — Lobby con alias del servidor, cero datos personales | Decisión «Pantallas» + «IA anónima»; `lobby.py`, `RoomIdentity.alias` de `api.create_room/join_room`; contrato §3 |
| UIF-04 — Chat con alias, contador en vivo y bloqueo local | Decisión «Contador de palabras»; `words.py`, `chat.py`, `snapshot.messages/max_words`; Testing Strategy fila contador |
| UIF-05 — Autoridad del orquestador; `too_many_words` mostrado | Decisión «Contador»; `ApiError(code="too_many_words")`, sin append local; secuencia «Envío y rechazo» |
| UIF-06 — Polling corto con frecuencias y sin bloqueo | Decisión «Polling»; `st.fragment(run_every=...)`, `poll_interval_seconds`, `X-Session-Token`; Data Flow «Ciclo de polling» |
| UIF-07 — Única boca `api.py`; fake conforme e intercambiable | Decisión «api.py única boca»; `SospechAI` Protocol, `_source()`, `FakeSospechAI`; Interfaces/Contracts |
| UIF-08 — Vista de votación vacía navegable | Decisión «Pantallas»; `voting.py` placeholder sin controles ni resultados |
| UIF-09 — Navegación end-to-end; router por `session_state` sin `pages/` | Decisión «Router por session_state»; `resolve_screen`; Testing Strategy fila transición |
| UIF-10 — UI solo muestra y envía; sin gRPC ni imports de engine/orquestador | Decisiones «api.py única boca» y «Contador»; arquitectura de `src/ui/` (solo HTTP+JSON vía `api.py`) |
| UIF-11 — Calidad: ≥3 pruebas AAA, cero warnings, ruff/black | Decisión «Testabilidad»; Testing Strategy; pyproject conserva `filterwarnings=["error"]` |
| UIF-12 — `streamlit` vía uv en pyproject + uv.lock, sin pip | Decisión «streamlit vía uv»; File Changes (`pyproject.toml`, `uv.lock`) |

## Known File Locations

- Contrato: `docs/CONTRATO_UI_ORQUESTADOR.md` (v1.0, congelado)
- Orquestador (solo lectura, no se modifica): `src/orchestrator/game.py`, `src/orchestrator/demo.py`
- Reglas duras: `AGENTS.md`