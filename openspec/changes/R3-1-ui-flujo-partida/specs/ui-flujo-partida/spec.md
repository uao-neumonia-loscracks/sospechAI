# ui-flujo-partida Specification

## Purpose

La capacidad `ui-flujo-partida` define la primera superficie visible del juego SospechAI durante el piloto (rol R3): el esqueleto navegable de la partida con sus cuatro pantallas — consentimiento obligatorio, lobby, sala de chat y vista de votación — construido ÚNICAMENTE contra el contrato `docs/CONTRATO_UI_ORQUESTADOR.md` v1.0. La UI habla ÚNICAMENTE con el orquestador (HTTP+JSON por polling) y nunca con el engine ni el dominio `game.py`; solo muestra y envía, no decide reglas, tiempos ni votos. La fuente de datos de R3-1 es un fake in-memory conforme al contrato, intercambiable por el servidor HTTP del orquestador sin tocar las pantallas. La lógica de votación y la revelación de resultados son R3-2, fuera del alcance de esta capacidad.

## Requirements

### Requirement: Arranque de la aplicación (UIF-01)

La aplicación MUST arrancar sin errores con el comando `uv run streamlit run src/ui/app.py`. La primera pantalla renderizada MUST ser la de consentimiento.

#### Scenario: Arranque limpio

- GIVEN un entorno con Python 3.13 gestionado por `uv`, con `streamlit` en `pyproject.toml` y `uv.lock` sincronizado
- WHEN se ejecuta `uv run streamlit run src/ui/app.py`
- THEN la aplicación Streamlit arranca sin excepciones ni errores de importación
- AND la pantalla renderizada inicial es la de consentimiento

#### Scenario: Dependencia ausente

- GIVEN un entorno donde `streamlit` no está instalado en el entorno uv
- WHEN se ejecuta `uv run streamlit run src/ui/app.py`
- THEN el proceso termina con un error de importación que identifica la dependencia faltante

### Requirement: Consentimiento obligatorio antes del lobby (UIF-02)

La pantalla de consentimiento MUST mostrarse antes del lobby, de forma obligatoria y no configurable. Debe exponer exactamente dos avisos fijos: (a) que un participante de la partida puede ser un modelo de lenguaje y (b) que la conversación se registra con fines de investigación. El acceso al lobby MUST NOT ser posible sin aceptar el consentimiento, incluido un acceso directo por URL a cualquier pantalla posterior.

#### Scenario: Aceptación explícita

- GIVEN un usuario que abre la aplicación por primera vez
- WHEN el usuario ve los dos avisos fijos y pulsa el botón de aceptación
- THEN la aplicación avanza al lobby
- AND la aceptación queda registrada en el estado de sesión de la pantalla

#### Scenario: Sin aceptación no hay entrada

- GIVEN un usuario en la pantalla de consentimiento que no lo ha aceptado
- WHEN el usuario intenta pasar al lobby sin pulsar el botón de aceptación
- THEN la aplicación MUST NOT renderizar la pantalla de lobby
- AND la aplicación permanece en la pantalla de consentimiento

#### Scenario: El consentimiento no se puede saltar por URL

- GIVEN un usuario que no ha aceptado el consentimiento en la sesión actual
- WHEN el usuario accede por URL directa a una pantalla posterior (lobby, chat o votación)
- THEN la aplicación MUST NOT renderizar esa pantalla
- AND la aplicación redirige o mantiene la pantalla de consentimiento hasta la aceptación

### Requirement: Lobby con alias del servidor y cero datos personales (UIF-03)

El lobby MUST mostrar el alias generado por el servidor con el formato "Jugador N" (N = orden de inserción, una IA siempre en último lugar tras `start`). La aplicación MUST NOT solicitar datos personales del usuario (ni nombre real ni correo electrónico), MUST NOT aceptar un alias elegido por el cliente y MUST NOT enviar alias alguno al orquestador: el servidor lo liga desde el token de sesión (contrato §3, §6).

#### Scenario: Alias asignado por el servidor

- GIVEN un usuario unido a una sala con token de sesión y alias asignados por el servidor
- WHEN la aplicación renderiza el lobby
- THEN se muestra el alias "Jugador N" proveniente de la respuesta del servidor
- AND no se muestra ningún campo de nombre real ni de correo electrónico

#### Scenario: Posición de la IA

- GIVEN una partida iniciada con `start` (contrato §6.3)
- WHEN la aplicación muestra la lista de jugadores dentro de la partida
- THEN la IA aparece únicamente como el último alias "Jugador N", sin etiqueta "IA" ni énfasis visual de posición

#### Scenario: El cliente no propone alias

- GIVEN un usuario en el lobby
- WHEN el usuario intenta escribir o enviar un alias propio
- THEN la aplicación MUST NOT enviar ese alias al orquestador
- AND el alias mostrado sigue siendo siempre el "Jugador N" asignado por el servidor

### Requirement: Sala de chat con alias y contador de palabras (UIF-04)

La sala de chat MUST mostrar los mensajes con su alias, MUST ofrecer un campo de entrada de texto y MUST mostrar un contador de palabras en vivo. Al superar el límite de palabras (`max_words`), la aplicación MUST bloquear localmente el envío del mensaje: el usuario no puede enviar texto por encima del límite. El límite lo obtiene la aplicación de la instantánea del orquestador (`max_words` en `public_state()`).

#### Scenario: Contador de palabras en vivo

- GIVEN un usuario escribiendo en el campo de entrada de la sala de chat
- WHEN el texto cambia
- THEN el contador muestra en vivo el número de palabras del texto escrito
- AND el contador se actualiza sin necesidad de enviar el mensaje

#### Scenario: Bloqueo al superar el límite

- GIVEN una sala con `max_words` = 15 en la instantánea de estado
- WHEN el usuario escribe un texto de 16 o más palabras
- THEN la aplicación MUST NOT permitir el envío del mensaje
- AND al usuario se le indica de forma evidente que el límite de palabras fue superado

#### Scenario: Envío permitido dentro del límite

- GIVEN una sala con `max_words` = 15 en la instantánea de estado
- WHEN el usuario escribe un texto de 15 palabras o menos
- THEN la aplicación permite el envío del mensaje
- AND el mensaje se envía al orquestador para su inclusión en la ronda

### Requirement: Límite de palabras con autoridad en el orquestador (UIF-05)

El contador y el bloqueo local son una ayuda evidente de la UI; la autoridad sobre el límite real MUST reposar en el orquestador. Si el orquestador rechaza un mensaje por exceder el límite real (código de error `too_many_words`, contrato §9), la aplicación MUST mostrar ese rechazo al usuario y MUST NOT presentar el mensaje como entregado.

#### Scenario: Rechazo del orquestador mostrado al usuario

- GIVEN un mensaje enviado que el orquestador rechaza con `too_many_words` (400)
- WHEN la aplicación recibe el error del orquestador
- THEN la aplicación muestra el motivo del rechazo al usuario
- AND el mensaje no aparece en la conversación

#### Scenario: Límite local alineado con la instantánea

- GIVEN una sala cuyo estado publica `max_words`
- WHEN la aplicación carga una nueva instantánea con un `max_words` distinto
- THEN el bloqueo local del contador usa el último `max_words` publicado por el orquestador

### Requirement: Polling corto de estado (UIF-06)

La aplicación MUST actualizar el estado de la partida por polling a `GET /rooms/{room_code}/state` con la cabecera `X-Session-Token` (contrato §6.7, §8). La frecuencia SHOULD ser de 1 segundo en los estados `RONDA`, `DISCUSION` y `VOTACION`, y de 2 a 3 segundos en `LOBBY` y `REVELACION`. La aplicación MAY degradar o acelerar la frecuencia según el contrato §14.1. El polling MUST NOT bloquear la interacción del usuario con la UI durante cada tick.

#### Scenario: Frecuencia en estados de juego

- GIVEN una partida en estado `RONDA`, `DISCUSION` o `VOTACION`
- WHEN la aplicación ejecuta el ciclo de polling
- THEN `GET /rooms/{room_code}/state` se consulta cada 1 segundo
- AND el token de sesión se envía en la cabecera `X-Session-Token` en cada petición

#### Scenario: Frecuencia en lobby y revelación

- GIVEN una partida en estado `LOBBY` o `REVELACION`
- WHEN la aplicación ejecuta el ciclo de polling
- THEN `GET /rooms/{room_code}/state` se consulta cada 2 a 3 segundos

#### Scenario: El polling no bloquea la UI

- GIVEN una petición de estado en curso
- WHEN el usuario interactúa con la pantalla durante la espera de la respuesta
- THEN la UI permanece responsiva y no queda bloqueada por el ciclo de polling

#### Scenario: Cierre de sala detectado por el estado final

- GIVEN una partida cuyo siguiente poll devuelve `state == "REVELACION"` con `result` embebido (contrato §5, §14.4)
- WHEN la aplicación procesa la instantánea
- THEN la aplicación reconoce el estado final como evento de cierre de la sala
- AND mantiene la frecuencia de polling de 2 a 3 segundos en `REVELACION` (la presentación del contenido de revelación es R3-2)

### Requirement: Fuente de datos conforme al contrato e intercambiable (UIF-07)

La aplicación MUST obtener los datos de la partida desde una única boca de entrada: el módulo `api.py`. Mientras no exista el servidor HTTP del orquestador, la aplicación MUST usar una fuente de datos fake en memoria que respete las formas del contrato: la máquina de estados congelada `LOBBY → RONDA → DISCUSION → VOTACION → REVELACION`, los valores de cable `public_state()`/`result()` (contrato §§7-8) y el catálogo de códigos de error (contrato §9). El intercambio entre el fake y el cliente HTTP real MUST estar localizado en `api.py`, de modo que las pantallas no cambien al cambiar de fuente de datos.

#### Scenario: El fake respeta las formas del contrato

- GIVEN la fuente de datos fake activa en `api.py`
- WHEN se solicita la instantánea de estado de una sala
- THEN la respuesta tiene la forma de `public_state()` (claves `state`, `round_number`, `rounds`, `max_words`, `players`, `messages`, `votes_received`, `remaining_seconds`, `result`) y en `REVELACION` incluye el cuerpo de `result()`

#### Scenario: El fake recorre la máquina de estados congelada

- GIVEN la fuente de datos fake activa
- WHEN se simulan las transiciones de una partida completa
- THEN los estados recorridos son, en orden y con los valores de cable exactos, `LOBBY`, `RONDA`, `DISCUSION`, `VOTACION` y `REVELACION`
- AND cualquier operación no válida para el estado devuelve los códigos de error del catálogo del contrato

#### Scenario: El swap a HTTP real no toca las pantallas

- GIVEN la aplicación funcionando con el fake y un servidor HTTP del orquestador disponible
- WHEN se cambia la fuente de datos de `api.py` para hablar con el HTTP real
- THEN las pantallas de la UI no requieren cambios para seguir mostrando el estado y enviando acciones

### Requirement: Vista de votación vacía navegable (UIF-08)

La vista de votación MUST existir y ser navegable en R3-1, aunque su contenido esté vacío: la lógica de votación y la revelación con resultados son R3-2. La aplicación MUST NOT mostrar en R3-1 controles ni resultados de votación, ni lógica de revelación.

#### Scenario: Navegación a la vista de votación

- GIVEN una partida cuyo estado publicado es `VOTACION`
- WHEN la aplicación renderiza la pantalla según el estado
- THEN la vista de votación se muestra y es navegable
- AND la vista no contiene controles de votación ni resultados (reservados a R3-2)

#### Scenario: Vista vacía sin lógica propia

- GIVEN la vista de votación de R3-1 visible
- WHEN el usuario interactúa con ella
- THEN la vista no decide ni ejecuta votos, recuentos ni avances de estado
- AND solo permite la navegación hacia las otras pantallas del flujo

### Requirement: Navegación end-to-end entre las cuatro pantallas (UIF-09)

La aplicación MUST exponer un esqueleto navegable end-to-end con las cuatro pantallas: consentimiento → lobby → sala de chat → votación. La ruta activa MUST determinarse con `session_state` y la aplicación MUST NOT usar `st.navigation` ni `pages/` como mecanismo de ruteo, para que el consentimiento no pueda omitirse por URL.

#### Scenario: Recorrido completo del esqueleto

- GIVEN un usuario que acepta el consentimiento
- WHEN el usuario recorre lobby, sala de chat y votación siguiendo el avance del estado
- THEN las cuatro pantallas se renderizan en orden sin errores y permiten la navegación entre ellas

#### Scenario: Transición de pantalla por estado polling

- GIVEN una partida cuyo polling devuelve un estado nuevo
- WHEN la aplicación procesa la instantánea y renderiza la pantalla correspondiente
- THEN la pantalla mostrada se corresponde con el estado publicado (por ejemplo, `VOTACION` muestra la vista de votación)

#### Scenario: Router por session_state

- GIVEN la aplicación ejecutándose
- WHEN se inspecciona el mecanismo de ruteo
- THEN la pantalla activa se deriva de `session_state`
- AND `st.navigation` y la carpeta `pages/` no se usan como mecanismo de ruteo

### Requirement: La UI solo muestra y envía (UIF-10)

La UI MUST comunicarse únicamente con el orquestador por HTTP+JSON y MUST NOT comunicarse con el engine, ni por gRPC ni por ningún otro transporte directo. La UI MUST NOT decidir reglas de juego, tiempos ni votos: se limita a mostrar el estado del orquestador y a enviar las acciones del contrato. El cambio MUST NOT modificar `src/orchestrator/` ni `src/impostor_engine/` (es aditivo).

#### Scenario: Sin comunicación gRPC con el engine

- GIVEN el código nuevo de la UI
- WHEN se inspeccionan sus dependencias y llamadas
- THEN no existen importaciones ni invocaciones gRPC hacia `src/impostor_engine/`
- AND tampoco existen accesos directos a `src/orchestrator/` ni al dominio `game.py`

#### Scenario: La UI no decide lógica de juego

- GIVEN un estado de partida recibido desde el orquestador
- WHEN la UI renderiza el estado y acepta acciones del usuario
- THEN la UI solo refleja el estado y envía las acciones definidas en el contrato
- AND no computa reglas, tiempos, turnos ni votos por sí misma

### Requirement: Calidad del código nuevo (UIF-11)

El código nuevo MUST pasar la suite de pruebas con warnings tratados como error (`filterwarnings = ["error"]`), MUST ser compatible con `uv run ruff check` y `uv run black --check`, y MUST contar con al menos 3 pruebas con estructura Arrange-Act-Assert sobre el contador de palabras y la transición entre pantallas, todas en verde.

#### Scenario: Cero warnings

- GIVEN la suite de pruebas configurada con `filterwarnings = ["error"]`
- WHEN se ejecuta `uv run pytest`
- THEN la suite termina sin emitir ningún warning

#### Scenario: Estilo limpio

- GIVEN el código nuevo
- WHEN se ejecuta `uv run ruff check` y `uv run black --check`
- THEN no se reportan hallazgos en el código nuevo

#### Scenario: Pruebas AAA sobre contador y transición

- GIVEN al menos 3 pruebas con estructura Arrange-Act-Assert cubriendo el contador de palabras y la transición entre pantallas
- WHEN se ejecuta `uv run pytest`
- THEN todas las pruebas pasan

### Requirement: Dependencia streamlit gestionada por uv (UIF-12)

`streamlit` MUST añadirse como dependencia del proyecto en `pyproject.toml` y reflejarse en `uv.lock`, gestionada exclusivamente con `uv`. Está prohibida la instalación directa con `pip`. No se añade ninguna otra dependencia de entorno fuera del alcance de esta capacidad.

#### Scenario: Dependencia registrada en el proyecto

- GIVEN el proyecto SospechAI con entorno uv
- WHEN se añade `streamlit` a las dependencias con `uv`
- THEN `streamlit` aparece en `pyproject.toml` y en `uv.lock`
- AND `uv sync` instala el entorno sin errores

#### Scenario: Prohibido pip directo

- GIVEN el entorno virtual del proyecto
- WHEN se audita cómo se instaló `streamlit`
- THEN la instalación proviene de `uv` y no hay cambios de entorno realizados con `pip` directo