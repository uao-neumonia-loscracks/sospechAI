# Proposal: R3-1 — Flujo de partida en la UI (consentimiento, lobby, sala de chat, votación)

## Intent

La UI es la única superficie visible del juego SospechAI durante el piloto. Sin la pantalla de consentimiento no existe partida válida para el experimento: el piloto exige que cada participante acepte (a) que otro participante puede ser un modelo de lenguaje y (b) que la conversación se registra con fines de investigación, ANTES de entrar al lobby. Además, el piloto (lo conduce R3 la noche del miércoles 16) requiere que un ser humano pueda unirse a una partida sin aportar datos personales: el alias lo impone el servidor ("Jugador N") y el límite de palabras lo aplica el orquestador. Esta propuesta define el esqueleto navegable de las cuatro pantallas (consentimiento, lobby, sala de chat, votación) y el contenido mínimo de cada una, contra el contrato `docs/CONTRATO_UI_ORQUESTADOR.md` v1.0.

## Scope

### In Scope

- Pantalla de CONSENTIMIENTO antes del lobby, con texto fijo de los dos avisos (participante puede ser un modelo de lenguaje; la conversación se registra con fines de investigación) y botón de aceptar. Sin aceptar no se entra. No es opcional ni configurable.
- Lobby: el servidor asigna el alias generado ("Jugador N"); cero datos personales (ni nombre real ni correo).
- Sala de chat: mensajes con alias, campo de entrada, contador de palabras en vivo que bloquea el envío localmente al superar el límite. El límite real lo impone el orquestador (el bloqueo de la UI es local y evidente; la autoridad está en el orquestador).
- Actualización de estado por polling corto contra el orquestador (contrato: `GET /rooms/{room_code}/state`; polling 1 s en RONDA/DISCUSION/VOTACION, 2-3 s en LOBBY/REVELACION).
- Orden de entrega del esqueleto: PRIMERO navegación entre las cuatro pantallas (consentimiento, lobby, sala, votación), DESPUÉS el contenido de cada una. "DEBES VER": las cuatro pantallas navegables aunque estén vacías por dentro.
- Vista de VOTACIÓN vacía (solo navegación): la lógica y la revelación con resultados son R3-2.
- Fuente de datos Plan B: implementación fake en memoria que respete las formas del contrato (misma máquina de estados congelados `LOBBY → RONDA → DISCUSION → VOTACION → REVELACION` y mismos valores de cable); cuando exista el servidor HTTP del orquestador se cambia la fuente de datos sin tocar las pantallas.
- Añadir `streamlit` como dependencia del proyecto (pyproject.toml + uv.lock).
- Pruebas de componentes de UI: ≥3 pruebas con estructura Arrange-Act-Assert sobre el contador de palabras y la transición entre pantallas.

### Out of Scope

- R3-2: lógica de votación, resultados y pantalla de revelación con contenido.
- MLflow (R1) y Docker (R4).
- Tiempos y vencimientos del juego; reglas de juego; lógica de orquestador.
- Cualquier comunicación directa UI → engine por gRPC.
- Implementación del servidor HTTP del orquestador (R2).
- Persistencia de datos de la partida en la UI.

## Capabilities

> Esta sección es el CONTRATO entre proposal y specs.
> `openspec/specs/` está vacío (solo `.gitkeep`): no hay capacidades existentes que modificar.

### New Capabilities

- `ui-flujo-partida`: cubre la pantalla de consentimiento obligatoria, el lobby con alias generado por el servidor, la sala de chat con alias y contador de palabras que bloquea el envío local, la vista de votación vacía (navegación), el polling corto de estado contra el orquestador y la fuente de datos (fake in-memory conforme al contrato, intercambiable por HTTP real).

### Modified Capabilities

- None — no hay specs existentes en `openspec/specs/` (carpeta vacía).

## Approach

Entregar en dos fases dentro del mismo cambio:

1. **Esqueleto primero**: `src/ui/app.py` con router por `session_state` de Streamlit (evita `st.navigation`/`pages/` para que el consentimiento no se pueda saltar por URL) y cuatro pantallas como funciones puras en `src/ui/screens/` (consent.py, lobby.py, chat.py, voting.py), navegables end-to-end aunque estén vacías por dentro.
2. **Contenido por pantalla**: implementar cada pantalla contra `src/ui/api.py`, única boca de la UI con el orquestador. `api.py` tiene doble implementación: cliente HTTP con stdlib `urllib` contra el contrato (`GET /rooms/{room_code}/state`) y `FakeSospechAI` in-memory que respeta las formas del contrato (estados congelados y valores de cable). El polling corre por `st.fragment` con frecuencias según estado (1 s en RONDA/DISCUSION/VOTACION; 2-3 s en LOBBY/REVELACION).

Decisiones pendientes §14/§15 resueltas con los defaults aceptados por R3: polling 1 s/2-3 s; sin nombre visible elegido por el cliente; IA anónima e idéntica (sin etiqueta "IA" ni énfasis de posición); cierre de sala = detectar `state == "REVELACION"` en un poll. La UI solo muestra y envía: no decide reglas, tiempos ni votos.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/ui/app.py` | New | Router por `session_state`; arranque de la app Streamlit. |
| `src/ui/screens/consent.py` | New | Pantalla de consentimiento obligatorio (bloquea el paso al lobby sin aceptar). |
| `src/ui/screens/lobby.py` | New | Lobby: alias "Jugador N" generado por el servidor; sin datos personales. |
| `src/ui/screens/chat.py` | New | Sala de chat: mensajes con alias, campo de entrada, contador en vivo que bloquea el envío sobre el límite. |
| `src/ui/screens/voting.py` | New | Vista de votación vacía (navegación); contenido es R3-2. |
| `src/ui/api.py` | New | Única boca con el orquestador: HTTP stdlib `urllib` + `FakeSospechAI` in-memory conforme al contrato. |
| `pyproject.toml` | Modified | Añade `streamlit` a `dependencies` (+ `uv.lock`). |
| `tests/test_ui_*.py` | New | ≥3 pruebas AAA: contador de palabras y transición entre pantallas. |
| `docs/` | Modified (maybe) | Bitácora del piloto si aplica (no bloqueante). |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| El servidor HTTP del orquestador aún no existe en main | Med | Plan B: fake in-memory que respeta las formas del contrato (estados y valores de cable); el cambio de fuente de datos es un swap localizado en `api.py`. |
| `streamlit` es dependencia nueva en el entorno uv | Low | Avisar al grupo el mismo día (regla del equipo); tras la entrega se revisan `pyproject.toml` y `uv.lock` en PR. |
| El contador de la UI puede divergir del límite del orquestador | Med | El orquestador es autoritativo; la UI solo hace bloqueo local evidente; el envío se rechaza en el backend si excede el límite real. |
| `streamlit`/`.venv` en entorno uv en Windows | Low | Instalar solo vía `uv` (prohibido pip directo); `.venv` ya está excluido del versionado. |

## Rollback Plan

La UI es aditiva: no toca `src/orchestrator/` ni `src/impostor_engine/`, por lo que revertir no afecta al motor ni al orquestador.

1. `git revert` del commit que añade `streamlit` en `pyproject.toml` y `uv.lock`, luego `uv sync` para restaurar el entorno.
2. Eliminar `src/ui/` (nueva) y `tests/test_ui_*.py` (nuevos).
3. Verificar con `git status --short` que solo quedan cambios no deseados revertidos y que los árboles del orquestador y del engine quedan intactos; `uv run pytest` en verde.

No hay migración de datos: ninguna pantalla persiste estado de partida.

## Dependencies

- Contrato UI-Orquestador `docs/CONTRATO_UI_ORQUESTADOR.md` v1.0 (existente, PR #36): fuente de verdad de la interfaz.
- Servidor HTTP del orquestador (pendiente, R2): cubierto por el Plan B (fake in-memory) hasta que exista.
- Decisiones §14/§15 con defaults ya aceptados por R3 (polling, alias, IA anónima, cierre por fetch del estado final).
- Agregar `streamlit` a `pyproject.toml` + `uv.lock` (aviso al grupo el mismo día).

## Success Criteria

- [ ] `uv run streamlit run src/ui/app.py` arranca sin errores.
- [ ] Las 4 pantallas (consentimiento, lobby, sala, votación) son navegables end-to-end desde el esqueleto.
- [ ] No se puede entrar al lobby sin aceptar el consentimiento (ni por URL).
- [ ] El alias visible es "Jugador N" generado por el servidor; no se piden datos personales.
- [ ] El contador de palabras bloquea el envío al superar el límite establecido.
- [ ] El estado se actualiza por polling corto con las frecuencias del contrato (1 s en juego, 2-3 s en lobby/revelación).
- [ ] ≥3 pruebas con estructura AAA sobre el contador y la transición entre pantallas, todas en verde.
- [ ] Cero warnings: pytest corre con `filterwarnings = ["error"]`.
- [ ] `uv run ruff check` y `uv run black --check` limpios en el código nuevo.
- [ ] `git status --short` sin cambios no deseados (solo lo planificado en Affected Areas).