"""Zona neutral de código puro y sin estado compartido entre servicios.

Regla de AGENTS.md: este paquete no conoce rondas, votos, jugadores,
puntajes, partidas, gRPC ni HTTP. Solo aloja funciones puras y estructuras
de datos inmutables que cualquiera de los servicios puede importar.
"""
