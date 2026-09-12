"""Resolver system prompts versionados por persona para el engine.

El engine no conoce el juego; las personas son solo los datos de los
placeholders (alias, edad, ciudad, ocupacion). Fail-closed: cualquier
persona o version desconocida es un error, nunca un fallback silencioso
que contamine el experimento.
"""

import json
from pathlib import Path

VERSION_FILES: dict[str, str] = {
    "v1": "v1_neutro.md",
    "v2": "v2_persona.md",
    "v3": "v3_imperfeccion.md",
}

PERSONA_KEYS = {"alias", "edad", "ciudad", "ocupacion"}


class PromptStoreError(ValueError):
    """Resolver fallida del store: persona, version o plantilla invalidas."""


class PromptStore:
    """Resolver plantillas versionadas con los datos de la persona pedida."""

    def __init__(
        self,
        *,
        templates_dir: Path | None = None,
        personas_path: Path | None = None,
    ) -> None:
        """Fijar los directorios de plantillas y personas con defaults del paquete."""
        self._templates_dir = templates_dir or Path(__file__).parent / "prompts"
        self._personas_path = personas_path or Path(__file__).parent / "personas.json"
        self._personas_cache: dict | None = None

    def render_prompt(self, *, persona_id: str, version: str, max_words: int) -> str:
        """Resolver la plantilla de la version con los placeholders de la persona."""
        personas = self._load_personas()
        if persona_id not in personas:
            raise PromptStoreError(f"persona desconocida: {persona_id}")
        filename = VERSION_FILES.get(version)
        if filename is None:
            raise PromptStoreError(f"version desconocida: {version}")
        try:
            template = (
                self._templates_dir.joinpath(filename)
                .read_text(encoding="utf-8")
                .rstrip()
            )
        except FileNotFoundError:
            raise PromptStoreError(f"version desconocida: {version}") from None
        values = {**personas[persona_id], "max_words": str(max_words)}
        try:
            rendered = template.format(**values)
        except (KeyError, IndexError, ValueError) as error:
            raise PromptStoreError(
                f"placeholder sin resolver: {error.args[0]}"
            ) from None
        if "{" in rendered or "}" in rendered:
            raise PromptStoreError("placeholder sin resolver")
        return rendered

    def _load_personas(self) -> dict:
        """Cargar personas validando el esquema exacto; cachear tras el primer uso."""
        if self._personas_cache is not None:
            return self._personas_cache
        raw = self._personas_path.read_text(encoding="utf-8")
        personas = json.loads(raw)
        for persona_id, persona in personas.items():
            if not isinstance(persona, dict) or set(persona.keys()) != PERSONA_KEYS:
                raise PromptStoreError(f"persona sin esquema válido: {persona_id}")
        self._personas_cache = personas
        return personas
