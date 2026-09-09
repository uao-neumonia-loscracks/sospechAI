# sospechAI
Sistema de conversación multijugador para medir la detección humana de texto generado por IA

## Inicio propuesto de R2

La carpeta [r2_inicio](r2_inicio/README.md) contiene un primer prototipo local del
controlador de partidas, pruebas y un borrador de comunicación con el modelo.
Las reglas se proponen para revisión del equipo; A6, A8 y A15 siguen en desarrollo.

Para ejecutar la partida de práctica desde la raíz del repositorio:

```bash
uv run --no-project --python 3.13 python -m r2_inicio.demo
```

Consulta la [guía paso a paso](r2_inicio/README.md) y los
[acuerdos pendientes](r2_inicio/ACUERDOS_PENDIENTES.md). La demo utiliza respuestas
simuladas; todavía no es la aplicación multijugador integrada.
