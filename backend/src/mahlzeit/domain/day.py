"""Rules for the day: slots, default times, how far ahead, amounts."""

from __future__ import annotations

from collections.abc import Hashable, Sequence
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


def check_plan_date(day: date, *, today: date) -> None:
    """Plans are for today or later, up to 30 days ahead."""
    if day < today:
        raise Invalid("plan_in_past")
    check_entry_date(day, today=today)


_STEP = 30  # minutes: how far an entry dragged to the top or bottom sits from its neighbour
_LAST_MINUTE = 23 * 60 + 59


def _minutes(at: time) -> int:
    return at.hour * 60 + at.minute


def _time(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)


def retime[K: Hashable](
    order: Sequence[tuple[K, time]], moved: K, *, before: K | None
) -> dict[K, time]:
    """New times after dragging `moved` in front of `before` (to the end when None).

    `order` is the day as shown, entry keys with their times. Entries are ordered by time, so a
    drag means choosing a time between the new neighbours; when there is no free minute there,
    the entries after it move on by a minute. Returns only the times that change."""
    if moved not in dict(order) or (before is not None and before not in dict(order)):
        raise Invalid("order_invalid")
    if before == moved:
        return {}  # dropped on itself
    current = dict(order)
    rest = [(k, _minutes(a)) for k, a in order if k != moved]
    index = len(rest) if before is None else [k for k, _ in rest].index(before)
    prev = rest[index - 1][1] if index > 0 else None
    nxt = rest[index][1] if index < len(rest) else None
    here = _minutes(current[moved])
    if prev is None and nxt is None:
        new = here
    elif prev is None:
        assert nxt is not None
        new = here if here < nxt else max(nxt - _STEP, 0)
    elif nxt is None:
        new = here if here > prev else min(prev + _STEP, _LAST_MINUTE)
    else:
        new = here if prev < here < nxt else prev + (nxt - prev) // 2
    sequence = [*rest[:index], (moved, new), *rest[index:]]
    for i in range(max(index, 1), len(sequence)):
        key, at = sequence[i]
        if at > sequence[i - 1][1]:
            continue
        if sequence[i - 1][1] >= _LAST_MINUTE:
            raise Invalid("reorder_no_room")
        sequence[i] = (key, sequence[i - 1][1] + 1)
    return {k: _time(a) for k, a in sequence if _time(a) != current[k]}
