"""Stock: a ledger of signed movements per item. The level is their sum, never shown below zero.

Purchases put stock in, eaten meals take the whole dish out once, waste and corrections move it
by hand. Stock is advisory: it never blocks logging, and a shortfall (eating more than was in
stock) is written down quietly as a correction so the level lands on zero.
"""

from __future__ import annotations

import re
from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from mahlzeit.domain.errors import Invalid

MAX_STOCK = 1_000_000  # g or ml of one item
USUAL_MIN_PURCHASES = 3
USUAL_WINDOW_DAYS = 90
PLAN_DAYS_DEFAULT = 3
PLAN_DAYS_MAX = 14
PURCHASE_DAYS_BACK = 365
_EPSILON = 1e-6


class Reason(StrEnum):
    PURCHASE = "purchase"
    CONSUMPTION = "consumption"
    CORRECTION = "correction"
    WASTE = "waste"


class Source(StrEnum):
    """Where a movement comes from: a purchase line, an eaten entry, the shortfall of an eaten
    entry, the pantry check, or a change by hand."""

    PURCHASE = "purchase"
    ENTRY = "entry"
    SHORTFALL = "shortfall"
    PANTRY = "pantry"
    MANUAL = "manual"


class Status(StrEnum):
    OK = "ok"
    LOW = "low"
    OUT = "out"


# --- turning a list quantity into an amount --------------------------------------------------

_NUMBER = r"(?P<n>\d+(?:[.,]\d+)?)"
_WEIGHT = re.compile(rf"^{_NUMBER}\s*(?P<u>kg|g|l|ml)\.?$", re.IGNORECASE)
_PIECES = re.compile(
    rf"^{_NUMBER}\s*(?:x|\u00d7|stk\.?|stück|st\.?|pck\.?|pkg\.?|packung(?:en)?|dosen?|"
    r"flaschen?|becher|bund|glas|gläser|beutel|netz)?$",
    re.IGNORECASE,
)
_FACTOR = {"g": 1.0, "ml": 1.0, "kg": 1000.0, "l": 1000.0}


def _number(text: str) -> float:
    return float(text.replace(",", "."))


def amount_from_quantity(
    text: str | None,
    *,
    base_unit: str,
    package_size: float | None,
    serving: float | None = None,
) -> float | None:
    """'500 g', '1,5 kg', '2 Pck', '3' or nothing → grams or millilitres, or None when it
    cannot be told. Pieces and packages count in package sizes (else the first serving); no
    quantity at all means one package. Grams and millilitres are taken as equal (roughly right)."""
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return package_size
    if m := _WEIGHT.match(cleaned):
        return _number(m.group("n")) * _FACTOR[m.group("u").lower()]
    if m := _PIECES.match(cleaned):
        each = package_size or serving
        return _number(m.group("n")) * each if each else None
    return None


# --- levels -----------------------------------------------------------------------------------


def level(amounts: Iterable[float]) -> float:
    return sum(amounts, 0.0)


def shown(value: float) -> float:
    """Stock is never shown below zero."""
    return max(value, 0.0)


def shortfall(*, want: float, level_without: float) -> float:
    """What eating `want` lacks given the level without it: written down as a correction so
    the level lands on zero, never below."""
    return max(want - level_without, 0.0) if want > 0 else 0.0


def check_amount(amount: float) -> float:
    if not 0 <= amount <= MAX_STOCK:
        raise Invalid("stock_amount_invalid", max=MAX_STOCK)
    return float(amount)


def correction(*, level_now: float, counted: float) -> float:
    """The movement that makes the level what was counted."""
    return check_amount(counted) - level_now


def waste(*, level_now: float, amount: float) -> float:
    """Thrown away: at most what is there."""
    if amount <= 0:
        raise Invalid("stock_amount_invalid", max=MAX_STOCK)
    return -min(check_amount(amount), shown(level_now))


def next_status(status: Status | None) -> Status:
    """One tap moves a status-only item along: ok → low → out → ok."""
    order = [Status.OK, Status.LOW, Status.OUT]
    if status is None:
        return Status.LOW
    return order[(order.index(status) + 1) % len(order)]


def step(*, package_size: float | None, serving: float | None) -> float:
    """How much one tap of the pantry stepper moves: a package, a serving, or 100 g."""
    return package_size or serving or 100.0


# --- consumption ------------------------------------------------------------------------------


def dish_use[K: Hashable](components: Sequence[tuple[K | None, float | None]]) -> dict[K, float]:
    """The whole dish by item. Foods without a catalogue item are not in stock."""
    use: dict[K, float] = {}
    for item, amount in components:
        if item is not None and amount:
            use[item] = use.get(item, 0.0) + amount
    return use


def consumption[K: Hashable](
    components: Sequence[tuple[K | None, float | None]], *, eaten: bool, eaten_out: bool
) -> dict[K, float]:
    """What a meal takes out of stock: the whole dish once as soon as anyone has eaten it,
    nothing for a meal eaten out."""
    if not eaten or eaten_out:
        return {}
    return dish_use(components)


@dataclass(frozen=True, slots=True)
class Change:
    """A movement to write for a meal: what it takes out (source entry) or the shortfall it
    fills in (source shortfall)."""

    item: Hashable
    day: date
    source: Source
    amount: float


def sync_entry[K: Hashable](
    *,
    booked: Mapping[tuple[K, date], float],
    shortfalls: Mapping[tuple[K, date], float],
    wanted: Mapping[K, float],
    day: date,
    levels: Mapping[K, float],
) -> list[Change]:
    """Bring a meal's movements in line with what it now takes out of stock.

    `booked` and `shortfalls` are the meal's movements so far by item and day, `wanted` what it
    takes out now (on `day`), `levels` the household's levels with all movements. Taking more
    than is there fills the rest with a shortfall; giving back undoes the meal's own shortfall
    first, so a meal logged by mistake and removed leaves stock as it was."""
    now = dict(levels)
    result: list[Change] = []
    keys = list(booked) + [(item, day) for item in wanted if (item, day) not in booked]
    for key in keys:
        item, on = key
        target = -wanted.get(item, 0.0) if on == day else 0.0
        delta = target - booked.get(key, 0.0)
        if abs(delta) < _EPSILON:
            continue
        result.append(Change(item, on, Source.ENTRY, delta))
        if delta < 0:
            fill = shortfall(want=-delta, level_without=now.get(item, 0.0))
        else:
            fill = -min(delta, shortfalls.get(key, 0.0))
        if abs(fill) > _EPSILON:
            result.append(Change(item, on, Source.SHORTFALL, fill))
        now[item] = now.get(item, 0.0) + delta + fill
    return result


# --- suggestions ------------------------------------------------------------------------------


def missing[K: Hashable](needs: Mapping[K, float], levels: Mapping[K, float]) -> dict[K, float]:
    """What planned meals need beyond what is in stock."""
    result: dict[K, float] = {}
    for item, need in needs.items():
        lack = need - shown(levels.get(item, 0.0))
        if lack > _EPSILON:
            result[item] = lack
    return result


def is_usual(*, purchases: int) -> bool:
    """Enough history to call something a usual purchase."""
    return purchases >= USUAL_MIN_PURCHASES


def check_purchase_day(day: date, *, today: date) -> date:
    """A purchase is from today or the past year (a receipt found later)."""
    if not today - timedelta(days=PURCHASE_DAYS_BACK) <= day <= today:
        raise Invalid("purchase_day_invalid", days=PURCHASE_DAYS_BACK)
    return day


def check_plan_days(days: int) -> int:
    if not 1 <= days <= PLAN_DAYS_MAX:
        raise Invalid("plan_days_invalid", max=PLAN_DAYS_MAX)
    return days


# --- report -----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Movement:
    item: Hashable
    reason: Reason
    source: Source
    amount: float
    day: date


@dataclass(frozen=True, slots=True)
class ItemReport:
    purchased: float = 0.0
    logged: float = 0.0
    wasted: float = 0.0
    corrected: float = 0.0  # by hand and by the pantry check, signed
    shortfall: float = 0.0  # added because more was eaten than was in stock


def report(movements: Iterable[Movement]) -> dict[Hashable, ItemReport]:
    """Purchased, logged, wasted and corrected amounts per item."""
    sums: dict[Hashable, dict[str, float]] = {}
    for m in movements:
        row = sums.setdefault(m.item, dict.fromkeys(ItemReport.__slots__, 0.0))
        match m.reason:
            case Reason.PURCHASE:
                row["purchased"] += m.amount
            case Reason.CONSUMPTION:
                row["logged"] -= m.amount
            case Reason.WASTE:
                row["wasted"] -= m.amount
            case Reason.CORRECTION if m.source is Source.SHORTFALL:
                row["shortfall"] += m.amount
            case Reason.CORRECTION:
                row["corrected"] += m.amount
    return {item: ItemReport(**values) for item, values in sums.items()}
