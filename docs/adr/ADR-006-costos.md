# ADR-006 - Unidad de facturacion del router y presupuesto del barrido

**Fecha:** 2026-09-17 · **Estado:** propuesta
**Decide:** R1, con visto bueno del equipo para el presupuesto del barrido A25 · **Propone:** R1 · **Consultado:** R2 (consume la metrica de costo), pendiente

## Contexto

El numero medido que gobierna la planificacion hoy es **USD 0,23 por 143
solicitudes** a Featherless AI, segun la pagina de Billing con ventana
2026-09-01 a 2026-10-01. Eso da **~USD 0,0016 por llamada** con ~65 tokens por
llamada.

Ese numero es **dos ordenes de magnitud mayor** que lo que predice la tarifa
publicada por token (USD 0,17/M input, USD 0,20/M output). La causa quedo sin
confirmar desde el benchmark de R1 del 2026-09-09 y condiciona directamente el
tamano del barrido experimental de A25: **9 configuraciones x 10 partidas x 6
llamadas = 540 llamadas**.

La tarjeta A13 hace que el orquestador loguee la metrica `costo_estimado` en
MLflow. Si la formula que la alimenta no representa el cargo real, la metrica
miente y el equipo decide con un numero inventado.

Este ADR existe para responder tres preguntas del ticket R1-9 y para dejar la
formula de costo en un solo lugar.

## Lo que se verifico

| # | Afirmacion | Evidencia |
| --- | --- | --- |
| 1 | El proveedor efectivo es el que creemos | Billing: 143 solicitudes a Featherless AI, 0 a Together AI |
| 2 | El cargo no se explica por tokens | Describe 138x menos de lo cobrado |
| 3 | La facturacion por tiempo de computo existe en la plataforma | Documentacion de HF Inference Providers |
| 4 | El log de observabilidad por peticion no existe como artefacto | `benchmark_inference.py` imprime a stdout y no persiste nada |
| 5 | Billing no permite desglosar por peticion | La vista de HF desglosa por modelo y proveedor |
| 6 | El engine y `src/common/metrics.py` facturan distinto | Dos formulas divergentes en el codigo |

### 1. El proveedor efectivo si es el esperado (pregunta 3 de R1-9)

Billing muestra **143 solicitudes a Featherless AI y 0 a Together AI**. No hay
reenvio silencioso a un proveedor mas caro. Coincide con lo que el engine
reporta en `x-model-id` (`Qwen/Qwen2.5-7B-Instruct:featherless-ai`).

**Pregunta 3: respondida. No hay desvio de proveedor.**

### 2. El cargo no se explica por tokens

El benchmark midio ~65 tokens por llamada (~43 de prompt + 21,6 de completion).
A las tarifas publicadas:

```
(43,4 x 0,17 + 21,6 x 0,20) / 1_000_000 = USD 0,0000117 por llamada
143 x USD 0,0000117                      = USD 0,0017 total
```

Se cobraron **USD 0,23**. El modelo por token predice **USD 0,0017**: se queda
corto por un factor de **~138x**. El informe previo decia "~100x" como orden de
magnitud; el calculo exacto da ~138x.

Con el limite de que la ventana de Billing incluye tambien el spike, los
warm-ups y las pruebas de Docker y E2E, no solo las 30 muestras del benchmark.
Eso cambia el tiempo promedio por llamada, pero no cambia el hecho de que el
total esta dos ordenes por encima de lo que predice la tarifa por token.

**Conclusion: el modelo por token no describe el cargo.**

### 3. Los datos para el cruce que pedia el ticket no existen

El ticket R1-9 pedia cruzar el log de observabilidad contra el detalle de las
143 peticiones en Billing. Se verifico y **ese cruce no es posible**:

- `scripts/benchmark_inference.py` imprime el resumen JSON a stdout y **no
  persiste nada por peticion**. No hay escritura a archivo en todo el script.
- No existe ningun `.log`, `.jsonl` ni `.csv` con las peticiones, ni en el repo
  ni en el arbol local de trabajo.
- La vista de Inference Providers de Hugging Face desglosa el uso **por modelo y
  proveedor**, no por solicitud. El detalle por peticion que el ticket suponia
  tampoco existe del lado de Billing.

**Pregunta 1 del ticket ("el costo varia con los tokens o es plano"): no es
respondible con los datos existentes.** Requiere un experimento nuevo. Queda
propuesto abajo.

### 4. Hipotesis compatible: facturacion por tiempo de computo

La plataforma documenta que la facturacion puede ir por **tiempo de computo x
precio del hardware** (el ejemplo que da HF es una peticion de 10 s en una GPU
de USD 0,00012/s facturada USD 0,0012).

Con los tiempos medidos del benchmark:

```
Commit total: 143 x 1,6793 s = 240,1 s
USD 0,23 / 240,1 s          = USD 0,00096/s  =  USD 3,45 por hora de GPU
```

Esa tarifa es **~8x la del ejemplo de hardware que documenta HF**
(USD 0,00012/s). Es compatible en orden de magnitud, pero **no se confirma** con
los datos disponibles.

Una alternativa **igualmente compatible** es un **cargo plano por solicitud** de
USD 0,0016. Ambas explican el total perfectamente y **no se distinguen entre si**
sin un experimento controlado.

### 5. Prompt vs completion (pregunta 2 de R1-9)

El ticket asume que el prompt puede ser ~85% del gasto.

- **Bajo facturacion por token esa aritmetica es correcta**: con un system
  prompt de ~120 tokens y una respuesta de ~20,
  `(120 x 0,17) / (120 x 0,17 + 20 x 0,20) = 83,6%`.
- Pero el modelo por token es justamente el que falla por 138x, asi que ese 85%
  **no esta verificado**.
- Lo que **si** esta medido: **TTFT = 795,0 ms de 1679,3 ms = 47,3% del tiempo
  por llamada ocurre antes del primer token**. La generacion (884,3 ms para 21,6
  tokens, ~24 tokens/s) es el 52,7% restante.

**Pregunta 2: respondida con el matiz del modelo.** Si el cargo es por tiempo,
la fraccion que domina no es el prompt (85%) sino el tiempo previo al primer
token (47%), y recortar respuestas ayuda **menos** de lo que sugiere el ticket.

### 6. Dos formulas de costo divergentes en el mismo repo

| | `src/impostor_engine/inference_client.py` | `src/common/metrics.py` |
| --- | --- | --- |
| Unidad | USD por **1M** | USD por **1K** |
| Cacheados | Se **suman** al prompt completo | Se **restan** del prompt facturable |
| Tarifas | Constantes fijas | Parametro `Pricing` |

La convencion OpenAI-compatible (el engine pega contra
`https://router.huggingface.co/v1`) incluye los tokens cacheados **dentro** de
`prompt_tokens`. Por lo tanto la formula del engine **cobra los cacheados dos
veces**, y `src/common/metrics.py` es la correcta.

Ademas, `servicer.py` lee `usage.get("cached_tokens", 0)` con la clave plana,
cuando la convencion OpenAI-compatible la anida en
`prompt_tokens_details.cached_tokens`. Si eso es asi, los cacheados valen 0 hoy
y el doblecobro esta **latente**: se activa el dia que se encienda el cacheo de
prompt, que es justamente la mitigacion que sugiere el ticket. **Este ADR no
asume esa forma sin verificarla.**

Hay una tercera consecuencia: **el engine calcula `cost_usd` en
`servicer.py:338` pero no lo emite en la metadata** (la lista manda
`x-usage-*` y `x-latency-*`, sin costo), por eso el orquestador tuvo que
recalcularlo. Eso es lo que creo la duplicacion.

## Decision propuesta

1. **El numero que gobierna la planificacion es el medido, no el estimado.**
   Hasta nueva medicion, el presupuesto se calcula con **USD 0,0016 por
   llamada**. `costo_estimado` se reporta como estimacion por token, nunca como
   el cargo real.

2. **Una sola fuente de verdad para la formula de costo**:
   `src/common/metrics.py`. El engine la importa (AGENTS.md lo permite
   explicitamente) y se elimina su copia local: `estimate_cost_usd` y las tres
   constantes de `inference_client.py`.

3. **Tarifas canonicas en USD por 1K**, tomadas del engine y convertidas:
   prompt `0,00017` · completion `0,0002` · cached `0,000136`. Con eso `Pricing`
   puede tener valores por defecto, que es lo que hoy bloquea su comentario
   "los valores reales los fija el ADR-006, que todavia no existe".

4. **Los cacheados se facturan una sola vez**:
   `billable_prompt = prompt_tokens - cached_tokens`. Es la unica formula
   coherente con la convencion OpenAI-compatible.

5. **El barrido A25 es pagable.** 540 llamadas x USD 0,0016 = **USD 0,86**
   contra **USD 5,00** de saldo: **~5,8x de margen**. El saldo alcanza para
   ~3.125 llamadas. El riesgo del barrido **no es el dinero**.

6. **Antes de comprometer el barrido, una prueba controlada de ~USD 0,40 que
   decida la unidad de facturacion.** La pregunta 1 no se puede contestar con lo
   que hay, y la respuesta cambia la estrategia de A25.

## Alternativas

- **A. Dejar las dos formulas como estan** (rechazada). Dos implementaciones del
  mismo concepto que dan numeros distintos para la misma llamada es un defecto,
  y el doblecobro de cacheados se activa en cuanto se encienda el cacheo.

- **B. Seguir planificando con el modelo por token** (rechazada). Predice 138x
  menos de lo que se cobra. Planificar el barrido con ese numero llevaria a
  creer que 540 llamadas cuestan USD 0,0063.

- **C. Adoptar el modelo por tiempo de computo como verdad** (rechazada por
  ahora). Es compatible con los datos, pero ~8x el ejemplo documentado por HF y
  sin confirmacion de la tarifa de Featherless. Adoptarlo seria cambiar un
  supuesto no verificado por otro.

- **D. Adoptar un cargo plano por solicitud** (rechazada por ahora). Igual de
  compatible con el total que la hipotesis por tiempo, e igual de no confirmada.

- **E. Reducir el barrido de A25 para gastar menos** (rechazada). Con 5,8x de
  margen, recortar el experimento cambiaria valor cientifico por un ahorro de
  centavos.

## Consecuencias

**Positivas**

- `costo_estimado` pasa a ser una metrica con una unica formula, testeable y
  coherente con la convencion del proveedor.
- A25 queda desbloqueado con un presupuesto defendible: ~USD 0,86 de USD 5,00.
- El ADR deja por escrito que el cruce que pedia el ticket no era posible, para
  que nadie lo vuelva a intentar con los mismos datos.

**A vigilar**

- Si el cargo es por tiempo, la estrategia correcta es **menos llamadas y mas
  largas** (amortizar el 47,3% de tiempo previo al primer token) y **cacheo de
  prompt** para recortar el prefill. Recortar respuestas ayuda menos de lo que
  sugiere el ticket.
- Si el cargo es **plano por solicitud**, nada de lo anterior importa: solo
  importa el numero de llamadas, y ahi el barrido de 540 se vuelve mas caro de
  lo previsto.
- El benchmark midio con un **prompt fijo de ~43 tokens**. El juego real usa un
  system prompt de ~120 tokens y puede regenerar. Si el cargo es por tiempo, la
  sensibilidad al tamano del prompt es baja; si es plano, nula. Igual conviene
  **re-medir una partida real** antes de comprometer el barrido.
- La pagina de Billing ya mostro **lecturas inconsistentes** entre si (Billing
  vs "Models breakdown"). La prueba controlada tiene que leer Billing con su
  ventana de periodo explicita y contrastar con el numero de solicitudes.

**Impacto en el equipo**

- R2 consume la metrica; el cambio de formula y las tarifas por defecto le
  cambian los valores de `costo_estimado` en MLflow (a la baja, porque los
  cacheados se descuentan).
- Emitir el costo en la metadata del engine (`x-cost-usd`) seria un cambio de
  contrato gRPC y **no se hace en este ADR**: queda propuesto para que R1 y R2
  lo acuerden.

## Pendiente de verificar

Este ADR **no asume** la unidad real de facturacion del router, ni la tarifa de
Featherless, ni que `cached_tokens` llegue anidado. Queda propuesto:

**Prueba controlada (~USD 0,40):** 20 llamadas con `max_tokens=8` contra 20
llamadas con `max_tokens=512`, mismo prompt y mismo modelo. Si los dos grupos
cuestan lo mismo, el cargo es **plano por solicitud**. Si el grupo largo cuesta
mas, el cargo es **proporcional a tokens o a tiempo**. Se lee el delta en
Billing con su ventana de periodo explicita.

**Verificacion de la forma de `usage`:** una sola llamada con
`stream_options.include_usage=true`, registrando el objeto `usage` crudo, para
confirmar si los cacheados vienen en `prompt_tokens_details.cached_tokens`. Hoy
`sentencia` no se puede confirmar ni refutar desde el repo.
