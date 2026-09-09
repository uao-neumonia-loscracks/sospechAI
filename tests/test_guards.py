"""Guardas de salida deterministas: normalización, conteo y corte de palabras."""

import pytest

from src.impostor_engine.guards import count_words, cut_to_max_words, normalize_text


class TestNormalizeText:
    """Normalización NFC y colapso de espacios, idéntica a R2."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("  hola  mundo  ", "hola mundo"),
            ("\tcafe\u0301   rico\n", "café rico"),
            ("una", "una"),
            ("   \n\t  ", ""),
            ("a\u0301", "á"),
            ("  café  ", "café"),
        ],
    )
    def test_nfc_and_whitespace_collapse(self, raw: str, expected: str) -> None:
        """NFC combina diacríticos y split colapsa todo tipo de espacios."""
        assert normalize_text(raw) == expected


class TestCountWords:
    """Conteo de palabras sobre texto normalizado."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("", 0),
            ("  ", 0),
            ("hola", 1),
            ("  hola  mundo  ", 2),
            ("tres palabras acá", 3),
        ],
    )
    def test_split_count(self, text: str, expected: int) -> None:
        """Un split normalizado produce el conteo correcto."""
        assert count_words(text) == expected


class TestCutToMaxWords:
    """Corte sin exceder max_words, sin cortar en medio de surrogates."""

    @pytest.mark.parametrize(
        "text,max_words,expected",
        [
            ("hola mundo", 1, "hola"),
            ("hola mundo", 2, "hola mundo"),
            ("tres palabras", 5, "tres palabras"),
            ("", 3, ""),
            ("a b c d e", 3, "a b c"),
        ],
    )
    def test_basic_cut(self, text: str, max_words: int, expected: str) -> None:
        """Conserva las primeras max_words del texto normalizado."""
        assert cut_to_max_words(text, max_words) == expected

    def test_max_words_one(self) -> None:
        """Un sola palabra se conserva."""
        assert cut_to_max_words("una sola", 1) == "una"

    def test_empty_text(self) -> None:
        """Texto vacío produce texto vacío sin importar max_words."""
        assert cut_to_max_words("", 10) == ""

    def test_exact_limit(self) -> None:
        """Cuando el texto tiene exactamente max_words, no se trunca."""
        assert cut_to_max_words("dos palabras", 2) == "dos palabras"
