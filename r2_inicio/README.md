# Primer inicio de R2

**Objetivo de esta entrega:** entender y probar el controlador de una partida
local, y tener un borrador concreto para conversar con R1. Las reglas están
propuestas; la asignación y los acuerdos del equipo siguen pendientes.

## 1. Abrir la rama

Cuando la rama esté publicada, si todavía no tienes el repositorio:

```bash
git clone https://github.com/uao-neumonia-loscracks/sospechAI.git
cd sospechAI
git switch R2-Natalia-Hernandez
```

Si ya lo tienes, abre su carpeta, comprueba tus cambios con `git status`, ejecuta
`git fetch origin` y luego `git switch R2-Natalia-Hernandez`. Conserva cualquier
trabajo local que Git te pida guardar antes de cambiar de rama.

## 2. Ejecutar tu primera partida

Utiliza Python 3.13, la versión prevista en la propuesta. Estos comandos con
[uv](https://docs.astral.sh/uv/getting-started/installation/) funcionan en macOS,
Windows y Linux. uv puede descargar la versión de Python si aún no está instalada.

Desde la carpeta raíz `sospechAI`:

```bash
uv run --no-project --python 3.13 python -m r2_inicio.demo
```

Responde dos preguntas con un máximo de 15 palabras. Revisa las respuestas,
presiona Enter y vota escribiendo `2`, `3` o `4`. Al terminar se revela el impostor,
se muestran los puntajes y se guarda una simulación en SQLite.

Para observar el flujo completo sin escribir respuestas:

```bash
uv run --no-project --python 3.13 python -m r2_inicio.demo --auto
```

La demo es un ejercicio en consola: tú controlas un participante y los demás
utilizan frases fijas. No hay todavía jugadores conectados desde otros equipos,
modelo de IA, servidor gRPC ni interfaz Streamlit. La fase de discusión permite
revisar el texto; el chat de discusión multijugador queda para la integración.

## 3. Entender qué archivo hace qué

| Archivo | Qué debes entender para explicarlo |
| --- | --- |
| `game.py` | Qué acciones permite cada etapa, cómo valida mensajes y cómo cuenta votos. |
| `demo.py` | Cómo un cliente utiliza las reglas para ejecutar una partida. |
| `storage.py` | Cómo se guarda el resultado final y se marca como simulación. |
| `tests/test_game.py` | Cómo verificamos reglas válidas y rechazamos acciones incorrectas. |
| `proto/impostor.proto` | Qué mensajes intercambiarían el orquestador y el modelo. |
| `ACUERDOS_PENDIENTES.md` | Qué decisiones necesitan acordar antes de integrar el trabajo. |

Primero lee `GameState`, luego `submit_message()` y finalmente `cast_vote()`.
La identidad interna de IA no está incluida en la vista pública antes de la
revelación. SQLite guarda el resultado final; la recuperación de partidas
interrumpidas todavía no está implementada.

## 4. Ejecutar las pruebas

```bash
uv run --no-project --python 3.13 --with-requirements r2_inicio/requirements-dev.txt python -m pytest r2_inicio/tests -q
```

Las pruebas cubren el avance de rondas, las respuestas vacías o largas para ambos
tipos de jugador, los mensajes repetidos, los votos inválidos o duplicados, la
revelación, los puntajes y la escritura/lectura del resultado en SQLite.

Para validar el contrato preliminar:

```bash
uv run --no-project --python 3.13 --with-requirements r2_inicio/requirements-dev.txt python -m r2_inicio.validate_proto
```

Para comprobar calidad y formato:

```bash
uv run --no-project --python 3.13 --with-requirements r2_inicio/requirements-dev.txt ruff check r2_inicio
uv run --no-project --python 3.13 --with-requirements r2_inicio/requirements-dev.txt black --check r2_inicio
```

## 5. Cómo se relaciona con tus tareas

| Tarea | Avance de esta entrega | Qué sigue |
| --- | --- | --- |
| A6, compartida | Borrador `.proto` que se puede compilar. | Acuerdo R1/R2, stubs, CI y congelación del contrato. |
| A8 | Reglas y flujo de una partida local; resultado final en SQLite. | Servidor, comunicación con IA/UI, temporizadores, concurrencia y persistencia activa. |
| A15, compartida | Pruebas locales del dominio y del guardado. | Pruebas gRPC, cobertura e integración con servicios y bots. |

Estas tareas permanecen abiertas. El siguiente paso es revisar los acuerdos con
el equipo y transformar este dominio en el servicio `impostor-orchestrator`.

## Referencias

- [A6: contrato](https://github.com/uao-neumonia-loscracks/sospechAI/issues/6)
- [A8: orquestador](https://github.com/uao-neumonia-loscracks/sospechAI/issues/8)
- [A15: pruebas](https://github.com/uao-neumonia-loscracks/sospechAI/issues/15)
- [Gestión de Python con uv](https://docs.astral.sh/uv/guides/install-python/)
- [Tutorial oficial de gRPC para Python](https://grpc.io/docs/languages/python/basics/)
