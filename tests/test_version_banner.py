"""Prueba AAA de la etiqueta de versión del banner (feature/demo-banner, A29).

Cubre el contrato del pie de página: con APP_VERSION definida la etiqueta es
el SHA del commit desplegado; sin la variable, la etiqueta es "local".
"""

from src.ui.version_banner import version_label


def test_version_label_usa_app_version_si_existe() -> None:
    """Con APP_VERSION, la etiqueta es el SHA del commit (A29)."""

    environ = {"APP_VERSION": "a1b2c3d4"}

    label = version_label(environ)

    assert label == "a1b2c3d4"


def test_version_label_usa_local_sin_variable() -> None:
    """Sin APP_VERSION, la etiqueta es "local" (A29)."""

    environ: dict[str, str] = {}

    label = version_label(environ)

    assert label == "local"
