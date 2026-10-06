"""Search text normalisation: case, umlauts, accents and punctuation do not matter."""

from __future__ import annotations

import re
import unicodedata

_NON_WORD = re.compile(r"[^a-z0-9]+")


def normalize(text: str) -> str:
    folded = text.casefold().replace("ß", "ss")
    stripped = "".join(
        ch for ch in unicodedata.normalize("NFKD", folded) if not unicodedata.combining(ch)
    )
    return _NON_WORD.sub(" ", stripped).strip()
