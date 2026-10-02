#!/usr/bin/env bash
# Despliega las tres imagenes del commit actual y hace rollback si el smoke falla.
# Lo ejecuta el job "deploy" del pipeline, en el Droplet.
set -uo pipefail

DEPLOY_DIR=/opt/sospechai
COMPOSE="docker compose -p sospechai -f $DEPLOY_DIR/docker-compose.prod.yml"
NEW_TAG="$CI_COMMIT_SHORT_SHA"
PREV_TAG="$(cat "$DEPLOY_DIR/LAST_GOOD" 2>/dev/null || true)"

# Copiar los archivos de despliegue a su lugar fijo
cp docker-compose.prod.yml "$DEPLOY_DIR/"

# Login al registry para poder bajar imagenes
echo "$CI_REGISTRY_PASSWORD" | docker login -u "$CI_REGISTRY_USER" --password-stdin "$CI_REGISTRY"

export CI_REGISTRY_IMAGE HF_TOKEN

desplegar() {
  export IMAGE_TAG="$1"
  $COMPOSE pull && $COMPOSE up -d --remove-orphans
}

echo "DEPLOY: version nueva $NEW_TAG (anterior: ${PREV_TAG:-ninguna})"
if ! desplegar "$NEW_TAG"; then
  echo "DEPLOY: fallo el arranque de $NEW_TAG"
elif bash scripts/smoke.sh; then
  echo "$NEW_TAG" > "$DEPLOY_DIR/LAST_GOOD"
  docker image prune -f > /dev/null
  echo "DEPLOY OK: $NEW_TAG"
  exit 0
fi

if [ -n "$PREV_TAG" ]; then
  echo "ROLLBACK A $PREV_TAG"
  desplegar "$PREV_TAG"
else
  echo "SIN VERSION ANTERIOR: no hay a donde volver"
fi
exit 1
