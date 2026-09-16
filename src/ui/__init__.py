"""Capa de interfaz (R3): pantallas y router del flujo de partida.

La UI habla únicamente con el orquestador por HTTP+JSON a través de una sola
boca (`src/ui/api.py`); nunca importa ni invoca `src/orchestrator/` ni
`src/impostor_engine/`.
"""
