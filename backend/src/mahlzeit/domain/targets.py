"""Daily targets with history, training and rest days."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from mahlzeit.domain.nutrition import Nutrients

DEFAULT_WEEK_PATTERN = "RRRRRRR"


class DayType(StrEnum):
    TRAINING = "training"
    REST = "rest"


@dataclass(frozen=True, slots=True)
class Targets:
    """Optional daily targets. A missing value means the person tracks totals only."""

    kcal: float | None = None
    protein: float | None = None
    carbs: float | None = None
    fat: float | None = None


@dataclass(frozen=True, slots=True)
class TargetSet:
    valid_from: date
    day_type: DayType
    targets: Targets


def parse_week_pattern(pattern: str) -> str:
    """Seven letters, Monday first: T for training, R for rest."""
    p = pattern.strip().upper()
    if len(p) != 7 or set(p) - {"T", "R"}:
        raise ValueError("week pattern must be seven letters T or R, Monday first")
    return p


def day_type_for(
    day: date,
    *,
    pattern: str,
    override: DayType | None = None,
    has_workout: bool = False,
) -> DayType:
    if override is not None:
        return override
    if has_workout:
        return DayType.TRAINING
    return DayType.TRAINING if parse_week_pattern(pattern)[day.weekday()] == "T" else DayType.REST


def target_for(day: date, day_type: DayType, sets: Iterable[TargetSet]) -> Targets | None:
    """The targets valid on `day` for that day type: the newest set that started on or before it."""
    valid = [s for s in sets if s.day_type is day_type and s.valid_from <= day]
    if not valid:
        return None
    return max(valid, key=lambda s: s.valid_from).targets


def remaining(targets: Targets | None, eaten: Nutrients) -> Targets | None:
    """What is left today. Negative means over target. Nutrients without a target stay None."""
    if targets is None:
        return None

    def left(goal: float | None, used: float | None) -> float | None:
        return None if goal is None else goal - (used or 0.0)

    return Targets(
        kcal=left(targets.kcal, eaten.kcal),
        protein=left(targets.protein, eaten.protein),
        carbs=left(targets.carbs, eaten.carbs),
        fat=left(targets.fat, eaten.fat),
    )
