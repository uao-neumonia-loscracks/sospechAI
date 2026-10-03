# Reporte final — SospechAI

**Grupo 2** · Módulo 4 · 2026-10-02 · Repo: `jcmt-group/sospechAI` (GitLab)

## 1. Pregunta de investigación

¿Pueden los humanos detectar texto generado por IA en una conversación corta
en español coloquial colombiano? El proyecto la operacionaliza como un juego:
humanos y una IA impostora responden las mismas preguntas de ronda (máximo 15
palabras), debaten, votan al impostor y terminan en una revelación obligatoria.
La variable medida es la **tasa de detección del grupo** por partida
(`docs/model_card.md`, sección 3).

## 2. Qué se construyó

Tres servicios desplegados automáticamente en un Droplet de DigitalOcean
(Ubuntu 22.04, 4 GB, http://198.211.107.154):

| Servicio | Rol |
|---|---|
| `impostor-ui` | Frontend Streamlit (consentimiento → lobby → sala → votación → revelación). Solo habla HTTP con el orquestador. |
| `impostor-orchestrator` | Servidor HTTP del contrato UI-orquestador: reglas, rondas, votos, revelación, SQLite y tracking MLflow. |
| `impostor-engine` | Servicio gRPC que genera las respuestas del impostor llamando a la Inference API de Hugging Face (router → Featherless AI). No conoce reglas del juego. |

Diagramas y despliegue: [docs/arquitectura.html](docs/arquitectura.html) ·
[docs/despliegue.md](docs/despliegue.md). El CI/CD (GitLab CI + runner `shell`
en el propio Droplet) corre test en toda rama, build y deploy solo en `main`,
con smoke test y rollback automático ante fallo.

## 3. Decisiones de diseño principales

| Decisión | ADR |
|---|---|
| Inferencia remota por API en vez de modelo local GGUF | ADR-001 |
| Parámetros de juego: ventana de 20 s, deadline de 8 s, interrupción sin tasa inventada | ADR-003 |
| Costo: cargo por token, anomalía de ~100x retirada (era una lectura errónea) | ADR-006 |
| Tamaño del Droplet sin modelo local | ADR-007 |
| A22 reescrito: cliente HTTP resiliente hacia la Inference API (timeouts, un reintento solo pre-envío, nunca ante 4xx/5xx, sin backoff artificial) | ADR-008 |

## 4. Estado del componente experimental (honesto)

**7 partidas reales registradas en MLflow** (verificado vía API del servidor en
el Droplet el 2026-10-02: 7 runs `FINISHED` en el experimento Default, todos
con backend `hf-router`, proveedor featherless-ai, 3 jugadores, 2 rondas y la
métrica `rondas_sobrevividas`). La varianza entre runs es evidencia de que son
partidas distintas, no datos fabricados.

**El barrido completo de configuraciones (A25) NO se hizo.** No hay
comparación cuantitativa entre las versiones de prompt v1/v2/v3 ni
conclusiones estadísticas sobre la tasa de detección. Lo que existe es una
prueba de trazabilidad de un run con el stack integrado (A16) y partidas
individuales con resultado distinto (1.0 / 0.5 / 0.0).

## 5. Limitaciones

- Sin barrido experimental: no hay evidencia cuantitativa de qué prompt
  (v1/v2/v3) hace al impostor más o menos detectable.
- El set de evaluación propio (A4) estaba en borrador; la model card sigue
  declarando "sin evaluación cuantitativa".
- Latencia dependiente de un tercero (Featherless AI); un arranque en frío
  puede superar la ventana de respuesta.
- Un reintento único solo cubre fallos de red pre-envío; una respuesta 5xx
  termina la partida con revelación (decisión deliberada, ADR-008).

## 6. Consideraciones éticas

- **Consentimiento**: la UI exige aceptar antes de entrar al lobby que un
  participante puede ser un modelo de lenguaje y que la conversación se
  registra con fines de investigación. Sin aceptar, no se entra.
- **Alias**: los jugadores son "Jugador N" impuesto por el servidor; no se
  recolectan datos personales. En MLflow se guarda transcript anónimo, nunca
  identidades.
- **Revelación obligatoria**: toda partida termina mostrando quién era la IA,
  los votos y la tasa de detección. No hay partidas sin revelación.

## 7. Trabajo futuro

- Barrido completo de configuraciones (A25): 9 configuraciones × N partidas
  para comparar prompts y medir tasa de detección con los datos de MLflow ya
  disponibles.
- Caché de respuestas en el cliente de inferencia (diferida en ADR-008: el
  costo medido no lo justifica, < USD 0,000059/llamada).
- Set de evaluación A4 terminado para calibrar la model card.