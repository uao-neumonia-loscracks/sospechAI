"""Pruebas AAA del hash de versión de prompt por contenido."""

import pytest

from src.common.prompt_version import prompt_version_hash


def test_hash_is_stable_for_same_content(tmp_path) -> None:
    """El hash no cambia entre llamadas para un archivo idéntico."""
    # Arrange
    path = tmp_path / "v1.md"
    path.write_text("Sos un jugador más de la partida.", encoding="utf-8")
    # Act
    first = prompt_version_hash(path)
    second = prompt_version_hash(path)
    # Assert
    assert first == second


def test_hash_changes_when_content_changes(tmp_path) -> None:
    """Editar el archivo sin commitear cambia el hash del contenido."""
    # Arrange
    path = tmp_path / "v1.md"
    path.write_text("Primera versión.", encoding="utf-8")
    original = prompt_version_hash(path)
    # Act
    path.write_text("Primera versión editada.", encoding="utf-8")
    changed = prompt_version_hash(path)
    # Assert
    assert changed != original


def test_hash_returns_twelve_hexadecimal_chars(tmp_path) -> None:
    """El identificador publicado tiene exactamente 12 caracteres hex."""
    # Arrange
    path = tmp_path / "v1.md"
    path.write_text("Contenido arbitrario.", encoding="utf-8")
    # Act
    digest = prompt_version_hash(path)
    # Assert
    assert len(digest) == 12
    int(digest, 16)  # lanza ValueError si no es hexadecimal


def test_hash_missing_file_raises_file_not_found(tmp_path) -> None:
    """Un path inexistente se reporta con FileNotFoundError y mensaje claro."""
    # Arrange
    missing = tmp_path / "no-existe.md"
    # Act
    with pytest.raises(FileNotFoundError, match="(?i)no existe"):
        prompt_version_hash(missing)
    # Assert
    assert not missing.exists()
