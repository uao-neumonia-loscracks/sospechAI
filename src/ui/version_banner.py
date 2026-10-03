"""Pie de página con la versión desplegada (feature/demo-banner, A29).

La UI muestra en todas las pantallas un pie con un texto constante y el SHA
del commit desplegado. El SHA llega por la variable de entorno APP_VERSION,
que el pipeline de deploy inyecta (CI_COMMIT_SHORT_SHA); sin la variable
(arranque local) se muestra "local".
"""

import os

BANNER_TEXT = "SospechAI · despliegue aen vivo en clase"


def version_label(environ: dict[str, str] | None = None) -> str:
    """Devolver el SHA del commit desplegado, o "local" si APP_VERSION no existe.

    Acepta el entorno como argumento para poder probarse sin tocar os.environ
    (las pruebas nunca dependen de variables del proceso).
    """

    raw = (environ if environ is not None else os.environ).get("APP_VERSION")
    return raw if raw else "local"


def render_version_banner() -> None:
    """Dibujar el pie con el texto fijo y la versión desplegada."""

    # Validacion A30: tocar src/ reconstruye solo la capa COPY src; el venv
    # (uv sync) sale del cache del runner y no se vuelve a compilar.
    import streamlit as st

    st.markdown(f"{BANNER_TEXT} — versión {version_label()}")
