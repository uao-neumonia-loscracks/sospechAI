# Decisión de alcance — Set de evaluación de 100 pares (A4)

**Fecha:** 2026-09-18 · **Estado:** propuesta para revisión del equipo
**Ticket:** A4 (issue #4) — "Construir set de evaluación de 100 pares en español coloquial"
**Rol nominal:** R3 · **Fase:** 1 · **Puntos:** 8
**Alcance de este documento:** fija el alcance y el método para que R3 construya el dataset. No construye el dataset ni modifica ADR o contratos congelados.

## 1. Contexto

Ningún benchmark público mide la tarea del proyecto: decidir si un texto corto en español coloquial suena humano o generado por IA, en el formato exacto del juego (una respuesta de hasta 15 palabras a una pregunta de ronda). El issue #4 lo plantea como objetivo ("crear la métrica de referencia propia, porque ningún benchmark público mide la tarea del proyecto") y el `docs/model_card.md` lo confirma: "No hay benchmark público de español coloquial colombiano. Por eso existe A4".

El set es además insumo de otras tarjetas: la model card exige evaluar al menos dos modelos contra el set de 100 pares (A11) y el barrido experimental (A25) lo usará como línea base. Sin un set propio, la métrica de detección del juego no tiene referencia contra la cual calibrar el prompt del impostor.

Estado real hoy: `data/external/` no existe (la carpeta `data/` solo contiene `practice/` con bases de práctica), no hay preguntas ni respuestas redactadas y el issue #4 está abierto sin avance. Este documento resuelve la decisión de alcance para que R3 pueda ejecutar la construcción.

## 2. Decisión

El equipo acordó en la sesión del 18 de septiembre de 2026 documentar el alcance del ticket A4 con los cinco criterios de aceptación del issue #4 como compromiso:

| # | Criterio del issue #4 | Ejecuta | Evidencia |
| --- | --- | --- | --- |
| 1 | 100 preguntas detonantes redactadas | R3 | Listado completo en el CSV (sección 6) |
| 2 | Respuestas humanas recolectadas para cada una | R3 | Respuesta no vacía de 1 a 15 palabras por pregunta |
| 3 | Anotación de naturalidad en escala 1-5 por al menos dos hablantes nativos | Dos anotadores del equipo | Columnas de puntaje por anotador (sección 5) |
| 4 | Acuerdo entre anotadores calculado y reportado | R3 (cálculo y reporte), con revisión de R1 | Métrica de proximidad, sección 5 |
| 5 | Dataset versionado en `data/external/` | R3, con revisión de R1 | Git + hash del contenido (sección 6) |

## 3. Alcance (lo que sí)

- **100 preguntas detonantes** en español coloquial sobre situaciones cotidianas de estudiantes: alimentación, cortes de luz, transporte, exámenes y vida social. Los temas son coherentes con las preguntas de ronda existentes del juego (`src/orchestrator/game.py`, `DEFAULT_PROMPTS`: "¿Qué harías si se va la luz justo antes de entregar un trabajo?" y "¿Qué comida escogerías después de una clase larga?") y no constituyen una lista cerrada si el equipo ve necesario ajustar cobertura.
- **Formato de cada par**: pregunta detonante + respuesta humana de 1 a 15 palabras. El límite es el `max_words` real del juego: 15 por defecto (dominio `src/orchestrator/game.py` con `Game(max_words=15)`, servidor con `--max-words` por defecto 15 y contrato UI-orquestador §7.1).
- **Gama equilibrada**: longitudes variadas (respuestas cortas, medianas y cercanas al límite de 15 palabras) y estilos variados (declaración directa, humor, jerga estudiantil, expresiones coloquiales), en línea con lo que el juego espera tanto de humanos como del impostor (prompt v2, `docs/prompts/v2_persona.md`).
- **Registro**: español coloquial del proyecto (coloquial colombiano según la model card y los prompts); las instrucciones para anotadores y los materiales de documentación se redactan en español neutro profesional.

## 4. Fuera de alcance (lo que no)

- **No se recolectan respuestas del modelo** en este set: comparar modelos contra el set es la tarea del benchmark A11 y de la model card.
- **No se anota el origen real** de los textos (humano o IA): solo la naturalidad percibida. El origen es conocido por construcción (respuestas escritas por humanos), pero el set no se usa para entrenar ni calibrar clasificadores de origen.
- **No se usan modelos generativos** para redactar preguntas ni respuestas: la redacción es humana, lo que mantiene verificable el origen de cada elemento. Además, el curso prohíbe `.ipynb`, Colab y Kaggle (regla de `AGENTS.md`).
- **No se incluyen textos fuera del rango de 1 a 15 palabras**, ni formatos distintos de pregunta + respuesta.
- **Cada elemento debe ser verificable manualmente**: cualquier par cuyo origen, límite de palabras o tema no pueda confirmarse se corrige o se descarta antes de versionar.

## 5. Método de anotación

**Escala de naturalidad 1-5** (un valor por par y por anotador):

| Valor | Significado |
| --- | --- |
| 1 | Suena claramente a IA: texto artificial, poco natural para una persona. |
| 2 | Suena más a IA que a humano. |
| 3 | Ambiguo: no se puede decidir. |
| 4 | Suena más a humano que a IA. |
| 5 | Suena claramente a humano: natural, como lo escribiría una persona. |

**Anotadores**: al menos dos hablantes nativos del español del equipo, idealmente familiarizados con el registro coloquial colombiano del juego. Cada anotador evalúa los 100 pares de forma independiente, sin ver los puntajes del otro. No se usan nombres propios en este documento: se identifican como "anotador 1" y "anotador 2" en el dataset.

**Métrica de acuerdo (elegida): acuerdo por proximidad** — dos anotadores coinciden en un par si la diferencia absoluta entre sus puntajes es menor o igual a 1 punto. El acuerdo del set es la proporción de pares con diferencia ≤ 1 sobre los 100.

Justificación breve: la escala es ordinal y subjetiva, y una diferencia de un punto no cambia la clase percibida (artificial 1-2, ambiguo 3, natural 4-5). Cohen's kappa trataría igual una diferencia de 1 que una de 4 puntos, penalizando desacuerdos menores de forma desproporcionada para un set de 100 ítems con solo dos anotadores; la proximidad es más estable e interpretable en este caso. Para transparencia se reporta además la distribución completa de diferencias (0, 1, 2, 3, 4); kappa puede agregarse como complemento si el equipo lo pide, sin reemplazar la métrica decidida.

**Reporte en el dataset**: puntaje por anotador y diferencia por par; clase percibida según el promedio redondeado de ambos puntajes (1-2 artificial, 3 ambiguo, 4-5 natural); y un resumen con distribución de diferencias, promedio y desviación por ítem, proporción por clase percibida y la lista de pares con diferencia > 1 para revisión conjunta. El resumen se archiva en `docs/verificaciones/` o junto al dataset.

## 6. Entregables y versionado

- **Ruta**: `data/external/` (la carpeta no existe hoy; se crea al entregar el dataset).
- **Formato**: CSV en UTF-8 con una fila por par y las columnas:

| Columna | Contenido |
| --- | --- |
| `id` | Identificador del par (1 a 100) |
| `pregunta` | Pregunta detonante en español coloquial |
| `respuesta` | Respuesta humana de 1 a 15 palabras |
| `anotador_1`, `puntaje_1` | Identificación y puntaje de naturalidad (1-5) del primer anotador |
| `anotador_2`, `puntaje_2` | Idem del segundo anotador |
| `diferencia` | Valor absoluto de la diferencia entre puntajes |
| `acuerdo` | `true` si la diferencia es ≤ 1, `false` en caso contrario |
| `clase_percibida` | `artificial`, `ambiguo` o `natural` según el promedio redondeado |

- **Versionado**: el dataset vive en el repositorio, en una rama feature apuntando a `develop` (regla de ramas de `AGENTS.md`), con PR revisado. Cada versión del CSV registra su hash SHA-256 del contenido en un archivo de metadatos junto al dataset, de modo que A11 y A25 puedan referenciar desde MLflow la versión exacta del set que usaron.
- **Fuera de alcance**: publicar o procesar el set en Kaggle o Colab, prohibido por regla del curso (`AGENTS.md`).

## 7. Responsabilidades

| Actividad | Responsable |
| --- | --- |
| Redacción de preguntas y respuestas | R3 |
| Armado del CSV, cálculo del acuerdo y resumen | R3 |
| Versionado con git y hash del contenido | R3 |
| Revisión de formato y coherencia con el dominio del juego (límite de 15 palabras, registro coloquial, esquema de columnas) | R1 |
| Anotación de naturalidad en escala 1-5 | Dos anotadores del equipo, hablantes nativos del español (designados entre R1-R4; sin nombres propios en este documento) |
| Aprobación del alcance | Equipo (R1-R4) |

## 8. Estado

Propuesta para revisión del equipo. Este documento no cierra el issue #4: el cierre queda pendiente del dataset real construido por R3 con los cinco criterios de la sección 2 cumplidos y el resumen de anotación registrado.