# Model Card: el impostor de SospechAI

**Versión de la tarjeta:** 1.0 · **Fecha:** 2026-09-17 · **Responsable:** R4 · **Ticket:** A11

Esta tarjeta describe el modelo de lenguaje que hace de "impostor" en
SospechAI, tal como está configurado hoy en el repositorio. No es la tarjeta
del modelo base: esa la publica su autor en el Hub. Aquí se documenta **cómo
lo usa este proyecto**.

## 1. Identificación

| Campo | Valor | Cómo se verificó |
|---|---|---|
| Modelo | `Qwen/Qwen2.5-7B-Instruct` | `scripts/benchmark_inference.py`, `scripts/spike_inference.py`, `docs/verificaciones/2026-09-09-benchmark-r1.md` |
| Revisión en el Hub | `a09a35458c702b33eeacc393d103063234e8bc28` (última modificación 2025-01-12) | API del Hub, consultada el 2026-09-17 |
| Autor | Qwen (Alibaba Cloud) | Ficha del Hub |
| Modelo base | `Qwen/Qwen2.5-7B` | `cardData.base_model` de la ficha |
| Tamaño | 7,61 B parámetros (6,53 B sin embeddings) | README de la ficha |
| Contexto | 131 072 tokens declarados; `config.json` fijado en 32 768 | README de la ficha |
| Proveedor de inferencia | Featherless AI, vía el router de Hugging Face (`router.huggingface.co/v1`, OpenAI-compatible) | Mapeo `inferenceProviderMapping.featherless-ai`: `status: live`, `task: conversational` |
| Identificador enviado | `Qwen/Qwen2.5-7B-Instruct:featherless-ai` (sufijo `modelo:proveedor`) | Código de R1 |
| Acceso | Remoto por HTTP desde `impostor-engine`. Ningún peso se descarga ni se aloja en el proyecto (ADR-001) | `src/impostor_engine/inference_client.py` |

**Estado: modelo en uso, no confirmado como definitivo.** La tarjeta A11 exige
evaluar al menos dos modelos contra el set de 100 pares (A4), y ninguna de las
dos cosas existe todavía. Hasta entonces, "definitivo" no es un dato
verificado. El `model_id` viaja en cada `GenerationConfig`, así que cambiar de
modelo no requiere tocar el orquestador ni el `.proto`.

## 2. Licencia

**Apache License 2.0.** Verificada el 2026-09-17 por dos vías:

- Metadatos del Hub: etiqueta `license:apache-2.0` y `cardData.license: apache-2.0`.
- Archivo de licencia del repositorio del modelo:
  <https://huggingface.co/Qwen/Qwen2.5-7B-Instruct/blob/main/LICENSE>. El
  encabezado dice "Apache License, Version 2.0, January 2004".

El modelo no es *gated*. Apache 2.0 permite el uso académico y comercial y
exige conservar el aviso de licencia al redistribuir pesos. Este proyecto no
redistribuye pesos, solo consume la API.

> Ojo: otros tamaños de la familia Qwen2.5 tienen licencias distintas. Si el
> equipo cambia de modelo, esta sección se vuelve a verificar; no se hereda.

## 3. Uso previsto

- Generar **una respuesta breve por ronda** (máximo 15 palabras) en un chat
  grupal, haciéndose pasar por un jugador humano más.
- Servir como **estímulo experimental**: la variable que se mide es si los
  humanos detectan el texto generado. La variable independiente es la versión
  del prompt de sistema (v1, v2 y v3, en `docs/prompts/`).
- Solo participantes que **aceptaron un consentimiento** que avisa que uno de
  ellos puede ser un modelo de lenguaje. Toda partida termina en una
  **revelación obligatoria**.

## 4. Usos fuera de alcance

- Suplantar personas fuera del juego, o en cualquier contexto sin
  consentimiento previo y revelación posterior.
- Conversaciones largas o de varios turnos libres. El sistema solo está
  probado para respuestas de hasta 15 palabras.
- Decisiones sobre personas: evaluar, calificar o perfilar a los jugadores.
- Sacar conclusiones de detección de IA para otros idiomas, registros o
  longitudes de texto.
- Asesoría factual. El modelo inventa detalles de "su vida" por diseño (v2 y v3).

## 5. Parámetros de generación usados

| Parámetro | Valor | Dónde se fija |
|---|---|---|
| `temperature` | 0,9 | `GenerationConfig` enviada por el orquestador |
| `top_p` | 0,9 | `GenerationConfig` |
| `max_words` | 15 | `GenerationConfig`; lo aplican a la vez la guarda del engine y la regla del `Game` |
| `max_tokens` | `max_words × 3 + 8` = 53 | `src/impostor_engine/servicer.py` |
| `stream` | `true`, con `stream_options.include_usage` | `inference_client.py` |
| Deadline por respuesta | `min(8 s, ventana restante de la ronda)` | `serve.py` (`round_timeout=8.0`) y `apply_ai_turn` |
| Ventana de ronda | 20 s (provisional, ADR-003) | `Game(round_timeout=20.0)` |
| `system_prompt_version` | `v1` neutro, `v2` persona, `v3` imperfección deliberada | `docs/prompts/` y su copia en `src/impostor_engine/prompts/` |
| Persona | `personas.json` (alias, edad, ciudad, ocupación) | `src/impostor_engine/personas.json` |
| `regenerate_on_character_break` | **Apagado** para el piloto y la demo | Decisión del equipo (plan de cierre, R1-3) |
| Reintentos | Uno, solo ante fallo de red antes de enviar; nunca ante 4xx/5xx | `inference_client.py` |

## 6. Limitaciones conocidas en español coloquial colombiano

Lo observado hasta hoy. **No hay evaluación cuantitativa todavía**: el set de
100 pares (A4) no existe. Esta sección se actualiza con el barrido (A25).

- **Mezcla palabras en inglés** de vez en cuando (benchmark de R1, 2026-09-09).
- **Se pasa de 15 palabras** en promedio (~21,6 tokens de salida en el
  benchmark). La guarda del engine corta en `max_words`. El corte puede dejar
  frases truncadas, que un humano puede leer como señal.
- **Rompe personaje** con frases como "soy una IA" o "como modelo de
  lenguaje". Hay un detector de 24 patrones (`character_break.py`), pero con la
  regeneración apagada la respuesta rota **se publica igual**. La tasa se
  registra como `x-character-break`; todavía no se ha medido en partidas reales.
- **Regionalismos:** los prompts piden "español coloquial de Colombia" y v3
  sugiere expresiones ("parce", "sisas"). Falta evaluar si el modelo las usa
  con naturalidad o de forma caricaturesca. Es la primera hipótesis a revisar
  en el piloto (A16).
- **El README del modelo declara soporte multilingüe con español**, pero el
  campo `language` de sus metadatos solo lista `en`. No hay benchmark público
  de español coloquial colombiano. Por eso existe A4.
- **Latencia:** TTFT p95 de 1,39 s y total p95 de 2,28 s con el endpoint
  caliente. El primer llamado paga un warm-up de unos 2,8 s. Cabe en el
  deadline de 8 s, pero no se midió bajo carga concurrente.
- **Costo:** unos USD 0,0016 por llamada según Billing (143 solicitudes), cerca
  de 100 veces lo que sugiere la tarifa publicada por token. La causa está
  **sin confirmar** (R1-9, ADR-006 pendiente). Esto condiciona el tamaño del
  barrido experimental.

## 7. Consideraciones éticas: engaño controlado

El proyecto engaña a propósito: los participantes no saben cuál jugador es el
modelo. Lo que lo hace aceptable es que el engaño está **acotado, anunciado y
deshecho**:

1. **Consentimiento previo.** La pantalla de consentimiento va antes del lobby
   (regla de `AGENTS.md`). Dice que uno de los participantes *puede* ser un
   modelo de lenguaje y que la conversación se registra con fines de
   investigación. Sin aceptar, no se entra.
2. **Revelación obligatoria.** La revelación es un **estado** de la máquina
   (`REVELACION`), no una bandera configurable. Toda partida termina ahí,
   incluidas las interrumpidas por fallos técnicos. Muestra quién era el
   impostor y cómo votó cada quien. Mostrar también la versión del prompt
   usada está pendiente en la UI (R3-2, A14).
3. **Datos mínimos.** Los jugadores reciben alias generados ("Jugador N"). No
   se piden nombre real ni correo. Las transcripciones se guardan anonimizadas.
4. **Sin manipulación fuera del juego.** Los prompts limitan al modelo a
   responder la pregunta de la ronda. No persuade, no pide datos ni opina sobre
   personas reales.
5. **Fallos honestos.** Si el engine falla, la partida se revela y se marca
   inválida. Nunca se inventa una respuesta de reemplazo ni se cuenta como
   detección.

**Riesgos residuales:** un participante puede sentirse incómodo al descubrir
que no detectó al modelo. La revelación debe presentarse como un resultado del
experimento, no como un error de la persona. Además, las respuestas generadas
pueden contener estereotipos regionales; el piloto debe anotarlos.

## 8. Pendientes de verificación

| Qué | Dónde mirar | Responsable |
|---|---|---|
| Evaluación contra el set de 100 pares y comparación con un segundo modelo | A4, A11 | R1 + R3 |
| Tasa real de ruptura de personaje en partidas | MLflow, métrica `tasa_ruptura_personaje` (A13) | R1 |
| Causa del costo por llamada | ADR-006 (pendiente), R1-9 | R1 |
| Tarifa vigente de Featherless en el router | <https://huggingface.co/docs/inference-providers/pricing> | R1 |
| Benchmarks públicos del modelo | No se citan aquí porque no se verificaron. Ver <https://qwenlm.github.io/blog/qwen2.5/> | R4 |
