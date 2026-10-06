import string

import pytest

from mahlzeit.i18n import t
from mahlzeit.i18n.messages import MESSAGES


def test_all_languages_have_the_same_keys() -> None:
    keys = {lang: set(messages) for lang, messages in MESSAGES.items()}
    assert set(keys) == {"de", "en", "nl"}
    assert keys["de"] == keys["en"] == keys["nl"]


@pytest.mark.parametrize("key", sorted(MESSAGES["de"]))
def test_placeholders_match_across_languages(key: str) -> None:
    def fields(text: str) -> set[str]:
        return {f for _, f, _, _ in string.Formatter().parse(text) if f}

    assert fields(MESSAGES["de"][key]) == fields(MESSAGES["en"][key]) == fields(MESSAGES["nl"][key])


def test_unknown_language_falls_back_to_german() -> None:
    assert t("fr", "push.test.body") == MESSAGES["de"]["push.test.body"]
