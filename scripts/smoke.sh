#!/usr/bin/env bash
# Smoke test post-despliegue. Sale 0 si todo esta vivo, 1 si no.
set -uo pipefail

COMPOSE="docker compose -p sospechai -f /opt/sospechai/docker-compose.prod.yml"

echo "SMOKE: esperando a la UI..."
ui_ok=0
for _ in $(seq 1 30); do
  if curl -fsS http://localhost/_stcore/health 2>/dev/null | grep -q ok; then
    ui_ok=1
    break
  fi
  sleep 2
done
if [ "$ui_ok" -ne 1 ]; then
  echo "SMOKE: la UI no respondio en 60 segundos"
  exit 1
fi
echo "SMOKE: UI ok"

# Engine: HealthCheck gRPC, ejecutado dentro del propio contenedor del engine
if ! $COMPOSE exec -T engine uv run --no-sync python -m src.impostor_engine.smoke_health; then
  echo "SMOKE: el engine no respondio"
  exit 1
fi

# Orquestador: que el puerto 8080 acepte conexiones TCP
if ! $COMPOSE exec -T orchestrator python -c \
  "import socket; socket.create_connection(('localhost', 8080), 5).close()"; then
  echo "SMOKE: el orquestador no acepta conexiones en 8080"
  exit 1
fi
echo "SMOKE: orquestador ok"

echo "SMOKE OK"
exit 0
