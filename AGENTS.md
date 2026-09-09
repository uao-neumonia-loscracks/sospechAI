# Reglas del proyecto SospechAI

Estas reglas se aplican a todo cambio. Si un cambio las viola, se bloquea.

## Arquitectura: bajo acoplamiento

- `proto/impostor.proto` es la fuente unica de verdad. Esta congelado.
  Ningun cambio puede modificarlo sin un ADR aprobado.
- `src/orchestrator/` NUNCA importa nada de `src/engine/`. La unica
  comunicacion permitida es por gRPC a traves del contrato.
- `src/engine/` NO conoce rondas, votos, jugadores, puntajes ni partidas.
  Si aparece cualquiera de esas palabras en el engine, es un error de diseno.
- `src/ui/` NUNCA habla gRPC directo con el engine. Solo con el orquestador.
- Ningun modulo accede a atributos privados (_x) de otro modulo.

## Arquitectura: alta cohesion

- Un modulo, una responsabilidad.
- Funciones de mas de 40 lineas se rechazan salvo justificacion escrita.
- La normalizacion de texto vive en UNA sola funcion. Humanos y modelo pasan
  por ella. Dos rutas de normalizacion sesgan el experimento.

## Reglas duras del curso

- Prohibido .ipynb, Colab, Kaggle y la carpeta notebooks/.
- Entorno exclusivo uv con Python 3.13. Prohibido pip directo.
- Todo el codigo en src/. Todas las pruebas en tests/.
- Cero warnings. pytest corre con filterwarnings = ["error"].
- Docstrings y type hints en toda funcion publica.
- PEP 8 verificado con ruff y black.

## Pruebas

- Estructura Arrange-Act-Assert explicita.
- Una prueba que no puede fallar no cuenta.
- Las pruebas nunca llaman a la API real de Hugging Face.

## Secretos

- Cero credenciales en el repositorio. HF_TOKEN solo por variable de entorno.
- Prohibido versionar .env, .gguf, .h5, .pkl.

## Requisitos que no son configuracion

- La pantalla de revelacion es un estado de la maquina, no una bandera.
- La pantalla de consentimiento va antes del lobby.

## Commits

- Prefijo: feat:, fix:, test:, chore:
- Todo commit referencia su ticket: (A7), (A13), etc.
- Commits pequenos, uno por cambio logico.