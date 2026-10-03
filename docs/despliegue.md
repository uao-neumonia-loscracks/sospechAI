# Despliegue de SospechAI

Cómo se despliega SospechAI a producción: infraestructura, pipeline, smoke test, rollback, secretos y operación manual. Documenta el estado verificado del Módulo 4 (pipeline optimizado A30, `14:09` → `3:19` con cache caliente).

## 1. Arquitectura de despliegue

| Pieza | Qué es |
| --- | --- |
| Droplet | Ubuntu 22.04, 4 GB RAM, 2 vCPU (DigitalOcean), IP pública `198.211.107.154`. Sin modelo local: el engine llama a la Inference API de Hugging Face por HTTP (ver `docs/adr/ADR-007-tamano-del-droplet.md`). |
| Cloud Firewall | Reglas solo para los puertos **22** (SSH) y **80** (UI). Todo lo demás queda cerrado desde afuera, incluido MLflow (solo alcanzable por túnel SSH, ver sección 8). |
| GitLab Runner | Una sola instancia self-hosted con executor **shell** (etiqueta `droplet`), instalada **dentro del mismo Droplet**. Todos los jobs del pipeline corren ahí; no hay runners compartidos de GitLab. |
| Registry | Container Registry de GitLab (`registry.gitlab.com/jcmt-group/sospechai`). Las imágenes se construyen en el job `build` y se bajan en el Droplet durante el deploy. |
| Compose de producción | `/opt/sospechai/docker-compose.prod.yml`, project name `sospechai`. Contiene 4 servicios: `engine` (gRPC 50051, red interna), `orchestrator` (HTTP 8080, red interna), `ui` (Streamlit, publicado en `80:8501`) y `mlflow` (publicado solo en `127.0.0.1:5000`). |

```
                    Internet
                       |
              Cloud Firewall (22, 80)
                       |
                 Docker Droplet
        ┌──────────────┼──────────────┐
     engine:50051   orchestrator:8080   ui:80
        └───┐             │              │
     Inference API   mlflow:5000     (Streamlit 8501)
     (HF HTTP)      (solo localhost,
      externo)       túnel SSH)
```

El runner ejecuta el pipeline localmente: clona el repo, construye las imágenes con BuildKit y el job `deploy` corre `scripts/deploy.sh` en el mismo Droplet.

## 2. Cloud Firewall y no solo `ufw`

Docker **se salta `ufw`**. Las reglas de `ufw` se aplican en la cadena `FORWARD` de iptables, pero Docker inserta sus propias cadenas (`DOCKER`, `DOCKER-USER`) e inyecta reglas de reenvío directamente en iptables al publicar puertos (`-p`). El tráfico hacia un contenedor publicado entra por la cadena de Docker y **nunca pasa por la cadena donde `ufw` filtra**, así que `ufw allow 80` no es garantía de nada en un host con Docker: lo que `ufw` no vio, Docker lo dejó pasar.

Por eso la protección real vive **fuera del Droplet**, en el Cloud Firewall provisto por el proveedor (DigitalOcean): el firewall de red se aplica antes de que el paquete toque el host, y ni Docker ni nada dentro de la máquina puede saltárselo. Dejando solo `22` y `80` ahí se garantiza que `5000` (MLflow), `50051` (engine) y `8080` (orquestador) sean inalcanzables desde afuera incluso si un contenedor los publicara por error. El `ufw` interno puede existir además como segunda capa, pero nunca como única defensa.

## 3. Etapas del pipeline y en qué ramas corren

Archivo: `.gitlab-ci.yml`. Las tres etapas usan `tags: [droplet]` → corren en el runner self-hosted del Droplet.

| Etapa | Comando | En qué ramas | Qué hace |
| --- | --- | --- | --- |
| `test` | `docker run` con `ghcr.io/astral-sh/uv:python3.13-bookworm-slim` | **Todas** (sin `rules`) | Corre en un contenedor efímero con `--user "$(id -u):$(id -g)"`, cache de uv en `/opt/uv-cache` del host y el repo montado en `/app`. Ejecuta `uv sync --locked`, `ruff check`, `black --check` y `pytest -q` (426 pruebas, sin warnings, sin llamar a la API real de HF). No instala nada en el Droplet. |
| `build` | `docker buildx build --push` de las 3 imágenes | **Solo `main`** | `docker login` al registry con las credenciales de CI (variables del proyecto, nunca en el repo). Construye las 3 imágenes **en paralelo dentro del mismo job** (`& p1... & wait`), porque el runner es único y jobs separados se serializarían. Usa `--provenance=false --sbom=false`: evita el error "blob unknown to registry" que producían las attestations de BuildKit al pushear manifest list. Tag: `$CI_COMMIT_SHORT_SHA`. |
| `deploy` | `bash scripts/deploy.sh` | **Solo `main`** | Baja las imágenes del commit, levanta el compose, corre el smoke test y hace rollback si falla (sección 5). Define el `environment: production`. |

El `test` corre en cada MR (a `develop` y a `main`); `build` y `deploy` solo en `main`, de modo que **toda versión que llega a main termina desplegada automáticamente**.

## 4. El smoke test y por qué no llama a Hugging Face

Archivo: `scripts/smoke.sh`. Sale 0 si todo está vivo, 1 si no. Verifica disponibilidad local del trío, en orden:

1. **UI**: `curl -fsS http://localhost/_stcore/health` esperando `ok`, con reintentos (30 intentos × 2 s).
2. **Engine**: HealthCheck gRPC ejecutado **dentro del propio contenedor** con `docker compose exec -T engine uv run --no-sync python -m src.impostor_engine.smoke_health`. Es el módulo de health del engine sobre el contrato gRPC local — no genera texto.
3. **Orquestador**: `socket.create_connection(('localhost', 8080), 5)` dentro del contenedor del orquestador, para confirmar que acepta conexiones TCP en el puerto del contrato UI-orquestador.

No llama a Hugging Face a propósito: el smoke test mide **nuestro** despliegue (¿están los 3 servicios arriba y respondiendo entre sí?), no la disponibilidad de un proveedor externo. Si la Inference API estuviera caída, un smoke que la consultara haría rollback de un despliegue que técnicamente está bien, y enmascararía la causa real. La salud del modelo externo se observa en los runs de MLflow (latencia, errores de proveedor), no en la puerta del despliegue.

## 5. Cómo funciona el rollback — ejemplo real

Archivo: `scripts/deploy.sh`. Mecánica:

1. Lee la versión anterior de `/opt/sospechai/LAST_GOOD` (el último tag que pasó el smoke).
2. Copia `docker-compose.prod.yml` a su lugar fijo y hace `docker login` al registry.
3. `desplegar NEW_TAG` (`$CI_COMMIT_SHORT_SHA`): `docker compose pull && up -d --remove-orphans`.
4. Si arranca y **el smoke pasa** → escribe `NEW_TAG` en `LAST_GOOD`, `docker image prune -f`, `DEPLOY OK`, exit 0.
5. Si el arranque falla **o el smoke falla** → `ROLLBACK A $PREV_TAG` con `desplegar PREV_TAG` y exit 1 (pipeline rojo). Sin versión anterior: `SIN VERSION ANTERIOR: no hay a donde volver` (también exit 1).

**Prueba real del 02/10/2026** — pipeline **#2908204896** (https://gitlab.com/jcmt-group/sospechAI/-/pipelines/2908204896):

- Se mergeó a `main` una rama que rompía el engine a propósito (punto de entrada inválido en `docker-compose.prod.yml`).
- `deploy.sh` registró en el log del job:
  - `DEPLOY: version nueva fbc24b2f (anterior: 9e5d4622)`
  - `SMOKE: UI ok`
  - `SMOKE: el engine no respondio`
  - `ROLLBACK A 9e5d4622`
  - `ERROR: Job failed: exit status 1` → pipeline **rojo**, deploy marcado como fallido.
- La UI **nunca cayó**: `curl /_stcore/health` siguió respondiendo durante todo el proceso, porque el rollback repone la imagen anterior mientras el compose recicla.
- La corrección siguió el ciclo de ramas: revert a `develop` → MR → merge → MR a `main` → pipeline **#2908217555** en verde (`DEPLOY OK: 79cfe4e2`).

Máxima permanencia de la versión buena: el `LAST_GOOD` solo se actualiza después de un smoke exitoso, así que el rollback siempre vuelve a una versión que se sabe viva.

## 6. Dónde viven los secretos

Cero credenciales en el repositorio (regla dura del proyecto). Los secretos viven en **CI/CD → Variables** del proyecto de GitLab:

- `HF_TOKEN` (token de Hugging Face/Featherless): variable de proyecto.
- `SOSPECHAI_MODEL_ID` y `SOSPECHAI_PROVIDER`: variables de proyecto con defaults en el compose (`Qwen/Qwen2.5-7B-Instruct:featherless-ai` y `featherless-ai`).
- Las credenciales del registry (`CI_REGISTRY_USER`, `CI_REGISTRY_PASSWORD`, `CI_REGISTRY`) son variables **predefinidas** de GitLab CI, disponibles solo durante el job.

**`masked`**: GitLab reemplaza el valor por `[MASKED]` en los logs de todos los jobs. Nadie que vea un log del pipeline puede leerlo, ni aunque escribiera `echo $HF_TOKEN` en un script. Confirmado vía API: `HF_TOKEN` está `masked=true`.

**`protected`**: la variable solo se inyecta en jobs que corren sobre **ramas protegidas** (`main` y `develop`). Un MR de una rama feature externa o un fork **no** recibe el valor, así que un atacante no puede exfiltrar el token corriendo un job en su propia rama.

En runtime, `HF_TOKEN` llega a los contenedores por `environment:` del compose (solo al servicio `engine`, que es el único que habla con la Inference API); no se incrusta en ninguna imagen ni en `docker-compose.prod.yml`.

## 7. Por qué cada servicio tiene su propia imagen

El pipeline construye tres imágenes separadas (`Dockerfile`, `Dockerfile.orchestrator`, `Dockerfile.ui`) en lugar de un monolito. Razones:

- **Bajo acoplamiento en el despliegue**: cada servicio versiona y actualiza de forma independiente. Un cambio de UI no re-empaqueta el engine; una dependencia nueva del orquestador no obliga a reconstruir Streamlit.
- **Aislamiento de fallas**: un crash del engine no tira la UI (como se vio en el rollback: la UI siguió viva con el engine caído), y cada contenedor escala/reinicia por separado con `restart: unless-stopped`.
- **Caché de capas eficiente**: los tres Dockerfiles comparten el mismo patrón — dependencias congeladas primero (`pyproject.toml` + `uv.lock` → `uv sync --frozen`), código después — así un cambio de `src/` invalida pocos KB y no re-empaqueta el venv (era el cuello de botella previo al build optimizado de A30).
- **Secretos mínimos**: solo `engine` recibe `HF_TOKEN`; los otros servicios ni lo ven.
- **Contrato explícito**: cada imagen expone su puerto del contrato (50051 gRPC, 8080 HTTP, 8501 Streamlit) y basta con `docker compose` para cablearlos por nombre de servicio interno.

El `mlflow` no tiene imagen propia: reutiliza `orchestrator:${IMAGE_TAG}` con otro `command` (`uv run mlflow server`), porque comparte el mismo venv Python y evita una cuarta imagen que duplicaría dependencias.

## 8. Ver MLflow

MLflow corre en el Droplet publicado **solo en `127.0.0.1:5000`** (loopback) y el Cloud Firewall no abre el 5000, así que desde afuera hay que usar un túnel SSH:

```bash
ssh -L 5000:localhost:5000 deploy@198.211.107.154
```

Con el túnel activo, abre en tu navegador:

```
http://localhost:5000
```

El navegador manda el request por el túnel al `localhost:5000` del Droplet, donde MLflow responde (`MLFLOW_SERVER_ALLOWED_HOSTS` autoriza `localhost:*`). El orquestador lo llama internamente como `http://mlflow:5000` (nombre de servicio del compose). Cada partida terminada registra un run con params (modelo, proveedor, temperatura, max_words, jugadores, rondas), métricas (tasa de detección, latencia p95, tokens, costo estimado), artefactos (transcript anónimo y matriz de votos) y tags de trazabilidad.

## 9. Levantar todo manualmente si el Droplet se reinicia

Los cuatro servicios tienen `restart: unless-stopped`; si el Droplet se reinicia, Docker arranca y los contenedores **vuelven solos** con la versión de `LAST_GOOD` (las imágenes quedan cacheadas en el host). Por lo general **no hay que hacer nada**.

Para levantarlo o forzarlo a mano:

```bash
ssh deploy@198.211.107.154

# Versión a levantar: la última que pasó el smoke
export IMAGE_TAG="$(cat /opt/sospechai/LAST_GOOD)"
export CI_REGISTRY_IMAGE="registry.gitlab.com/jcmt-group/sospechai"
# HF_TOKEN y los demás secretos deben estar exportados o definidos en el entorno
# (equivalen a las variables protegidas del CI; no se versionan).

docker compose -p sospechai -f /opt/sospechai/docker-compose.prod.yml pull
docker compose -p sospechai -f /opt/sospechai/docker-compose.prod.yml up -d --remove-orphans
```

Verificación rápida de que todo está vivo:

```bash
curl -fsS http://localhost/_stcore/health          # UI: espera "ok"
docker compose -p sospechai -f /opt/sospechai/docker-compose.prod.yml \
  exec -T engine uv run --no-sync python -m src.impostor_engine.smoke_health
```

Esto reproduce a mano exactamente lo que hace el job `deploy` del CI (sección 5). El camino normal sigue siendo dejar que el pipeline despliegue solo; el manual existe como plan B de recuperación.