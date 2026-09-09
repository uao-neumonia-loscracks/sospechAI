# Acuerdos pendientes de R2

La decisión confirmada por Natalia es inferencia por API: el engine permanece como servicio ligero y solicita texto a Hugging Face. No se mantiene un modelo en el Droplet. Véase ADR-001.

| Tema | Implementado | Pendiente |
| --- | --- | --- |
| Jugadores | Dos humanos como mínimo y una IA; la demo simula tres humanos y una IA. | Tamaño real de sala. |
| Rondas | Dos por defecto, configurables. | Número definitivo y preguntas. |
| Palabras | 15 por defecto, misma normalización y rechazo para humanos e IA. | Límite basado en A2. |
| Ventana | 20 s por ronda, reloj monotónico inyectable. | Benchmark y temporizador del servidor. |
| Deadline de IA | Hasta 8 s, limitado al tiempo restante. | Presupuesto medido y margen para guardar/publicar. |
| Votos | Uno por humano, sin autovoto ni voto de IA. | Empates, abstenciones, desconexiones y límite de votación. |
| Fallo técnico | Revelación, `valid_game=false` y `tasa_deteccion=null`. | Registro en MLflow y política visible de reinicio. |
| Persistencia | Resultado final de simulaciones SQLite. | Guardado activo, recuperación y datos humanos anonimizados. |

## R1: inferencia y contrato

Se conservan los campos 1-4 de GenerationConfig y se añaden `engine_backend=5` y `model_id=6`, como indica el plan. La extensión conserva compatibilidad del formato, pero ambos servicios deben actualizar sus stubs para interpretar los campos nuevos. El contrato sigue siendo borrador.

R1 aplica guardas de generación; R2 mantiene la comprobación final simétrica de palabras y la única normalización utilizada para publicar. Si R1 envía texto inválido, R2 no lo trunca ni sustituye: interrumpe la partida.

R1 administra HTTP, HF_TOKEN, facturación y posibles reintentos. R2 hace un intento de aplicación por turno y descarta streams parciales. Los reintentos HTTP de R1 deben respetar el deadline, sin duplicar publicaciones y registrando intentos/costos. No reintentar errores de autenticación o crédito agotado.

`model_id` identifica la selección solicitada, no demuestra el proveedor efectivo. Falta acordar cómo devuelve R1 proveedor, uso y versión efectivos para MLflow. El hash del prompt debe acompañarse de su ruta o hash de contenido: un commit puede modificar varias variantes.

## R3: interfaz y experimento

Falta el contrato UI-orquestador: crear/entrar, credenciales, estado, envío por ronda, votación y acciones del anfitrión. Los alias no autentican personas. La UI no debe elegir el impostor ni modificar el dominio directamente.

La revelación muestra el alias de IA, no nombres personales. Las sesiones de práctica y las partidas interrumpidas se separan de los experimentos humanos válidos. Un fallo de red no cuenta como detección humana. R2 aportará el evento de cierre y R3 la integración MLflow.

## R4: estructura y operación

Se usa `src/orchestrator`, `proto`, `tests`, `scripts`, `docs`, UV y Python 3.13. El entorno raíz solo contiene las dependencias de este incremento; R4 integra las de los otros servicios y el CI del equipo.

En Compose se localiza MLflow por su nombre de servicio, por ejemplo `http://mlflow:5000`; `127.0.0.1` apunta al propio contenedor. MLflow debe escuchar en la interfaz adecuada de esa red. Esto no exige abrir sus puertos ni los de gRPC a Internet.
