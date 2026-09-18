"""Hash del contenido de un prompt versionado, independiente de git."""

import hashlib
from pathlib import Path


def prompt_version_hash(path: Path) -> str:
    """Calcular el SHA-256 del contenido de un prompt, en 12 hex.

    El plan original pedía el hash corto del commit de git, pero usamos el
    hash del contenido porque (a) el contenedor Docker no tiene .git
    disponible y (b) el hash del commit no cambia si el archivo se edita
    sin commitear, mientras que el hash del contenido sí: es estrictamente
    más fuerte para reproducibilidad.
    """
    try:
        content = path.read_bytes()
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"No existe el archivo de prompt: {path}") from exc
    return hashlib.sha256(content).hexdigest()[:12]
