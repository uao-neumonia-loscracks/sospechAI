# Revisión del cambio a API — R2 Natalia

**Fecha:** 2026-09-09 · **Base revisada:** inicio local de R2, commit `748d52d`.

El cambio confirmado es ejecutar el modelo en un proveedor externo. El servicio `impostor-engine` sigue existiendo como intermediario gRPC/HTTP. En el inicio de R2 había reglas, consola de práctica, SQLite y un borrador de contrato; no había un modelo instalado ni un despliegue que retirar.

## Impacto y correcciones de esta rama

| Área | Efecto de la API | Corrección |
| --- | --- | --- |
| Reglas | Votos, puntajes y normalización no dependen del lugar de inferencia. | Se conserva el dominio y su validador compartido para humanos e IA. |
| Espera | La red y el proveedor pueden demorar o fallar. | Cliente gRPC con deadline limitado al tiempo restante de la ronda. |
| Streaming | Una respuesta puede quedar incompleta. | Acumular fragmentos, exigir cierre final vacío y descartar texto parcial o excesivo. |
| Experimento | Una avería puede delatar al impostor. | Revelar y marcar la partida interrumpida; sin puntaje ni tasa de detección. La interrupción debe registrarse aparte al integrar MLflow. |
| Configuración | Modelo y backend pasan a ser datos de la petición. | Añadir campos 5 y 6 sin renumerar los anteriores; generar stubs. A6 sigue pendiente. |
| Consumo | Un reintento puede duplicar una llamada facturable. | Validar el turno antes de invocar y hacer un intento de aplicación en R2. R1 administra HTTP. |
| Organización | El inicio separado no seguía la estructura del equipo. | Mover a `src/orchestrator`, `proto`, `tests`, `scripts` y `docs`; entorno UV con Python 3.13. |

El cliente usa el [deadline de gRPC](https://grpc.io/docs/guides/deadlines/). R1 debe propagar ese presupuesto al cliente HTTP y cancelar el trabajo cuando termine el RPC. El deadline de R2 por sí solo no demuestra que el proveedor haya cancelado el cobro.

## Ajustes necesarios en el plan recibido

1. **El contrato sí cambia.** Añadir `engine_backend` y `model_id` es una extensión aditiva; requiere stubs actualizados y revisión R1/R2. No se crea una etiqueta de contrato congelado.
2. **La guarda de R1 y la validación de R2 cumplen funciones distintas.** El engine controla la generación; el controlador verifica las mismas reglas antes de publicar cualquier participante. Se conserva una única normalización.
3. **El modelo candidato aparece con proveedor.** La consulta pública del 09/09 mostró `featherless-ai` con estado `live`. Esto no acredita acceso con el token del equipo, latencia, precio ni calidad. Véase la [verificación](verificaciones/2026-09-09-inference-api.md).
4. **La cuota indicada necesita corrección.** La documentación consultada muestra USD 0,10 mensuales para Free, sujetos a cambio; no “inferior a 0,10”. R1 debe medir el presupuesto antes del barrido.
5. **El spike necesita cuidar la medición.** Para p95 por rango más próximo usar `ceil(0.95 * n) - 1`: con 30 muestras es el índice 28. El ejemplo usa el 27. Registrar ausencia de primer token, chunks sin `choices`, respuestas vacías, errores, intentos y timeout total. No llamar “costo despreciable” a un saldo sin resolución suficiente para medirlo.
6. **No asumir latencias por un código HTTP.** Un 503 no demuestra por sí solo un arranque en frío. Los umbrales de 8/20 s de esta rama son propuestas hasta contar con datos de A2.
7. **No se incorpora un modelo local de respaldo.** La instrucción actual elimina el modelo del Droplet. Ante un fallo se interrumpe y revela; la consola simulada es solo una herramienta de aprendizaje.
8. **Pregeneración y caché necesitan un diseño experimental explícito.** Una respuesta calculada con historia incompleta cambia el contexto. Reutilizar una respuesta cacheada no produce una generación independiente ni mide la latencia de API. No se implementan en R2.
9. **La trazabilidad requiere más que un hash de commit.** Registrar también ruta o hash del contenido del prompt y proveedor efectivo. Un commit puede contener varias variantes y el modelo solicitado no prueba qué proveedor atendió la petición. Falta acordar esos metadatos con R1/R3.
10. **MLflow en otro contenedor requiere dirección de servicio.** Usar, por ejemplo, `http://mlflow:5000`; localhost apunta al propio contenedor. Esto corresponde a la [resolución de servicios de Compose](https://docs.docker.com/compose/how-tos/networking/).
11. **Dos cuentas del plan no coinciden.** Cuatro personas aportando 20 pares producen 80, no 100; 25 por persona completa la meta. La propuesta adjunta enumera 3 × 3 × 3 × 2 × 3 niveles: 162 configuraciones, no 243. El barrido reducido de 3 × 3 sigue siendo 9, sujeto al acuerdo del equipo.
12. **Los criterios de cierre deben tener evidencia.** Pytest sin pruebas normalmente termina con código 5. Los estados del tablero no prueban integración; no se cierran A5/A6/A8/A15 por este incremento ni se certifica una nota. Las referencias del plan a “hoy 08/09” deben actualizarse al organizar el trabajo.

## Pendientes y siguiente paso

R1 verifica acceso real, latencia y consumo; implementa el cliente HTTP y acuerda errores, cancelación y metadatos. R2 y R1 revisan los stubs, el fragmento final y los parámetros de [ADR-003](adr/ADR-003-parametros-de-juego.md).

Después, R2 incorpora el servidor multijugador, autenticación de sesiones, control de concurrencia, temporizador activo y persistencia. La ventana actual se evalúa con acciones y consultas; todavía no existe un proceso que la vigile sin actividad. R3 conecta UI y MLflow, y R4 integra Compose y CI. No se han modificado tarjetas, contratado infraestructura ni comunicado decisiones al docente.
