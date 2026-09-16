# Benchmark real de Inference Providers — R1

**Fecha:** 2026-09-09 · **Autor:** R1 · **Alcance:** acceso autenticado, latencias, tokens y errores del router de Hugging Face con stream real.

## Resumen

Primer benchmark real del proyecto contra `router.huggingface.co` en formato OpenAI-compatible con `stream=True`. Se registran tiempos hasta el primer token (TTFT) y de generación total sobre 30 muestras, con 3 llamadas de calentamiento descartadas. La cuenta quedó sin créditos incluidos durante la medición (HTTP 402) y se reanudó tras comprar $5 de créditos prepagos.

## Método

- **Endpoint:** `POST https://router.huggingface.co/v1/chat/completions`
- **Modelo enrutado:** `Qwen/Qwen2.5-7B-Instruct:featherless-ai` (sufijo `modelo:proveedor`)
- **Parámetros:** `temperature=0.9`, `max_tokens=64`, `stream=true`, `stream_options.include_usage=true`
- **Prompt fijo:** "Responde en una sola frase: ¿qué harías esta noche?"
- **Muestras:** 30, precedidas de 3 de warm-up (descartadas)
- **Percentiles:** `ceil(p * n) - 1` en índice 0, según el criterio del plan (con 30 muestras, p95 = índice 28)
- **User-Agent explícito:** el router responde 403 HTML al UA por defecto de urllib

## Resultados

| Métrica | p50 | p95 | min | max | mean |
| --- | --- | --- | --- | --- | --- |
| TTFT (ms) | 605.9 | 1389.5 | 457.0 | 3933.4 | 795.0 |
| Total (ms) | 1483.9 | 2284.3 | 1303.8 | 4772.6 | 1679.3 |
| Completion tokens | — | — | — | — | 21.6 |

- Éxitos: 30/30 · Errores: 0 · Streams cerrados con `[DONE]`: 30/30.
- Reproducción: `uv run python scripts/benchmark_inference.py`

## Lectura para el contrato

- El p95 de TTFT (1.39 s) deja el deadline de R2 (8 s) **ajustado pero viable**: gran parte del presupuesto queda para la generación completa y el margen de guardas. Aun así, el máximo observado (3.93 s TTFT) y la varianza entre corridas (p95 total 2.3–4.1 s) recomiendan no apretar el deadline sin más evidencia.
- El primer disparo paga un warm-up notable (2.8 s en el spike vs 0.6 s posterior); la latencia informada es con endpoint caliente.
- El proveedor efectivo (`featherless-ai`) responde en español mezclando palabras en inglés ocasionalmente; la respuesta promedio supera las 15 palabras del juego, lo que refuerza la necesidad de la guarda de corte de R1.

## Costo y presupuesto

- El bucket gratuito (USD 0,10 mensuales, sujeto a cambio) se agotó con ~11 llamadas de este modelo (spike + warm-ups + primeras muestras). Es una observación de operación, no una tarifa por llamada.
- Se compraron **USD 5 de créditos prepagos** (decisión de R1, 2026-09-09) para completar la medición.
- **Costo medido (fuente: página de Billing, ventana 2026-09-01 a 2026-10-01):** USD 0,23 de Inference Usage por **143 solicitudes** a través de Featherless AI (Together AI: 0 solicitudes) → **~USD 0,0016 por llamada** efectivo con ~65 tokens/llamada. Saldo disponible: USD 5,00 (≈ 3 000 llamadas al ritmo actual).
- **Observación:** el costo medido del router HF es ~100× mayor que lo que sugiere la tarifa por token publicada por Featherless (USD 0,17/M input, USD 0,20/M output). La causa raíz no está confirmada; el número que gobierna la planificación es el medido por Billing. **Pendiente para el equipo:** entender la unidad real de facturación del router (posible componente por solicitud o por tiempo de cómputo además de los tokens).
- **Lección de metrología:** las páginas de HF pueden mostrar valores inconsistentes entre sí (Billing vs "Models breakdown" mostraron USD 0,89/<USD 0,01 en una lectura y USD 0,23/USD 0,18 en la siguiente tras 143 solicitudes). Para decisiones de dinero se usa Billing con su ventana de período explícita.
- Regla operativa adoptada: **no reintentar errores de autenticación ni crédito agotado** (HTTP 402); abortar y reportar.

## Límites de esta medición

- Un solo modelo, un solo proveedor, un solo prompt, un solo día y un solo nodo de salida. No es el barrido 3 × 3 del plan.
- No mide retransmisión, fallos intermedios de stream ni comportamiento bajo carga concurrente.