"""Shares of a joint meal: who ate how much of one dish.

Shares are set by feel: half and half by default. A person who weighs can enter the exact amount
of a component instead, which overrides the share for that component (see nutrition.intake).
"""

from __future__ import annotations

from collections.abc import Hashable, Sequence
from dataclasses import dataclass

from mahlzeit.domain.day import MAX_AMOUNT
from mahlzeit.domain.errors import Invalid

MIN_SHARE = 0.05
PRESETS = (0.25, 0.5, 0.75)
_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class PartShare:
    """One person's part of a meal. A logged part belongs to its owner and is never moved."""

    key: Hashable
    share: float
    logged: bool = False


def equal(people: int) -> float:
    if people < 1:
        raise ValueError("a meal needs at least one person")
    return 1 / people


def check(share: float, *, people: int) -> float:
    """A share is at least 5 %, and on a joint meal leaves 5 % for every other person."""
    most = 1 - MIN_SHARE * (max(people, 1) - 1)
    if not MIN_SHARE - _EPSILON <= share <= most + _EPSILON:
        raise Invalid("share_invalid", min=MIN_SHARE, max=round(most, 2))
    return float(min(max(share, MIN_SHARE), most))


def rebalance(parts: Sequence[PartShare], *, who: Hashable, share: float) -> dict[Hashable, float]:
    """New shares for the others after `who` takes `share`.

    Everyone else who has not eaten yet shares the rest of the dish, in proportion to what they
    had. A logged part stays as its owner left it. Returns only the parts that change."""
    others = [p for p in parts if p.key != who]
    open_parts = [p for p in others if not p.logged]
    if not open_parts:
        return {}
    return _spread(1 - share - sum(p.share for p in others if p.logged), open_parts)


def _spread(pool: float, open_parts: Sequence[PartShare]) -> dict[Hashable, float]:
    """Share `pool` among `open_parts` in proportion to what they had. Nobody goes below the
    minimum: whoever would is held there and the others share what is left."""
    result: dict[Hashable, float] = {}
    remaining = list(open_parts)
    while remaining:
        weight = sum(p.share for p in remaining)
        trial = {
            p.key: pool * p.share / weight if weight > 0 else pool / len(remaining)
            for p in remaining
        }
        low = [p for p in remaining if trial[p.key] < MIN_SHARE]
        if not low:
            result.update(trial)
            break
        for p in low:
            result[p.key] = MIN_SHARE
            pool -= MIN_SHARE
        remaining = [p for p in remaining if p not in low]
    return result


def joining(parts: Sequence[PartShare]) -> tuple[float, dict[Hashable, float]]:
    """A newcomer joins a meal: (their share, the new shares of those already on it).

    Open parts and the newcomer split what the logged parts leave, evenly."""
    logged = sum(p.share for p in parts if p.logged)
    open_parts = [p for p in parts if not p.logged]
    each = max((1 - logged) / (len(open_parts) + 1), MIN_SHARE)
    return each, {p.key: each for p in open_parts}


def exact_fraction(*, component_amount: float, eaten: float) -> float:
    """The fraction of a component's total amount a person weighed out for themselves."""
    if component_amount <= 0 or not 0 < eaten <= MAX_AMOUNT:
        raise Invalid("exact_amount_invalid", max=MAX_AMOUNT)
    return eaten / component_amount


def normalize(parts: Sequence[PartShare]) -> dict[Hashable, float]:
    """Shares after someone leaves a meal: those who have not eaten yet fill what the logged
    parts leave, in proportion to what they had."""
    open_parts = [p for p in parts if not p.logged]
    if not open_parts:
        return {}
    room = max(1 - sum(p.share for p in parts if p.logged), MIN_SHARE)
    return {k: min(v, 1.0) for k, v in _spread(room, open_parts).items()}
