# ADR-001 - Inferencia remota desde impostor-engine

**Fecha:** 2026-09-09 · **Estado:** aceptada por instrucción de Natalia; revisión conjunta pendiente
**Decide:** Natalia para el alcance de esta rama · **Consultado:** R1, R3 y R4 pendientes

## Contexto

La propuesta del Módulo 2 describía GGUF en el Droplet. Natalia confirma que el equipo cambia a API para evitar alojar el modelo allí. Aún no hay comparación medida de costos ni resultados de A2.

## Decisión

Mantener el servicio gRPC `impostor-engine` y realizar desde él las llamadas HTTP a Inference Providers de Hugging Face. R2 mantiene gRPC; el token queda en R1.

## Alternativas descartadas

- Modelo local en el Droplet: fuera del alcance indicado por su costo.
- Llamada directa desde UI/R2: acopla las reglas al proveedor y dispersa credenciales.
- Fallback local automático: no solicitado; no se incorpora ni se confunde con la simulación.

## Consecuencias

R1 confirma proveedor, latencia, cuotas y presupuesto. A1/A2 pasan a medir API; A22 debe replantearse y A20 dimensionarse con mediciones del resto de servicios y del Runner. A27 protege el token. Estos tickets no se editan desde esta rama.

R2 añade deadline y cierre por fallo: revela la IA y excluye la partida del cálculo de detección. Los campos nuevos del proto son una propuesta aditiva, sin congelar A6. No se han medido cargos, realizado experimentos humanos ni enviado mensajes al docente.
