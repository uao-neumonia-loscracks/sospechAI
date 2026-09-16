# ADR-003 - Ventanas y cierre ante fallos de inferencia

**Fecha:** 2026-09-09 · **Estado:** propuesta
**Decide:** R2 propone · **Consultado:** R1 y equipo pendientes

## Contexto

La API añade latencia y errores externos. Esperar indefinidamente o contar una avería como detección humana perjudica el experimento.

## Decisión

Proponer una ventana configurable de 20 s por ronda y un RPC de hasta 8 s, limitado al tiempo restante. Publicar únicamente streams completos. Ante fallo, revelar la IA y marcar interrupción sin tasa de detección.

## Alternativas descartadas

- Espera ilimitada: puede bloquear la partida.
- Respuesta inventada de sustitución: cambia el tratamiento experimental.
- Pregeneración con historia incompleta: cambia la información disponible para la IA.

## Consecuencias

A2 debe aportar datos antes de aceptar estos valores. La demo didáctica desactiva la ventana. Faltan el temporizador activo, los límites de discusión/votación y la política de reconexión o reinicio. Dos rondas y 15 palabras son valores del ejemplo. Las decisiones pueden revisarse mediante otro ADR.
