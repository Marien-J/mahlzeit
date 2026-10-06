import pytest

from mahlzeit.domain.search import normalize


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Käse", "kase"),
        ("Hähnchen Brustfilet, roh", "hahnchen brustfilet roh"),
        ("Weißbrot", "weissbrot"),
        ("  Crème   fraîche ", "creme fraiche"),
        ("Gouda 48 % Fett i. Tr.", "gouda 48 fett i tr"),
        ("ÉPINARDS", "epinards"),
        ("", ""),
    ],
)
def test_normalize(text: str, expected: str) -> None:
    assert normalize(text) == expected
