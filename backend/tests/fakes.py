"""Fakes for outside services."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mahlzeit.off_client import OffUnavailable

NUTELLA = json.loads((Path(__file__).parent / "fixtures" / "off_product_complete.json").read_text())


class FakeOff:
    def __init__(
        self, products: dict[str, dict[str, Any]] | None = None, down: bool = False
    ) -> None:
        self.products = products if products is not None else {"4008400401621": NUTELLA}
        self.down = down
        self.product_calls: list[str] = []
        self.search_calls: list[str] = []

    def product(self, code: str) -> dict[str, Any]:
        self.product_calls.append(code)
        if self.down:
            raise OffUnavailable("down")
        return self.products.get(code) or {
            "status": "failure",
            "result": {"id": "product_not_found"},
        }

    def search(self, query: str, language: str) -> list[dict[str, Any]]:
        self.search_calls.append(query)
        if self.down:
            raise OffUnavailable("down")
        return [p["product"] | {"code": code} for code, p in self.products.items()]
