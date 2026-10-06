"""Server-side strings: emails and push notifications. The UI has its own catalogues."""

from __future__ import annotations

from typing import Any

from mahlzeit.i18n.messages import MESSAGES

FALLBACKS = ("de", "en")


def t(language: str, key: str, **params: Any) -> str:
    for lang in (language, *FALLBACKS):
        text = MESSAGES.get(lang, {}).get(key)
        if text is not None:
            return text.format(**params)
    raise KeyError(key)
