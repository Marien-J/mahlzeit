"""Rules for the day: slots, default times, how far ahead, amounts."""

from __future__ import annotations

from datetime import date, time, timedelta
from enum import StrEnum

from mahlzeit.domain.errors import Invalid

MAX_PLAN_DAYS = 30
MAX_AMOUNT = 100_000  # g or ml in one component


class Slot(StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


ANCHORS = (Slot.BREAKFAST, Slot.LUNCH, Slot.DINNER)
_DEFAULT_TIMES = {Slot.BREAKFAST: time(8, 0), Slot.LUNCH: time(12, 30), Slot.DINNER: time(19, 0)}


class EntryState(StrEnum):
    PLANNED = "planned"
    LOGGED = "logged"
    SKIPPED = "skipped"


def default_time(slot: Slot, *, now: time) -> time:
    """Anchors have fixed defaults; a snack starts at the current time."""
    return _DEFAULT_TIMES.get(slot, now.replace(second=0, microsecond=0))


def check_entry_date(day: date, *, today: date) -> None:
    if day > today + timedelta(days=MAX_PLAN_DAYS):
        raise Invalid("date_too_far_ahead", max_days=MAX_PLAN_DAYS)


def entry_state_for(day: date, *, today: date) -> str:
    return EntryState.PLANNED.value if day > today else EntryState.LOGGED.value


def check_amount(amount: float) -> float:
    if not 0 < amount <= MAX_AMOUNT:
        raise Invalid("amount_invalid", max=MAX_AMOUNT)
    return float(amount)
