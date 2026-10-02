# ADR-006 - Costo de la API: el cargo es por token y la anomalia de ~100x no existe

**Fecha:** 2026-09-18 · **Estado:** propuesta
**Decide:** R1 · **Propone:** R1 · **Consultado:** R4 (el model_card cita el numero que este ADR retira), pendiente

## Contexto

El ticket R1-9 nacio de una observacion del benchmark del 2026-09-09: **USD 0,23
de Inference Usage por 143 solicitudes**, es decir ~USD 0,0016 por llamada,
"cerca de 100 veces lo que sugiere la tarifa publicada por token". Ese numero
quedo escrito en `docs/model_card.md` como pendiente de explicar, condicionaba
el tamano del barrido experimental de A25 (9 configuraciones x 10 partidas x 6
llamadas = 540 llamadas) y motivo este ADR.

El ticket pedia diagnosticar tres cosas: si el costo por peticion varia con los
tokens o es plano, que fraccion es prompt contra completion, y si el proveedor
efectivo es el que creemos.

## Lo que se midio (2026-09-18)

Lectura de la pagina de Billing, ventana de periodo explicita **SEP 1 - OCT 1**:

| Metrica | Valor |
| --- | --- |
| Inference Usage del periodo | **USD 0,00** (el widget lo rotula como "< USD 0,01") |
| Solicitudes | **169**, todas a Featherless AI (Together AI: 0) |

Contra la linea base de 143 solicitudes del 2026-09-09 son **+26 solicitudes**:
mis 21 llamadas de hoy (1 de diagnostico + 20 de la prueba controlada) mas 5
que no son mias, atribuibles a actividad del equipo en los 9 dias intermedios
(pruebas de Docker y E2E con el engine real). No hace falta explicarlas una por
una: no cambian ninguna magnitud.

## Hallazgo principal: la lectura de USD 0,23 era incorrecta

**El total NO subio a USD 0,23. Sigue en USD 0,00.** Un contador acumulativo de
un mismo periodo **no puede bajar**: si el 2026-09-09 el periodo marcaba USD
0,23 con 143 solicitudes, hoy no puede marcar USD 0,00 con 169. Una de las dos
lecturas es falsa.

La que sobrevive es la de hoy, por dos razones:

1. **El conteo de solicitudes si se movio** (143 -> 169) mientras el costo no.
   Si esas 26 llamadas hubieran costado USD 0,0016 cada una, el total mostraria
   ~USD 0,04. Muestra USD 0,00.
2. La propia medicion del 2026-09-09 habia dejado anotada una **leccion de
   metrologia**: las paginas de HF mostraron valores contradictorios entre si
   (USD 0,89 y USD 0,18 y USD 0,01 en lecturas sucesivas del mismo periodo). La
   inestabilidad de esa pagina ya estaba documentada.

**La anomalia de ~100x no existe.** R1-9 se creo para explicar un numero que
estaba mal medido.

## La pregunta 1 tiene respuesta: el cargo es por token

El limite superior es lo decisivo, no ruido. "< USD 0,01" sobre 169 solicitudes
implica:

```
< USD 0,01 / 169 solicitudes = < USD 0,000059 por llamada
```

Contra las tres hipotesis de facturacion:

| Hipotesis | Prediccion para esas 169 | Billing | Veredicto |
| --- | --- | --- | --- |
| Proporcional a **tokens** (tarifa publicada, ~65 tokens/llamada) | ~USD 0,003 | USD 0,00 | **compatible** |
| **Plano** por solicitud (a USD 0,0016) | USD 0,27 | USD 0,00 | descartada |
| Proporcional al **tiempo** de computo | USD 0,09 o mas, solo por mis 20 llamadas | USD 0,00 | descartada |

**El cargo es proporcional a los tokens y consistente con la tarifa publicada.**
Las otras dos hipotesis quedan descartadas por un margen amplio: la distancia
entre USD 0,003 y USD 0,27 es de dos ordenes de magnitud, muy por encima de la
resolucion de un centavo de la pagina.

**El experimento controlado lo confirma.** Veinte llamadas en dos grupos de 10,
a igual numero de llamadas pero con trabajo generado muy distinto:

| | Grupo A (cortas) | Grupo B (largas) | Ratio B/A |
| --- | --- | --- | --- |
| Llamadas | 10 | 10 | 1,0x |
| Segundos | 16,7 | 77,2 | 4,6x |
| Completion tokens | 181 | 6.199 | 34,2x |

Costo esperado de esas 20 llamadas bajo cada hipotesis: ~USD 0,0015 por token,
~USD 0,032 si fueran planas y ~USD 0,090 si fueran por tiempo. **Billing no se
movio de USD 0,00**, lo que deja al modelo por token como unico sobreviviente.

Nota de diseno: `max_tokens` **no** fuerza generaciones largas — el modelo corta
cuando termina su respuesta. Para forzar salida larga hubo que cambiar el
*prompt*, no el limite.

## La pregunta 2: prompt contra completion

El ticket asumia que el prompt podria ser ~85% del gasto. Bajo facturacion por
token, con un system prompt de ~120 tokens y una respuesta de ~20,
`(120 x 0,17) / (120 x 0,17 + 20 x 0,20) = 83,6%`: **la aritmetica del ticket es
correcta**. Con el cargo confirmado como proporcional a tokens, esa estimacion
queda en pie como criterio de reparto.

Lo medido en tiempo (TTFT 795,0 ms de 1679,3 ms = 47,3% del tiempo por llamada
es previo al primer token) sirve para la latencia y el deadline de R2, no para
el costo.

## La pregunta 3: el proveedor efectivo

**Respondida dos veces, por fuentes independientes:**

- **Billing:** 169 solicitudes a Featherless AI, **0 a Together AI**. No hay
  reenvio silencioso a un proveedor mas caro.
- **La respuesta del router** trae la cabecera
  **`x-inference-provider: featherless-ai`**.

Dato adicional: el campo `model` que devuelve el router es
`Qwen/Qwen2.5-7B-Instruct` **sin** el sufijo `:featherless-ai` que se envia: el
sufijo enruta, no vuelve en la respuesta.

## La forma real del objeto `usage` (verificada)

Se volco el objeto crudo de una llamada:

```json
{
  "prompt_tokens": 33,
  "completion_tokens": 8,
  "total_tokens": 41,
  "cached_tokens": 0
}
```

**`cached_tokens` viene PLANO, no anidado en `prompt_tokens_details`.** Una
hipotesis previa de este ADR (que el router seguia la forma anidada de OpenAI)
es **falsa**: este proveedor se aparta de esa forma. La lectura original de
`servicer.py` era la correcta y el cambio a la forma anidada **se revirtio**.

Tambien se verifico que la respuesta **no trae ninguna cabecera de costo ni de
facturacion**: el costo no es legible desde la API, solo desde Billing.

## Dos formulas de costo divergentes en el mismo repo

| | `src/impostor_engine/inference_client.py` | `src/common/metrics.py` |
| --- | --- | --- |
| Unidad | USD por **1M** | USD por **1K** |
| Cacheados | Se **suman** al prompt completo | Se **restan** del prompt facturable |
| Tarifas | Constantes fijas | Parametro `Pricing` |

La convencion OpenAI-compatible incluye los tokens cacheados **dentro** de
`prompt_tokens`. Bajo ese supuesto la formula del engine **cobra los cacheados
dos veces** y `src/common/metrics.py` es la correcta.

**Estado de ese supuesto: inferido, no verificado.** El `usage` real devuelve
`cached_tokens: 0`, asi que la pertenencia de los cacheados al prompt **no es
observable todavia**: solo se verifica el dia que el cacheo de prompt produzca
`cached_tokens > 0`. Hasta entonces las dos formulas dan el **mismo resultado**
y el doblecobro permanece **latente**.

Hay una tercera consecuencia: el engine calcula `cost_usd` en `servicer.py:338`
pero **no lo emite en la metadata** (la lista manda `x-usage-*` y `x-latency-*`,
sin costo), por eso el orquestador tuvo que recalcularlo. Eso es lo que creo la
duplicacion.

## Decision propuesta

1. **Retirar el numero de USD 0,23 y su derivado de ~USD 0,0016 por llamada.**
   Son incorrectos. Hay que sacarlos de `docs/model_card.md` (linea del resumen
   de costo) y de `docs/verificaciones/2026-09-09-benchmark-r1.md` (seccion
   "Costo y presupuesto"), y reemplazarlos por la lectura del 2026-09-18: **USD
   0,00 para 169 solicitudes**, con el limite de < USD 0,000059 por llamada.
   Dejarlos seria publicar en la entrega un numero que este ADR demuestra falso.

2. **El costo se estima por token a las tarifas publicadas.** El modelo por
   token, que era el que "no explicaba" el cargo, resulta ser el correcto. La
   metrica `costo_estimado` de A13 es utilizable como esta.

3. **Una sola fuente de verdad para la formula**: `src/common/metrics.py`, con
   las tarifas canonicas en USD por 1K (`0,00017` / `0,0002` / `0,000136`). El
   engine delega en ella y se elimino su copia local.

4. **El presupuesto del barrido A25 deja de ser un problema.** 540 llamadas a
   tarifa publicada rondan **USD 0,01**: es practicamente gratis. Ya no hay
   razon economica para recortar el experimento; si algo, ahora se puede
   ampliar.

5. **La estrategia "menos llamadas y mas largas" pierde su base.** Nacia de la
   hipotesis de facturacion por tiempo o de un cargo plano por solicitud, ambas
   descartadas. El eje de ahorro pasa a ser el volumen de tokens, no el numero
   de llamadas.

## Alternativas

- **A. Mantener el numero de USD 0,23 y marcar la pregunta 1 como no
  concluyente** (rechazada). El techo de "< USD 0,01" sobre 169 solicitudes es
  un dato duro que descarta dos de las tres hipotesis por dos ordenes de
  magnitud. Declarar no concluyente algo que la medicion resuelve deja un
  supuesto falso circulando.

- **B. Explicar el USD 0,00 como "Featherless no factura a esta escala"**
  (rechazada como conclusion). Es una explicacion posible, pero **no es la mas
  parsimoniosa**: no hace falta postular una cuota gratuita cuando el modelo por
  token ya predice ~USD 0,003 para estas 169 solicitudes, un valor que tambien
  se muestra como USD 0,00. Queda anotada como ambiguedad residual abajo.

- **C. Seguir planificando con USD 0,0016 por llamada para no arriesgar** (rechazada).
  Sobrestima el costo 140x y llevaria a recortar un experimento que cuesta
  centavos.

- **D. Gastar mas para separar "por token" de "gratis a esta escala"**
  (rechazada). Separarlas exigiria generar mas de USD 0,01 de uso previsto por
  token, unas 150 llamadas largas, y **no cambia ninguna decision**: en ambos
  casos el barrido es practicamente gratis.

## Consecuencias

**Positivas**

- A25 queda desbloqueado sin restriccion economica. El riesgo del barrido no
  era el dinero, y ahora esta demostrado.
- `costo_estimado` en MLflow pasa a ser una metrica con base empirica.
- Se retira un numero falso antes de que llegue a la entrega final.

**A vigilar**

- **El model_card y el benchmark siguen citando el numero retirado** hasta que
  se corrijan. Es el riesgo mas concreto de este ADR.
- La ambiguedad residual (tarifa por token contra cuota gratuita) no afecta
  ninguna decision, pero conviene no presentar como "tarifa confirmada" lo que
  es "consistente con la tarifa publicada".

**Impacto en el equipo**

- R2 consume la metrica; los valores de `costo_estimado` quedan como estaban
  conceptualmente. El cambio de formula unificado es **inocuo hoy**, porque
  `cached_tokens` es 0 en este proveedor.
- Emitir el costo en la metadata gRPC (`x-cost-usd`) seria un cambio de
  contrato: queda propuesto, no implementado.
- R4 es dueno del `model_card` y tiene que aplicar la retraccion del punto 1.

## Pendiente de verificar

**1. Ambiguedad residual de la unidad de facturacion.** Los datos confirman que
el cargo **no** es plano ni por tiempo de computo, y que es **consistente con la
tarifa publicada por token**. No distinguen entre "se factura por token" y
"Featherless esta dentro de una cuota gratuita a esta escala". Se resolverse
requeriria generar mas de USD 0,01 de uso previsto (~150 llamadas largas), y no
cambia ninguna decision.

**2. La semantica de los cacheados.** Sigue inobservable mientras
`cached_tokens` sea 0. Se verifica el dia que se encienda el cacheo de prompt:
si el costo por llamada BAJA, los cacheados estaban incluidos en el prompt.

**3. La tarifa vigente de Featherless.** No se confirmo contra la pagina de
precios; los numeros usados son los que el equipo ya tenia (USD 0,17/M input,
USD 0,20/M output).
