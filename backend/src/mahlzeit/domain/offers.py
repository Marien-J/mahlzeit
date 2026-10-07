"""Offers: a planned meal proposed to a partner for a date and slot.

An offer is pending until the receiver accepts, declines or counters it, the sender withdraws it,
or its day ends. Only the pending state can change.
"""

from __future__ import annotations

from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from mahlzeit.domain.day import EntryState, Slot
from mahlzeit.domain.errors import Conflict, Forbidden, Invalid
from mahlzeit.domain.nutrition import Nutrients
from mahlzeit.domain.targets import Targets


class OfferState(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    COUNTERED = "countered"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


class Action(StrEnum):
    ACCEPT = "accept"
    DECLINE = "decline"
    COUNTER = "counter"
    WITHDRAW = "withdraw"
    EXPIRE = "expire"


_RESULT = {
    Action.ACCEPT: OfferState.ACCEPTED,
    Action.DECLINE: OfferState.DECLINED,
    Action.COUNTER: OfferState.COUNTERED,
    Action.WITHDRAW: OfferState.WITHDRAWN,
    Action.EXPIRE: OfferState.EXPIRED,
}


def next_state(state: OfferState, action: Action, *, is_sender: bool = False) -> OfferState:
    """The state after `action`. The receiver answers; only the sender withdraws; time expires."""
    if state is not OfferState.PENDING:
        raise Conflict("offer_not_pending", state=state.value)
    if action is Action.WITHDRAW and not is_sender:
        raise Forbidden("offer_not_yours")
    if action in (Action.ACCEPT, Action.DECLINE, Action.COUNTER) and is_sender:
        raise Forbidden("offer_not_yours")
    return _RESULT[action]


def is_overdue(day: date, *, today: date) -> bool:
    """Offers for a day last until that day ends."""
    return day < today


def effective_state(state: OfferState, day: date, *, today: date) -> OfferState:
    """What readers see: a pending offer whose day is over reads as expired at once, before the
    hourly job writes it down."""
    if state is OfferState.PENDING and is_overdue(day, today=today):
        return OfferState.EXPIRED
    return state


def check_receiver(sender: Hashable, receiver: Hashable) -> None:
    if sender == receiver:
        raise Invalid("offer_to_self")


@dataclass(frozen=True, slots=True)
class PlannedPart:
    """One of the receiver's parts in some entry of the day."""

    key: Hashable
    slot: str
    state: str


def replaced_by_accept(slot: str, receiver_parts: Sequence[PlannedPart]) -> list[Hashable]:
    """Which of the receiver's entries an accepted offer replaces: their planned meals in the
    slot. Logged and skipped entries stay. A snack replaces nothing, since there can be several."""
    if slot == Slot.SNACK:
        return []
    return [p.key for p in receiver_parts if p.slot == slot and p.state == EntryState.PLANNED.value]


def projection_after_accept(
    before: Targets | None, *, replaced: Nutrients, incoming: Nutrients
) -> Targets | None:
    """The receiver's day if the offer is accepted: what is left once everything planned is
    eaten, minus the incoming share, plus what the replaced plans would have used."""
    if before is None:
        return None

    def after(goal: float | None, back: float | None, new: float | None) -> float | None:
        return None if goal is None else goal + (back or 0.0) - (new or 0.0)

    return Targets(
        kcal=after(before.kcal, replaced.kcal, incoming.kcal),
        protein=after(before.protein, replaced.protein, incoming.protein),
        carbs=after(before.carbs, replaced.carbs, incoming.carbs),
        fat=after(before.fat, replaced.fat, incoming.fat),
    )
