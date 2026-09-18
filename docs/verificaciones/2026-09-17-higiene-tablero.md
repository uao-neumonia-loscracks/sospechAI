# Higiene del tablero — 2026-09-17 — R4 (R4-2)

Revisión de las 29 tarjetas (issues de GitHub) contra el repositorio y los PR.
El Kanban vale el 15 % del módulo.

**Limitación:** el token de `gh` no tiene el scope `read:project`, así que no
se pudo leer la columna de cada tarjeta dentro del Project. Esta revisión usa
los issues, que sí son accesibles. Para leer columnas:
`gh auth refresh -s read:project,project`.

## Hallazgos globales

| # | Hallazgo | Estado |
|---|---|---|
| 1 | **Ninguna de las 29 tarjetas tiene responsable asignado ni fecha (milestone).** | Propuesta abajo; falta aplicarla |
| 2 | Las 3 tarjetas cerradas (A5, A7, A8) no tenían PR enlazado. | **Hecho:** comentario con el PR #30 en cada una |
| 3 | Ningún PR usa `Closes #N`, así que GitHub no enlaza ni cierra tarjetas solo. | Regla para el equipo desde hoy |
| 4 | Faltan las tarjetas **A18** y **A31**. El plan usa A31 para Archify. | Crear A31 o renumerar; explicar el salto A17 → A19 |
| 5 | **A22** tenía el objetivo obsoleto (volumen GGUF). | **Hecho:** reescrita como cliente HTTP resiliente |
| 6 | **A20** dice "4 GB". | ADR-007 en estado propuesta; decisión del equipo antes del 20/09 |
| 7 | **A13 está mal etiquetada en los commits.** La tarjeta es MLflow, pero los PR #32/#33 (prompts y store de prompts) llevan `(A13)`. | Corregir la referencia en futuros PR; MLflow sigue sin empezar |
| 8 | **A11 no es el Model Card.** La tarjeta es "Benchmark de calidad y confirmación del modelo definitivo". El plan de cierre llama A11 al Model Card. | Decidir: el Model Card cubre el criterio "decisión documentada" de A11, o se crea tarjeta propia |
| 9 | No existe `.github/pull_request_template.md` en el repo, aunque A3 exige plantilla de PR. | A3 no puede cerrarse sin ella |
| 10 | `main` y `develop` divergieron (#39 solo en develop, #41 solo en main). El PR #40 de sincronización se cerró sin merge. | Equipo, antes de la entrega |

## Tarjetas abiertas: responsable y fecha propuestos

Los responsables salen del reparto del plan de cierre. Logins:
R1 `JCMelendezT`, R2 `nathernandez1189`, R3 `juano2024`, R4 `MiguelDiuza`.

| Tarjeta | Estado según el repo | Responsable | Fecha |
|---|---|---|---|
| A1 Entorno de benchmark 2 vCPU / 4 GB | Sin objeto con ADR-001; el benchmark se hizo contra la API | R1 | Cerrar con referencia a PR #30 y ADR-001 |
| A2 Benchmark Qwen2.5-1.5B Q4_K_M | Reemplazado por el benchmark real de Inference Providers (`40065be`, PR #30) | R1 | Reescribir título y cerrar con PR #30 |
| A3 Repo: UV, Gitflow, plantilla de PR | UV y reglas hechos (PR #31, #35); **falta la plantilla de PR** | R4 | 18/09 |
| A4 Set de evaluación de 100 pares | Sin evidencia en el repo | R1 + R3 | Decisión de alcance 18/09 |
| A6 Congelar `.proto` v1 | La cabecera del `.proto` todavía dice "BORRADOR… no es un contrato congelado" | R1 + R2 | 18/09 |
| A9 UI: lobby, sala, mensajes | Contrato (PR #36) y esqueleto (PR #41); falta contenido | R3 | 18/09 |
| A10 Arnés de bots | En curso hoy (R4-3) | R4 | 17/09 |
| A11 Benchmark de calidad y modelo definitivo | Ver hallazgo 8 | R1 (+ R4 Model Card) | 18/09 |
| A12 Docker compose | Parcial: solo el engine (PR #39, en develop) | R1 | 18/09 |
| A13 MLflow | Sin empezar (ver hallazgo 7) | R1 | 18/09 |
| A14 UI: votación y revelación | Sin empezar | R3 | 18/09 |
| A15 Suite de pruebas | 187 pruebas; auditoría entregada; falta AAA y contrato | R4 (auditoría) + dueños | 18/09 |
| A16 Partida piloto | Pendiente de integración | R3 | 18/09 |
| A17 Video, README, calidad | Pendiente | R4 | 18/09 |
| A19 Migrar a GitLab | Módulo 4 | R4 | 22/09 |
| A20 Droplet | ADR-007 propuesto | R4 | 22/09 |
| A21 Dockerfiles definitivos y registry | Módulo 4 | R4 + R1 | 24/09 |
| A22 Cliente HTTP resiliente | Reescrita hoy | R1 | 26/09 |
| A23 `.gitlab-ci.yml` | Módulo 4 | R4 | 27/09 |
| A24 GitLab Runner | Módulo 4 | R4 | 27/09 |
| A25 Sesiones experimentales y barrido | Módulo 4; depende del costo (R1-9) | R3 | 28/09 |
| A26 Smoke test y rollback | Módulo 4 | R4 | 30/09 |
| A27 Credenciales enmascaradas | Módulo 4 | R4 + R1 | 24/09 |
| A28 Análisis y gráficas | Módulo 4 | R3 | 30/09 |
| A29 Ensayo completo | Módulo 4 | Equipo | 02/10 |
| A30 Reporte final | Módulo 4 | R4 | 02/10 |

## Para aplicar las asignaciones

Una vez que el equipo confirme la tabla:

```bash
gh issue edit <n> --add-assignee <login>
```

Para las fechas, lo más limpio son dos milestones, "Módulo 3 (19/09)" y
"Módulo 4 (03/10)", más `--milestone`.
