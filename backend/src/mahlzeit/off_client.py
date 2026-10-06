"""HTTP adapter for Open Food Facts. Calls go through services, which rate-limit and cache them."""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from mahlzeit import __version__
from mahlzeit.config import get_settings

PRODUCT_FIELDS = (
    "code,product_name,product_name_de,product_name_en,product_name_nl,brands,quantity,"
    "product_quantity,product_quantity_unit,serving_size,serving_quantity,nutriments,"
    "nutrition_data_per,categories_tags,image_front_small_url"
)


class OffUnavailable(Exception):
    pass


class OffClient(Protocol):
    def product(self, code: str) -> dict[str, Any]: ...
    def search(self, query: str, language: str) -> list[dict[str, Any]]: ...


class HttpOffClient:
    def _headers(self) -> dict[str, str]:
        s = get_settings()
        return {"User-Agent": f"Mahlzeit/{__version__} ({s.off_contact or s.base_url})"}

    def product(self, code: str) -> dict[str, Any]:
        s = get_settings()
        try:
            r = httpx.get(
                f"{s.off_base_url}/api/v3/product/{code}.json",
                params={"fields": PRODUCT_FIELDS},
                headers=self._headers(),
                timeout=8,
            )
        except httpx.HTTPError as err:
            raise OffUnavailable(str(err)) from err
        if r.status_code >= 500:
            raise OffUnavailable(f"status {r.status_code}")
        data: dict[str, Any] = r.json()
        return data

    def search(self, query: str, language: str) -> list[dict[str, Any]]:
        s = get_settings()
        try:
            r = httpx.get(
                f"{s.off_search_url}/search",
                params={"q": query, "langs": language, "page_size": 10, "fields": PRODUCT_FIELDS},
                headers=self._headers(),
                timeout=8,
            )
        except httpx.HTTPError as err:
            raise OffUnavailable(str(err)) from err
        if r.status_code != 200:
            raise OffUnavailable(f"status {r.status_code}")
        hits: list[dict[str, Any]] = r.json().get("hits") or []
        return hits


_client: OffClient | None = None


def get_off_client() -> OffClient:
    global _client
    if _client is None:
        _client = HttpOffClient()
    return _client


def set_off_client(client: OffClient | None) -> None:
    """Tests replace the network client with a fake."""
    global _client
    _client = client
