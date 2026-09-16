"""Store versionado de prompts: resolución por persona y fallos fail-closed."""

import json
from pathlib import Path

import pytest

from src.impostor_engine import prompt_store
from src.impostor_engine.prompt_store import PromptStore, PromptStoreError

PERSONAS_PATH = Path(prompt_store.__file__).parent / "personas.json"


def test_render_v2_persona_p1() -> None:
    """v2 con p1 resuelve los placeholders de persona y el límite de palabras."""
    store = PromptStore()
    resultado = store.render_prompt(persona_id="p1", version="v2", max_words=15)
    assert "Eres Pipe, 22 anos, de Cali. estudiante de ingeniería." in resultado
    assert "en maximo 15 palabras" in resultado
    assert "{" not in resultado and "}" not in resultado


def test_render_v3_persona_p2() -> None:
    """v3 con p2 incluye la imperfección deliberada sin frases de v2."""
    store = PromptStore()
    resultado = store.render_prompt(persona_id="p2", version="v3", max_words=15)
    assert "escribiendo rapido desde el celular" in resultado
    assert "Puedes usar" not in resultado
    assert "jajaja" in resultado


def test_render_v1_without_persona_data() -> None:
    """v1 es la línea base: solo el límite de palabras, sin datos de persona."""
    store = PromptStore()
    resultado = store.render_prompt(persona_id="p1", version="v1", max_words=7)
    assert resultado.startswith("# v1 - neutro (linea base)")
    assert "maximo 7 palabras" in resultado


def test_unknown_persona_raises() -> None:
    """Una persona inexistente se rechaza sin resolver la plantilla."""
    store = PromptStore()
    with pytest.raises(PromptStoreError, match="persona desconocida: nope"):
        store.render_prompt(persona_id="nope", version="v2", max_words=5)


def test_unknown_version_raises() -> None:
    """Una versión inexistente se rechaza sin resolver la plantilla."""
    store = PromptStore()
    with pytest.raises(PromptStoreError, match="version desconocida: v9"):
        store.render_prompt(persona_id="p1", version="v9", max_words=5)


def test_personas_json_has_only_experiment_fields() -> None:
    """personas.json solo contiene los placeholders del experimento, no el juego."""
    personas = json.loads(PERSONAS_PATH.read_text(encoding="utf-8"))
    forbidden = {"ronda", "voto", "puntaje", "partida", "jugador"}
    for persona_id, persona in personas.items():
        assert set(persona.keys()) == {"alias", "edad", "ciudad", "ocupacion"}
        for value in persona.values():
            assert not any(word in str(value).casefold() for word in forbidden)


@pytest.mark.skipif(
    not Path("docs/prompts").exists(),
    reason="docs/prompts aún no está mergeado (PR #32)",
)
def test_engine_templates_match_docs_prompts() -> None:
    """Los templates runtime no divergen de los prompts revisados en docs."""
    engine_dir = Path(prompt_store.__file__).parent / "prompts"
    docs_dir = Path("docs/prompts")
    for template in sorted(engine_dir.iterdir()):
        if not template.is_file():
            continue
        assert template.read_bytes() == (docs_dir / template.name).read_bytes()
