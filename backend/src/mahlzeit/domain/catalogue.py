"""Rules for catalogue items: categories, label plausibility, names, barcodes, servings."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from mahlzeit.domain.errors import Invalid
from mahlzeit.domain.nutrition import Nutrients

LANGS = ("de", "en", "nl")


class Category(StrEnum):
    """Doubles as the shopping-list aisle."""

    PRODUCE = "produce"
    BAKERY = "bakery"
    MEAT_FISH = "meat_fish"
    DAIRY_EGGS = "dairy_eggs"
    DRY_GOODS = "dry_goods"
    CANNED = "canned"
    FROZEN = "frozen"
    OILS_FATS = "oils_fats"
    SPICES_CONDIMENTS = "spices_condiments"
    SWEETS_SNACKS = "sweets_snacks"
    DRINKS = "drinks"
    HOUSEHOLD = "household"
    PERSONAL_CARE = "personal_care"
    OTHER = "other"


class TrackingMode(StrEnum):
    COUNTED = "counted"  # stock tracks an amount
    STATUS = "status"  # staples such as oil and spices: ok, low or out


class BaseUnit(StrEnum):
    G = "g"
    ML = "ml"


def check_label(n: Nutrients) -> None:
    """Reject values that cannot be on a real label (typos such as 3720 kcal). Gaps are fine."""
    grams = ("protein", "carbs", "sugar", "fat", "sat_fat", "fibre", "salt", "alcohol")
    bad = (
        (n.kcal is not None and not 0 <= n.kcal <= 900)
        or any((v := getattr(n, g)) is not None and not 0 <= v <= 100 for g in grams)
        or (n.sugar is not None and n.carbs is not None and n.sugar > n.carbs + 0.5)
        or (n.sat_fat is not None and n.fat is not None and n.sat_fat > n.fat + 0.5)
        or sum(getattr(n, g) or 0 for g in ("protein", "carbs", "fat", "fibre", "alcohol")) > 105
    )
    if bad:
        raise Invalid("label_implausible")


def check_names(names: Mapping[str, str | None]) -> dict[str, str]:
    cleaned = {lang: (names.get(lang) or "").strip()[:120] for lang in LANGS}
    result = {lang: v for lang, v in cleaned.items() if v}
    if not result:
        raise Invalid("item_name_required")
    return result


def check_barcode(code: str) -> str:
    """EAN-8, UPC-A, EAN-13 or GTIN-14 with a valid check digit."""
    digits = code.strip()
    if not digits.isdigit() or len(digits) not in (8, 12, 13, 14):
        raise Invalid("barcode_invalid")
    body, check = digits[:-1], int(digits[-1])
    weighted = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    if (10 - weighted % 10) % 10 != check:
        raise Invalid("barcode_invalid")
    return digits


def check_serving(label: str, amount: float) -> tuple[str, float]:
    label = label.strip()
    if not 1 <= len(label) <= 40 or not 0 < amount <= 5000:
        raise Invalid("serving_invalid")
    return label, float(amount)


def display_name(names: Mapping[str, str | None], language: str) -> str:
    """User language, then German, then English (as the brief asks)."""
    for lang in (language, "de", "en", "nl"):
        if names.get(lang):
            return names[lang] or ""
    return ""
