# ADR-007 - Tamaño del Droplet sin modelo local

**Fecha:** 2026-09-17 · **Estado:** propuesta
**Decide:** equipo, antes del 2026-09-20 · **Propone:** R4 · **Consultado:** R1 (Docker), pendiente

## Contexto

La tarjeta A20 dice "Provisionar Droplet 4 GB". Ese tamaño venía de cargar
Qwen2.5-1.5B GGUF en memoria. ADR-001 lo cambió: la inferencia es remota
(Inference API por HTTP) y el Droplet ya no aloja el modelo.

Lo que corre ahora en el Droplet:

- Tres contenedores Python 3.13 livianos (engine gRPC, orquestador, UI Streamlit),
  sin pesos de modelo.
- SQLite local para las partidas.
- MLflow (servidor y artefactos), si se despliega ahí y no en local.
- El GitLab Runner (A24), que **construye tres imágenes Docker** en cada
  pipeline. Es el consumo pico: `uv sync` con wheels de grpcio más capas de build.

## Decisión propuesta

**2 GB de RAM / 2 vCPU con 2 GB de swap**, con dos condiciones:

1. MLflow corre en la máquina de análisis y no en el Droplet. Si tiene que vivir
   en el Droplet, se sube a 4 GB.
2. El pipeline construye las imágenes en serie, no en paralelo, y limpia caché
   de build (`docker builder prune`) tras cada despliegue para vigilar el disco.

Si el smoke test (A26) o el Runner muestran OOM o swap sostenido, se
redimensiona a 4 GB. DigitalOcean permite subir de tamaño sin reinstalar.

## Alternativas

- **Mantener 4 GB:** es la opción segura y con más margen, pero cuesta más y ya
  no la justifica el modelo. Es razonable si el equipo prefiere no arriesgar la
  demo del 3 de octubre.
- **1 GB:** descartado. El build de las tres imágenes con el Runner no cabe
  con margen.

## Consecuencias

- Hay que editar el título y los criterios de A20 para que digan el tamaño
  aprobado. Un ticket que dice "4 GB" con un Droplet de 2 GB es una
  incoherencia visible.
- A24 (Runner) y A26 (smoke test) deben medir memoria durante el primer
  pipeline y dejarla registrada en `docs/verificaciones/`.
- **Pendiente de verificar:** la tarifa vigente de cada tamaño en
  <https://www.digitalocean.com/pricing/droplets>. Este ADR no la asume.
