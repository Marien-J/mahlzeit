"""Mapping Open Food Facts API v3 product reads to item drafts. Pure: no network here."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from mahlzeit.domain.catalogue import BaseUnit, Category
from mahlzeit.domain.nutrition import Nutrients

# Label values a draft must have before it counts as complete (alcohol only "where known").
REQUIRED = ("kcal", "protein", "carbs", "sugar", "fat", "sat_fat", "fibre", "salt")

_FIELDS = {
    "protein": "proteins_100g",
    "carbs": "carbohydrates_100g",
    "sugar": "sugars_100g",
    "fat": "fat_100g",
    "sat_fat": "saturated-fat_100g",
    "fibre": "fiber_100g",
    "salt": "salt_100g",
    "alcohol": "alcohol_100g",
}

# First matching tag wins; order matters (spreads before chocolate).
_CATEGORY_HINTS: list[tuple[str, Category]] = [
    ("beverages", Category.DRINKS),
    ("frozen", Category.FROZEN),
    ("spreads", Category.SPICES_CONDIMENTS),
    ("condiments", Category.SPICES_CONDIMENTS),
    ("sauces", Category.SPICES_CONDIMENTS),
    ("spices", Category.SPICES_CONDIMENTS),
    ("honeys", Category.SPICES_CONDIMENTS),
    ("cheeses", Category.DAIRY_EGGS),
    ("yogurts", Category.DAIRY_EGGS),
    ("milks", Category.DAIRY_EGGS),
    ("dairies", Category.DAIRY_EGGS),
    ("eggs", Category.DAIRY_EGGS),
    ("meats", Category.MEAT_FISH),
    ("fishes", Category.MEAT_FISH),
    ("seafood", Category.MEAT_FISH),
    ("breads", Category.BAKERY),
    ("oils", Category.OILS_FATS),
    ("fats", Category.OILS_FATS),
    ("canned", Category.CANNED),
    ("chocolates", Category.SWEETS_SNACKS),
    ("snacks", Category.SWEETS_SNACKS),
    ("confectioneries", Category.SWEETS_SNACKS),
    ("biscuits", Category.SWEETS_SNACKS),
    ("cereals", Category.DRY_GOODS),
    ("pastas", Category.DRY_GOODS),
    ("rices", Category.DRY_GOODS),
    ("legumes", Category.DRY_GOODS),
    ("nuts", Category.DRY_GOODS),
    ("fruits", Category.PRODUCE),
    ("vegetables", Category.PRODUCE),
]


@dataclass(frozen=True)
class ItemDraft:
    barcode: str
    names: dict[str, str]
    brand: str | None
    base_unit: BaseUnit
    package_size: float | None
    servings: list[tuple[str, float]]
    nutrients: Nutrients
    category: Category
    image_url: str | None = None
    missing: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return bool(self.names) and not self.missing


def _num(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f >= 0 else None


def _category(tags: list[str]) -> Category:
    for hint, category in _CATEGORY_HINTS:
        if any(hint in tag for tag in tags):
            return category
    return Category.OTHER


def map_product(raw: Mapping[str, Any]) -> ItemDraft | None:
    product = raw.get("product")
    if raw.get("status") == "failure" or not isinstance(product, dict):
        return None
    nutr = product.get("nutriments") or {}

    kcal = _num(nutr.get("energy-kcal_100g"))
    if kcal is None and (kj := _num(nutr.get("energy-kj_100g"))) is not None:
        kcal = round(kj / 4.184, 1)
    values: dict[str, float | None] = {"kcal": kcal}
    values |= {name: _num(nutr.get(key)) for name, key in _FIELDS.items()}
    nutrients = Nutrients.from_mapping(values)

    names = {
        lang: str(product.get(f"product_name_{lang}")).strip()
        for lang in ("de", "en", "nl")
        if str(product.get(f"product_name_{lang}") or "").strip()
    }
    if not names and str(product.get("product_name") or "").strip():
        names = {"de": str(product["product_name"]).strip()}

    per = str(product.get("nutrition_data_per") or "")
    unit_raw = str(product.get("product_quantity_unit") or "").lower()
    base_unit = BaseUnit.ML if unit_raw == "ml" or per.endswith("ml") else BaseUnit.G

    servings: list[tuple[str, float]] = []
    serving = _num(product.get("serving_quantity"))
    if serving and serving > 0:
        servings.append(("serving", serving))

    brand = str(product.get("brands") or "").split(",")[0].strip() or None
    return ItemDraft(
        barcode=str(raw.get("code") or product.get("code") or ""),
        names=names,
        brand=brand,
        base_unit=base_unit,
        package_size=_num(product.get("product_quantity")),
        servings=servings,
        nutrients=nutrients,
        category=_category(list(product.get("categories_tags") or [])),
        image_url=product.get("image_front_small_url"),
        missing=[n for n in REQUIRED if getattr(nutrients, n) is None],
    )
