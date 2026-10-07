"""Recipe rules: fields, portions from a cooked weight, scaling for the shopping list."""

from __future__ import annotations

from collections.abc import Hashable, Sequence
from enum import StrEnum

from mahlzeit.domain.errors import Invalid

MAX_SERVINGS = 100
MAX_YIELD_G = 100_000
MAX_PORTIONS = 20
MAX_NOTES = 4000


class RecipeKind(StrEnum):
    RECIPE = "recipe"
    SAVED_MEAL = "saved_meal"  # a one-serving recipe for one-tap logging


def check_name(name: str) -> str:
    cleaned = name.strip()[:120]
    if not cleaned:
        raise Invalid("recipe_name_required")
    return cleaned


def check_servings(kind: RecipeKind, servings: float) -> float:
    if kind is RecipeKind.SAVED_MEAL:
        if servings != 1:
            raise Invalid("servings_invalid", max=1)
    elif not 0 < servings <= MAX_SERVINGS:
        raise Invalid("servings_invalid", max=MAX_SERVINGS)
    return float(servings)


def check_cooked_yield(grams: float | None) -> float | None:
    if grams is None:
        return None
    if not 0 < grams <= MAX_YIELD_G:
        raise Invalid("cooked_yield_invalid", max=MAX_YIELD_G)
    return float(grams)


def check_notes(notes: str | None) -> str | None:
    return (notes or "").strip()[:MAX_NOTES] or None


def check_portions(portions: float, *, most: float = MAX_PORTIONS) -> float:
    """Portions eaten in one meal (at most 20), or bought for the list (`most`: a whole batch)."""
    if not 0 < portions <= most:
        raise Invalid("portions_invalid", max=most)
    return float(portions)


def portions_from_cooked(grams: float, *, cooked_yield_g: float | None, servings: float) -> float:
    """A portion weighed after cooking, as portions of the recipe (one portion = one serving)."""
    if cooked_yield_g is None:
        raise Invalid("cooked_yield_missing")
    if grams <= 0:
        raise Invalid("amount_invalid")
    return grams / cooked_yield_g * servings


def scale[K: Hashable](
    ingredients: Sequence[tuple[K, float]], *, servings: float, portions: float
) -> list[tuple[K, float]]:
    """Ingredient amounts for `portions` of a recipe written for `servings`."""
    factor = portions / servings
    return [(key, amount * factor) for key, amount in ingredients]


def combine[K: Hashable](ingredients: Sequence[tuple[K, float]]) -> list[tuple[K, float]]:
    """Add up the same item listed more than once, keeping the first-seen order."""
    sums: dict[K, float] = {}
    for key, amount in ingredients:
        sums[key] = sums.get(key, 0.0) + amount
    return list(sums.items())


def _number(value: float, language: str, digits: int) -> str:
    text = f"{value:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text if language == "en" else text.replace(".", ",")


def quantity_text(amount: float, unit: str, language: str) -> str:
    """An amount as a shopping list quantity: '250 g', '1,25 kg', '1.5 l'."""
    if amount >= 1000:
        return f"{_number(amount / 1000, language, 2)} {'kg' if unit == 'g' else 'l'}"
    digits = 0 if amount >= 10 else 1
    return f"{_number(amount, language, digits)} {unit}"
