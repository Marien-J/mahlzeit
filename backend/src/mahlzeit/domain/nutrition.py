"""Nutrition maths. Values are per 100 g or 100 ml unless scaled to an amount.

Energy is stored as given and never recomputed from the macros. Missing values stay missing:
totals sum what is known and report which nutrients were incomplete (roughly right beats exact).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields, replace

NUTRIENTS = ("kcal", "protein", "carbs", "sugar", "fat", "sat_fat", "fibre", "salt", "alcohol")


@dataclass(frozen=True, slots=True)
class Nutrients:
    kcal: float | None = None
    protein: float | None = None
    carbs: float | None = None
    sugar: float | None = None
    fat: float | None = None
    sat_fat: float | None = None
    fibre: float | None = None
    salt: float | None = None
    alcohol: float | None = None

    def times(self, factor: float) -> Nutrients:
        return Nutrients(**{n: (None if v is None else v * factor) for n, v in self.items()})

    def scaled(self, amount: float) -> Nutrients:
        """Values per 100 → values for `amount` g or ml."""
        return self.times(amount / 100)

    def items(self) -> list[tuple[str, float | None]]:
        return [(f.name, getattr(self, f.name)) for f in fields(self)]

    def as_dict(self) -> dict[str, float | None]:
        return dict(self.items())

    @classmethod
    def from_mapping(cls, values: Mapping[str, float | None]) -> Nutrients:
        return cls(**{n: values.get(n) for n in NUTRIENTS})


ZERO = Nutrients(**{n: 0.0 for n in NUTRIENTS})


@dataclass(frozen=True, slots=True)
class Totals:
    values: Nutrients
    incomplete: frozenset[str]


def total(parts: Iterable[Nutrients]) -> Totals:
    sums = dict.fromkeys(NUTRIENTS, 0.0)
    incomplete: set[str] = set()
    for part in parts:
        for name, value in part.items():
            if value is None:
                incomplete.add(name)
            else:
                sums[name] += value
    return Totals(values=Nutrients(**sums), incomplete=frozenset(incomplete))


def per_serving(dish: Nutrients, *, servings: float) -> Nutrients:
    if servings <= 0:
        raise ValueError("servings must be positive")
    return dish.times(1 / servings)


def per_cooked_gram(dish: Nutrients, *, cooked_yield_g: float) -> Nutrients:
    """The whole dish → values per 100 g of the cooked result."""
    if cooked_yield_g <= 0:
        raise ValueError("cooked yield must be positive")
    return dish.times(100 / cooked_yield_g)


@dataclass(frozen=True, slots=True)
class Part:
    """One component of a meal entry, already scaled to the whole dish."""

    key: str
    nutrients: Nutrients


def intake(
    parts: Iterable[Part], *, share: float, exact_fraction: Mapping[str, float] | None = None
) -> Totals:
    """One person's intake: the dish times their share, with exact portions overriding per part.

    `exact_fraction` maps a part key to the fraction of that part the person actually ate
    (from an exact amount they weighed)."""
    if not 0 < share <= 1:
        raise ValueError("share must be in (0, 1]")
    exact = exact_fraction or {}
    return total(p.nutrients.times(exact.get(p.key, share)) for p in parts)


def rounded(n: Nutrients) -> Nutrients:
    """Display rounding: whole kcal, one decimal for grams, two for salt."""

    def r(name: str, v: float | None) -> float | None:
        if v is None:
            return None
        digits = 0 if name == "kcal" else 2 if name == "salt" else 1
        return round(v, digits)

    return replace(n, **{name: r(name, v) for name, v in n.items()})
