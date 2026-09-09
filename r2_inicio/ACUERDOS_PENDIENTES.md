# Acuerdos pendientes antes de integrar R2

Este documento propone decisiones para conversar cuando se repartan los roles.
No registra acuerdos ya aprobados. La rama no cierra las tareas A6, A8 ni A15.

## Reglas temporales del ejemplo

| Tema | Comportamiento del ejemplo | Acuerdo que falta |
| --- | --- | --- |
| Participantes | Mínimo dos humanos y una IA; la demo simula tres humanos y una IA. | Número de participantes y condiciones para abrir una partida real. |
| Rondas | Dos; todas las personas y la IA responden una vez por ronda. | Número definitivo y quién selecciona las preguntas. |
| Palabras | Máximo 15; se rechaza el exceso para humanos e IA. | Límite basado en A2 y comportamiento ante respuestas largas. |
| Normalización | Espacios y Unicode NFC; conserva mayúsculas, tildes y puntuación. | Qué señales lingüísticas quieren conservar para el experimento. |
| Tiempo | Avance por respuestas recibidas; todavía no hay temporizador. | Ventanas de respuesta, de discusión y de votación; expiración, desconexiones y abstenciones. |
| Votos | Un voto por humano; no hay autovoto ni voto de IA. | Si esas reglas son las elegidas por el equipo. |
| Puntaje | Un punto por señalar correctamente al impostor. | Condición de victoria, empates y posibles eliminaciones. |
| Revelación | Automática al recibir todos los votos humanos; muestra el alias del impostor. | Cómo cerrar una partida con votos ausentes sin bloquear la revelación. |
| Persistencia | SQLite conserva el resultado final de cada simulación. | Guardado durante la partida y recuperación tras reiniciar el servidor. |

Los dos participantes humanos simulados no representan personas reales. La IA
simulada devuelve frases escritas de antemano. Estos registros no deben usarse
como evidencia de detección humana, datos de A4 ni sesiones experimentales de A25.

## Con R1: servicio de inferencia, A6

El archivo `proto/impostor.proto` conserva los campos y sus números del PDF y
añade las definiciones ausentes de `HealthRequest` y `HealthResponse`.

Falta acordar los valores predeterminados de generación, el presupuesto de tiempo,
la semántica de los fragmentos finales, errores y la versión del prompt. Un retry
debe descartar una generación parcial antes de intentar otra y evitar publicar dos
respuestas para el mismo turno. El controlador seguirá validando el límite final.

El ejemplo de consola todavía no llama este servicio. Después de la revisión
conjunta se generarán los stubs, se añadirá la validación en CI con R4 y se decidirá
si corresponde crear la etiqueta `proto-v1`. Esa etiqueta no se crea en este inicio.

## Con R3: comunicación entre la interfaz y el orquestador

Este es un inventario para diseñar un segundo contrato; no son RPC implementadas.

| Operación propuesta | Entrada principal | Respuesta esperada |
| --- | --- | --- |
| Crear sala | Configuración autorizada de la partida. | Identificador de sala y credencial del anfitrión. |
| Entrar a sala | Sala y consentimiento. | Alias automático y credencial del participante. |
| Consultar estado | Sala y credencial. | Etapa, ronda, mensajes públicos, tiempo restante y acciones permitidas. |
| Enviar respuesta | Credencial, ronda y texto. | Aceptación o motivo del rechazo. |
| Votar | Credencial y alias sospechoso. | Confirmación del único voto. |
| Iniciar o avanzar | Credencial del anfitrión o evento del temporizador. | Nuevo estado autorizado. |

La interfaz no debe poder elegir `is_ai`, actuar como otro alias, obtener la
identidad del impostor antes del cierre ni modificar directamente el estado.
En el servicio futuro las credenciales se traducirán a identidades del lado del
servidor; los alias por sí solos no autentican a nadie. `public_state()` ofrece una
vista sin la marca de IA, pero todavía no hay endpoints ni gestión de sesiones.

## Con R4: estructura, pruebas e integración

La carpeta `r2_inicio` mantiene el ejemplo independiente mientras se acuerda la
estructura canónica en A3. Las herramientas de desarrollo están fijadas en un
archivo propio; no se configura el proyecto raíz ni se declara completada A3.

La futura integración necesita servidor gRPC, cliente de inferencia con timeout,
control de concurrencia, persistencia de partidas activas, temporizadores y
pruebas de contrato e integración. Las pruebas actuales verifican el dominio y
SQLite de forma local. La compilación del `.proto` comprueba su sintaxis, no el
funcionamiento de un servicio real.
