# ADR-008 - A22 reescrito: cliente HTTP resiliente hacia la Inference API

**Fecha:** 2026-10-02 · **Estado:** aceptada
**Decide:** R1 · **Consultado:** R2 (deadline y cierre por fallo), R4 (model_card)

## Contexto

El ticket A22 decía "Volumen persistente y descarga del GGUF fuera de la
imagen". Con el cambio a la Inference API (ADR-001) el engine dejó de
descargar un modelo local: la generación es una llamada HTTP de streaming al
router de Hugging Face. El GGUF ya no existe como artefacto, y con él
desaparece el problema de "persistir el volumen para no redescargar".

Lo que sí existe hoy es un cliente HTTP que habla con un proveedor externo
remoto: red real, cuotas del proveedor, autenticación y facturación. Ese es el
riesgo operativo que el ticket original intentaba reducir con otra forma.

## Decisión

**A22 se reescribe como "Cliente HTTP resiliente hacia la Inference API".** El
ticket ya no trata de almacenamiento, sino de que el engine sobreviva a los
fallos del canal HTTP sin duplicar llamadas facturables.

La resiliencia del cliente en `src/impostor_engine/inference_client.py` es:

- **Timeout por llamada.** `InferenceClient(timeout=60.0)` por defecto,
  configurable por llamada. El presupuesto se vuelve un *deadline* absoluto
  (`time.monotonic() + budget`) y el socket usa `timeout=remaining`, de modo
  que el tiempo restante siempre se agota entre intentos.
- **Reintentos: como máximo uno, y solo para fallos de red previos al envío**
  (conexión rechazada, DNS, socket timeout en el connect). Se reintenta
  únicamente si el deadline restante lo permite. **Nunca** se reintenta una
  respuesta HTTP, jamás después de recibir un byte del stream, ni en errores
  de autenticación o crédito: cada byte recibido implica que la petición pudo
  haberse facturado (ACUERDOS_R2).
- **Sin backoff artificial.** El único limitador entre intentos es el deadline:
  si el fallo de envío ocurre y queda tiempo, se reintenta de inmediato con el
  resto del presupuesto. No hay sleep ni espera exponencial.
- **Manejo de errores HTTP con tipo estable y mensaje seguro.** La traducción
  en `_map_http`:

  | HTTP | kind de `InferenceError` |
  | --- | --- |
  | 401, 403 | `auth` |
  | 402 | `credits` |
  | 404, 422 | `rejected` |
  | 429, >= 500 | `unavailable` |
  | resto | `rejected` |

  Ningún código HTTP se reintenta; el mensaje se trunca a 200 caracteres y no
  expone credenciales.

Verificado por las pruebas en `tests/test_inference_client.py`:
`test_402_is_credits_without_retry`, `test_401_is_auth_without_retry`,
`test_network_error_before_send_retries_once_then_unavailable`,
`test_timeout_kind_on_deadline_socket_timeout`,
`test_http_5xx_is_unavailable_without_retry`,
`test_404_is_rejected_without_retry`,
`test_sent_request_builds_openai_body` y
`test_attempts_counts_retry_when_send_failure`.

## Qué quedó fuera y por qué

- **Caché de respuestas.** No se construyó por tiempo. El costo medido real es
  inferior a USD 0,000059 por llamada con 169 solicitudes en el periodo
  (ADR-006): no es un problema de dinero, y una caché correcta exigiría decidir
  claves, TTL y qué hacer con respuestas idénticas en partidas distintas.
- **Reintentos de respuestas 5xx/429.** Deliberado: reintentar una respuesta
  HTTP ya recibida puede duplicar una llamada facturada. El sistema prefiere
  fallar con `unavailable` y que el orquestador cierre la partida revelando la
  IA (decisión de R2) antes que arriesgar doble cargo.

## Consecuencias

- El ticket A22 queda cerrado: su intención original (no redescargar un modelo
  local) se resolvió con ADR-001, y su riesgo real (canal HTTP frágil) queda
  cubierto por este cliente y sus pruebas.
- El costo por llamada no es una restricción para reintentos ni para el barrido
  de A25 (ver ADR-006, punto 4).
- No se tocó código: este ADR documenta comportamiento existente y verificado.