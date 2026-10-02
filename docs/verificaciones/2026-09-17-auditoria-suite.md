# Auditoría de la suite de pruebas — 2026-09-17 — R4 (A15)

Informe de solo lectura. No se modificó ninguna prueba ni código de producción.

**Base auditada:** `main` en `6d553ee` (incluye R3-1). Python 3.13, `uv`.

```bash
uv run pytest -q --cov=src --cov-report=term-missing   # 187 passed, 0 skipped
uv run pytest --collect-only -q | tail -1              # 187 tests collected
```

## Resumen

| Métrica | Valor |
|---|---|
| Pruebas recolectadas | **187** (mínimo del curso: 120) |
| Pasan / fallan / skip | 187 / 0 / 0 (desde la raíz del repo) |
| Warnings | 0 (`filterwarnings = ["error"]` activo) |
| Cobertura total de `src` | **79 %** (781 sentencias, 163 sin cubrir) |
| Con AAA explícito | **14 de 187** (solo `test_ui_router.py`) |
| No cuentan (no pueden fallar o están duplicadas) | 2 |
| Débiles (tautológicas) | 24 |
| **Sólidas** | **161** |
| Llamadas reales a Hugging Face | 0 (verificado con salida HTTP bloqueada) |

El número está cubierto con holgura. **El riesgo no es la cantidad, es AAA:** la regla del curso exige las tres secciones explícitas y hoy solo el 7 % de la suite las tiene.

## 1. Conteo por área

| Área | Archivo | Pruebas |
|---|---|---|
| Engine | `test_character_break.py` | 31 |
| Engine | `test_servicer.py` | 29 |
| Engine | `test_guards.py` | 19 |
| Engine | `test_inference_client.py` | 14 |
| Engine | `test_prompt_store.py` | 7 |
| **Engine subtotal** | | **100** |
| Orquestador | `test_api_boundary.py` (incluye 2 de loopback gRPC) | 41 |
| Orquestador | `test_game.py` | 23 |
| **Orquestador subtotal** | | **64** |
| Contrato / integración | `test_engine_integration.py` (servicer real ↔ cliente real por loopback) | 9 |
| UI | `test_ui_router.py` | 14 |
| **Total** | | **187** |

No hay pruebas de contrato con `grpcio-testing` (R2-6 pendiente). Las 9 de
`test_engine_integration.py` y las 2 marcadas `integration` en
`test_api_boundary.py` son hoy la única verificación del `.proto` de punta a punta.

**`main` y `develop` divergieron.** En `develop` (`0f433d8`) corren 176 pruebas:
le faltan las 14 de la UI (R3-1) y tiene cambios en `test_character_break.py`
que `main` no tiene. El número de la entrega depende de qué rama se entregue:
hay que reconciliarlas antes del viernes.

## 2. Arrange-Act-Assert

Criterio: tres secciones separadas por un comentario o una línea en blanco.

| Archivo | AAA explícito | Observación |
|---|---|---|
| `test_ui_router.py` | 14 / 14 | `# Arrange / # Act / # Assert` en todas. Es el modelo a seguir. |
| `test_api_boundary.py` | 0 / 41 | AAA implícito; varias fusionan Act y Assert (`assert EngineClient(...).generate(...) == ...`). |
| `test_game.py` | 0 / 23 | AAA implícito, bien ordenado; faltan los separadores. |
| `test_servicer.py` | 0 / 29 | AAA implícito; Act dentro de `list(...)` pegado al Assert. |
| `test_engine_integration.py` | 0 / 9 | Act y Assert dentro del mismo `with`. |
| `test_inference_client.py` | 0 / 14 | Arrange largo (dobles de urllib) sin separar. |
| `test_character_break.py` | 0 / 31 | Una línea por prueba: Act y Assert fusionados. |
| `test_guards.py` | 0 / 19 | Una línea por prueba, parametrizada. |
| `test_prompt_store.py` | 0 / 7 | AAA implícito. |

**173 pruebas incumplen la forma explícita.** El arreglo es mecánico: separar
con comentarios y sacar el Act del `assert`. No cambia el comportamiento. Lo
debe hacer el dueño de cada archivo (R1: engine; R2: orquestador) para no
pisar ramas activas.

## 3. Pruebas que no cuentan o son débiles

**No pueden fallar o no aportan (2), no cuentan:**

| Prueba | Motivo |
|---|---|
| `test_servicer.py::test_budget_capped_by_round_timeout` | Solo afirma `timeout is not None`. El servicer siempre pasa `timeout`, así que pasaría aunque el tope de `round_timeout=4.0` no existiera. Debería afirmar `<= 4.0`. |
| `test_servicer.py::test_resolved_system_prompt_is_preferred_over_static` | Mismo Arrange/Act que `test_system_prompt_is_sent_when_configured` y misma aserción. Además, el nombre dice lo contrario del docstring: gana el override estático, no el resuelto. |

**Débiles, tautológicas (24):** `test_character_break.py::test_each_pattern_detects_its_phrase`
parametriza sobre `CHARACTER_BREAK_PATTERNS`, los mismos datos que usa la
implementación. Cada caso comprueba que una regex construida desde la frase
encuentra esa misma frase. Solo fallan si dos patrones se solapan o se rompe la
normalización. Sirven como regresión, pero no prueban el criterio del detector.
Lo que sí lo prueba son las 7 pruebas de frases dentro y fuera de personaje del
mismo archivo.

**Borde (se cuentan, pero conviene fortalecerlas):**

- `test_ui_router.py::test_app_and_screens_import_and_start_at_consent`: es un
  smoke de importación y repite la comprobación de consentimiento de la primera
  prueba.
- `test_ui_router.py::test_poll_interval_*` (6): fijan constantes del contrato
  §14.1. Es válido porque el contrato las fija, pero son aserciones de constantes.

## 4. La prueba en skip

`test_prompt_store.py::test_engine_templates_match_docs_prompts` tiene
`@pytest.mark.skipif(not Path("docs/prompts").exists(), reason="... PR #32")`.

- El PR #32 ya se mergeó y, desde la raíz, la prueba **corre y pasa**. Ese es
  el skip que reportaba el plan (172 + 1 skip).
- **Defecto:** la ruta es relativa al directorio actual. Ejecutada desde
  `tests/` (`cd tests && uv run pytest test_prompt_store.py`), la prueba se
  salta en silencio. Una prueba que se salta según desde dónde se lance puede
  ocultar una divergencia real entre `src/impostor_engine/prompts/` y
  `docs/prompts/`.
- **Arreglo sugerido (R1):** resolver la ruta desde `Path(__file__)` y quitar el
  `skipif`, porque `docs/prompts/` ya es parte del repo.

## 5. Cobertura por módulo

| Paquete | Sentencias | Sin cubrir | Cobertura |
|---|---|---|---|
| `src/impostor_engine` | 402 | 63 | 84 % |
| `src/orchestrator` | 305 | 77 | 75 % |
| `src/ui` | 74 | 23 | 69 % |

**Los tres archivos peor cubiertos:**

| Archivo | Cobertura | Lectura |
|---|---|---|
| `src/impostor_engine/serve.py` | 0 % (32 sent.) | Entrypoint del servidor. Ninguna prueba lo arranca. |
| `src/orchestrator/demo.py` | 0 % (71 sent.) | Demo de consola; se ejecuta a mano, no desde pytest. El arnés de bots (A10) puede cubrir el mismo recorrido. |
| `src/ui/app.py` | 32 % (22 sent.) | Rama de render de Streamlit; `screens/*.py` quedan en 60 %. |

Otras brechas: `prompt_store.py` en 82 % (sin probar los errores de archivo
ausente o JSON inválido, líneas 53-74) y `servicer.py` en 91 % (validaciones de
config 254-281 sin caso propio).

## 6. Hugging Face

- `test_inference_client.py` reemplaza `urllib.request.urlopen` con
  `monkeypatch` en cada prueba y fija un `HF_TOKEN` falso con una fixture
  `autouse`.
- El resto usa dobles (`FakeStreamClient`, `Stub`) o loopback `127.0.0.1`.
- `scripts/spike_inference.py` y `scripts/benchmark_inference.py` sí llaman al
  router real, pero están fuera de `tests/` y pytest no los recolecta.
- **Verificación empírica:** la suite completa pasó (187/187) sin `HF_TOKEN` y
  con `HTTP(S)_PROXY` apuntando a un puerto cerrado (`127.0.0.1:9`), dejando
  solo el loopback fuera del proxy. Ninguna prueba necesita salida a internet.
- **Recomendación:** poner en `tests/conftest.py` una fixture `autouse` que haga
  fallar cualquier `urlopen` no parcheado. Hoy la garantía depende de que cada
  prueba nueva se acuerde de parchear.

## 7. Hallazgo colateral: la validación estándar estaba rota en `main`

`uv run black --check src tests scripts` abortaba con `UnicodeDecodeError`
porque la línea 231 de `.gitignore` ("Caché", añadida en `f614c6f`) estaba en
Latin-1 y black lee ese archivo. En `develop` ya estaba bien. Se corrigió en un
commit aparte en esta misma rama (`fix: guardar .gitignore en UTF-8`).

## Qué falta cubrir, por prioridad

1. **AAA explícito en 173 pruebas.** Es riesgo directo de la sustentación. Dueños: R1 y R2.
2. **Reconciliar `main` y `develop`** para saber qué suite se entrega. Equipo.
3. Pruebas de contrato con `grpcio-testing` (R2-6).
4. `serve.py` y el recorrido de partida completa: el arnés de bots (R4-3) cubre el segundo.
5. Arreglar las 2 que no cuentan y la ruta relativa del skip. R1.
6. Fixture `conftest.py` que bloquee la red. R4, si el equipo lo aprueba.
