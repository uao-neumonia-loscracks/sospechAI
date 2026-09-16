# R1-5 · Integración E2E — Hallazgos

_Fecha: miércoles 16 de septiembre de 2026 · Autor: R1 (Juan Melendez)_

## Criterio de éxito

> Una partida de consola llega a REVELACION con al menos una respuesta
> generada por el engine real.

**CUMPLIDO** ✅

## Evidencia

- Engine real: `uv run python -m src.impostor_engine.serve --port 50051`
  (proceso en `[::]:50051`, `HealthCheck -> healthy: true, detail: "ok"`).
- Conductor: la demo del orquestador NO habla con el engine (usa respuestas
  simuladas), así que se escribió un conductor E2E específico en
  `scripts/e2e_real_engine.py` que une las tres piezas:
  - `EngineClient` real de R2 (`src.orchestrator.engine_client`),
  - reglas reales de `Game` (`src.orchestrator.game`),
  - engine real vía gRPC (`proto/impostor.proto`).
- Modelo solicitado: `Qwen/Qwen2.5-7B-Instruct:featherless-ai` (persona `p1`,
  prompt `v2`, `temperature=0.9`, `top_p=0.9`, `max_words=15`).
- Regeneración por quiebre de personaje: **OFF** (default de `serve.py`).

Salida de consola (2 rondas completas):

```
RONDA 1: Si se va la luz justo antes de entregar un trabajo, ¿qué harías?
  Jugador 1 (humano simulado): Intentaría compartir internet desde el celular...
  Jugador 2 (humano simulado): Me tocaría buscar una cafetería...
  Jugador 4 (IMPOSTOR, engine real): Buscar la iluminación paracaúas, o mejor
    aún, imprimir antes de apagarse el servicio.
  Jugador 3 (humano simulado): Primero revisaría la batería...

RONDA 2: ¿Qué comida escogerías después de una clase larga?
  Jugador 1: Una arepa con queso...
  Jugador 2: Yo pediría arroz con pollo...
  Jugador 4 (IMPOSTOR, engine real): Un pollo a la brasa con arroz y yuca,
    fácil y rico.
  Jugador 3: Preferiría una comida caliente...

REVELACION: el impostor era Jugador 4.
Puntajes: {'Jugador 1': 0, 'Jugador 2': 1, 'Jugador 3': 0}
Tasa de detección: 33.3%
Partida guardada: c8f48674-de80-4d81-9cfe-f4c40ccf890c en
  data/practice/partidas_e2e_real.sqlite3
```

## Hallazgos — lista completa (sin arreglar todavía)

### Bloqueantes
1. **Ninguno.** El handshake gRPC funcionó de primera: puerto correcto,
   stubs sincronizados (misma versión de `proto/`), cierre del stream con
   `is_final=true` y `text_delta=""` aceptado por `EngineClient`.

### No bloqueantes / observaciones
2. **La demo oficial del orquestador no usa el engine.** `src/orchestrator/demo.py`
   responde desde constantes `SCRIPTED_RESPONSES`; no hay ninguna ruta en el
   orquestador que llame a `apply_ai_turn`. Para la sustentación del 19, si la
   demo debe mostrar texto real, hace falta un conductor E2E como el de este
   archivo o integrar `apply_ai_turn` en la demo (decisión de R2/R1).
3. **Calidad de la respuesta de la ronda 1.** «Buscar la iluminación paracaúas»
   es semánticamente extraña (puede ser paráfrasis rara o alucinación leve del
   modelo). No es un fallo de integración; es calidad del modelo con el prompt
   y temperatura actuales. Anotado para revisar prompt/parámetros si mejora la
   tasa de detección (no es objetivo de R1-5).
4. **Cosmética de consola en Windows:** acentos y «¿» se mostraron como
   caracteres corruptos (`Regeneraci�n`) por la codificación de la consola
   PowerShell; los datos persistidos en SQLite están bien (UTF-8). No afecta
   al criterio.
5. **El stream real no entrega trailing metadata visible desde el script de
   consola de R1** (los metadatos viven en el canal; el test
   `test_trailing_metadata_reaches_r2_stub` ya los valida). Para la demo no
   hace falta.
6. **`save_practice_game` guardó la partida E2E como sesión `simulacion`.**
   Es la clasificación correcta según `storage.py`; el resultado real (sin
   interrupción) quedó en `valid_game=true`.

## Priorización propuesta

- [ ] Decidir: ¿la demo del 19 usa este conductor E2E o se integra
      `apply_ai_turn` en `demo.py`? (afecta a R2)
- [ ] Decidir: ¿ajustar prompt/temperatura tras ver la respuesta de ronda 1?
- [ ] Nada más impide repetir la partida E2E.