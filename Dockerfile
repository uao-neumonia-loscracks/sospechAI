# Engine de SospechAI: genera utterances vía gRPC usando la Inference API.
# Construye con Python 3.13 y uv; HF_TOKEN llega por variable de entorno,
# nunca se incrusta en la imagen.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Usuario sin privilegios ANTES de copiar: los COPY usan --chown y el venv
# queda solo-lectura en runtime, asi un cambio de src invalida pocos KB
# y no re-empaqueta el venv entero (era el cuello de botella del build).
RUN useradd --create-home --shell /bin/bash app \
    && mkdir -p /app/data /app/mlruns \
    && chown app:app /app/data /app/mlruns

# Primero las dependencias congeladas (mejor caché de capas).
COPY --chown=app:app pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Después el código y el contrato.
COPY --chown=app:app proto ./proto
COPY --chown=app:app src ./src

USER app

EXPOSE 50051

# Entrypoint real del engine (módulo "serve", no "server").
CMD ["uv", "run", "--no-sync", "python", "-m", "src.impostor_engine.serve"]