"""Offers: a planned meal proposed to a partner for a date and slot.

The receiver accepts (the meal becomes joint and replaces their own plan for that slot),
declines, or counters with a different meal for the same slot. The sender can withdraw a pending
offer, and every pending offer ends when its day does. A new offer for a slot is always allowed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import date, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from mahlzeit import clock
from mahlzeit.domain import offers as rules
from mahlzeit.domain import shares as share_rules
from mahlzeit.domain.day import EntryState, Slot
from mahlzeit.domain.errors import Conflict, Invalid, NotFound
from mahlzeit.domain.nutrition import Totals, intake, total
from mahlzeit.domain.offers import Action, OfferState, PlannedPart
from mahlzeit.domain.permissions import Actor, Client, require_household
from mahlzeit.domain.targets import Targets
from mahlzeit.models import MealEntry, MealParticipant, Offer, User
from mahlzeit.services import audit, push
from mahlzeit.services import day as day_service
from mahlzeit.services.day import EntryInput
from mahlzeit.services.targets import today_for

ENTITY = "offer"
RECENT_DAYS = 14
DEFAULT_SHARE = 0.5


@dataclass(frozen=True)
class Effect:
    """What accepting would do to the receiver's day (None targets: totals only)."""

    incoming: Totals
    targets: Targets | None
    projection_before: Targets | None
    projection_after: Targets | None


@dataclass(frozen=True)
class OfferView:
    offer: Offer
    state: OfferState  # as readers see it: pending offers of a past day read as expired
    sender: User
    receiver: User
    entry: MealEntry | None
    effect: Effect | None


@dataclass(frozen=True)
class Counter:
    """The meal sent back: one of the responder's own plans for the slot, or a new one."""

    entry_id: uuid.UUID | None = None
    meal: EntryInput | None = None


# --- reading ----------------------------------------------------------------------------------


def _get(db: Session, actor: Actor, offer_id: uuid.UUID, *, lock: bool = False) -> Offer:
    """An offer the actor is part of. `lock` holds the row until commit, so two answers to one
    offer (accept on one phone, withdraw on the other) cannot both go through."""
    query = select(Offer).where(Offer.id == offer_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    offer = db.scalars(query).first()
    if offer is None:
        raise NotFound("offer_not_found")
    require_household(actor, offer.household_id)
    if actor.user_id not in (offer.from_user_id, offer.to_user_id):
        raise NotFound("offer_not_found")
    return offer


def _today(db: Session, user_id: uuid.UUID) -> date:
    return today_for(db.get_one(User, user_id))


def _effect(db: Session, actor: Actor, offer: Offer, entry: MealEntry) -> Effect:
    me = db.get_one(User, actor.user_id)
    entries = day_service._entries(db, actor.household_id, offer.day)
    person = day_service.person_day(db, me, offer.day, entries)
    parts = [
        PlannedPart(key=e.id, slot=e.slot, state=p.state)
        for e in person.entries
        if (p := day_service.participant_of(e, me.id)) is not None
    ]
    replaced_ids = set(rules.replaced_by_accept(offer.slot, parts))
    replaced = total(
        day_service.participant_intake(e, p).values
        for e in person.entries
        if e.id in replaced_ids and (p := day_service.participant_of(e, me.id)) is not None
    )
    incoming = intake(day_service.entry_parts(entry), share=offer.share)
    return Effect(
        incoming=incoming,
        targets=person.targets,
        projection_before=person.projection,
        projection_after=rules.projection_after_accept(
            person.projection, replaced=replaced.values, incoming=incoming.values
        ),
    )


def _view(db: Session, actor: Actor, offer: Offer) -> OfferView:
    state = rules.effective_state(
        OfferState(offer.state), offer.day, today=_today(db, offer.to_user_id)
    )
    entry = day_service.find_entry(db, actor, offer.entry_id) if offer.entry_id else None
    effect = None
    if state is OfferState.PENDING and entry is not None and offer.to_user_id == actor.user_id:
        effect = _effect(db, actor, offer, entry)
    return OfferView(
        offer=offer,
        state=state,
        sender=db.get_one(User, offer.from_user_id),
        receiver=db.get_one(User, offer.to_user_id),
        entry=entry,
        effect=effect,
    )


def get(db: Session, actor: Actor, offer_id: uuid.UUID) -> OfferView:
    return _view(db, actor, _get(db, actor, offer_id))


def list_offers(db: Session, actor: Actor, *, include_closed: bool = False) -> list[OfferView]:
    """Offers to or from the actor: the open ones, or also those of the last two weeks that
    were answered, withdrawn or expired. Newest first."""
    since = _today(db, actor.user_id) - timedelta(days=RECENT_DAYS)
    rows = db.scalars(
        select(Offer)
        .where(
            Offer.household_id == actor.household_id,
            or_(Offer.from_user_id == actor.user_id, Offer.to_user_id == actor.user_id),
            Offer.day >= since,
        )
        .order_by(Offer.created_at.desc(), Offer.id.desc())
    )
    views = [_view(db, actor, o) for o in rows]
    return views if include_closed else [v for v in views if v.state is OfferState.PENDING]


def pending_count(db: Session, actor: Actor) -> int:
    """Offers waiting for the actor's answer (the badge)."""
    return sum(1 for v in list_offers(db, actor) if v.offer.to_user_id == actor.user_id)


# --- writing ----------------------------------------------------------------------------------


def _snapshot(offer: Offer) -> dict[str, object]:
    return {
        "from": str(offer.from_user_id),
        "to": str(offer.to_user_id),
        "entry": str(offer.entry_id) if offer.entry_id else None,
        "day": offer.day.isoformat(),
        "slot": offer.slot,
        "share": round(offer.share, 4),
        "state": offer.state,
    }


def _close(
    db: Session, actor: Actor | None, offer: Offer, state: OfferState, *, action: str
) -> None:
    before = offer.state
    offer.state = state.value
    offer.responded_at = clock.now()
    audit.record(
        db,
        actor=actor,
        entity=ENTITY,
        entity_id=offer.id,
        action=action,
        before={"state": before},
        after={"state": offer.state},
        household_id=offer.household_id,
        client=None if actor else Client.JOB,
    )


def withdraw_open(db: Session, actor: Actor, *, entry_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """End a person's pending offers of a meal that is no longer theirs to give (it was eaten,
    moved, or they left it). Part of the caller's transaction."""
    pending = db.scalars(
        select(Offer).where(
            Offer.entry_id == entry_id,
            Offer.from_user_id == user_id,
            Offer.state == OfferState.PENDING.value,
        )
    )
    for offer in pending:
        _close(db, actor, offer, OfferState.WITHDRAWN, action="withdrawn")


def _notify(db: Session, offer: Offer, *, sender: User, receiver: User, entry: MealEntry) -> None:
    if not receiver.profile.push_offers:
        return
    kind = "counter" if offer.counter_of_id else "offer"
    push.notify(
        db,
        receiver.id,
        message=kind,
        url="/",
        params={
            "name": sender.display_name,
            "meal": day_service.entry_title(entry, receiver.language),
        },
    )


def _create(
    db: Session,
    actor: Actor,
    entry: MealEntry,
    to: User,
    *,
    share: float,
    counter_of: Offer | None = None,
) -> Offer:
    """A new pending offer from the actor. It replaces their own pending offer to the same
    person for the same day and slot."""
    sender = db.get_one(User, actor.user_id)
    previous = db.scalars(
        select(Offer).where(
            Offer.from_user_id == actor.user_id,
            Offer.to_user_id == to.id,
            Offer.day == entry.day,
            Offer.slot == entry.slot,
            Offer.state == OfferState.PENDING.value,
        )
    )
    for old in previous:
        _close(db, actor, old, OfferState.WITHDRAWN, action="withdrawn")
    offer = Offer(
        household_id=actor.household_id,
        from_user_id=actor.user_id,
        to_user_id=to.id,
        entry_id=entry.id,
        counter_of_id=counter_of.id if counter_of else None,
        day=entry.day,
        slot=entry.slot,
        share=share_rules.check(share, people=2),
        state=OfferState.PENDING.value,
    )
    db.add(offer)
    db.flush()
    audit.record(
        db,
        actor=actor,
        entity=ENTITY,
        entity_id=offer.id,
        action="counter" if counter_of else "sent",
        after=_snapshot(offer),
    )
    _notify(db, offer, sender=sender, receiver=to, entry=entry)
    return offer


def _offerable(
    db: Session, actor: Actor, entry_id: uuid.UUID, to_user_id: uuid.UUID
) -> tuple[MealEntry, User]:
    """The actor's planned meal and the person it goes to, checked."""
    entry, part = day_service.own_entry(db, actor, entry_id)
    rules.check_receiver(actor.user_id, to_user_id)
    receiver = next((m for m in day_service.others(db, actor) if m.id == to_user_id), None)
    if receiver is None:
        raise NotFound()
    if part.state != EntryState.PLANNED:
        raise Invalid("offer_meal_not_planned")
    if rules.is_overdue(entry.day, today=_today(db, actor.user_id)):
        raise Invalid("plan_in_past")
    if day_service.participant_of(entry, receiver.id) is not None:
        raise Conflict("offer_already_joint")
    return entry, receiver


def send(
    db: Session,
    actor: Actor,
    *,
    entry_id: uuid.UUID,
    to_user_id: uuid.UUID,
    share: float = DEFAULT_SHARE,
) -> OfferView:
    """Offer one of the actor's planned meals to another member. `share` is theirs of the dish."""
    entry, receiver = _offerable(db, actor, entry_id, to_user_id)
    offer = _create(db, actor, entry, receiver, share=share)
    db.commit()
    return _view(db, actor, offer)


def withdraw(db: Session, actor: Actor, offer_id: uuid.UUID) -> OfferView:
    offer = _get(db, actor, offer_id, lock=True)
    state = rules.effective_state(
        OfferState(offer.state), offer.day, today=_today(db, offer.to_user_id)
    )
    rules.next_state(state, Action.WITHDRAW, is_sender=offer.from_user_id == actor.user_id)
    _close(db, actor, offer, OfferState.WITHDRAWN, action="withdrawn")
    db.commit()
    return _view(db, actor, offer)


def _answerable(db: Session, actor: Actor, offer_id: uuid.UUID, action: Action) -> Offer:
    """A pending offer the actor may answer. One whose day is over is written down as expired."""
    offer = _get(db, actor, offer_id, lock=True)
    today = _today(db, offer.to_user_id)
    if offer.state == OfferState.PENDING and rules.is_overdue(offer.day, today=today):
        _close(db, actor, offer, OfferState.EXPIRED, action="expired")
        db.commit()
    rules.next_state(OfferState(offer.state), action, is_sender=offer.from_user_id == actor.user_id)
    return offer


def _accept(db: Session, actor: Actor, offer: Offer) -> None:
    entry = day_service.find_entry(db, actor, offer.entry_id) if offer.entry_id else None
    sender_part = day_service.participant_of(entry, offer.from_user_id) if entry else None
    if entry is None or sender_part is None or sender_part.state != EntryState.PLANNED:
        raise Conflict("offer_meal_gone")
    if day_service.participant_of(entry, actor.user_id) is not None:
        raise Conflict("offer_already_joint")
    # Their own plans for the slot make room; logged and skipped entries stay.
    mine = [
        (e, p)
        for e in day_service._entries(db, actor.household_id, offer.day)
        if (p := day_service.participant_of(e, actor.user_id)) is not None
    ]
    replace_ids = set(
        rules.replaced_by_accept(
            offer.slot, [PlannedPart(key=e.id, slot=e.slot, state=p.state) for e, p in mine]
        )
    )
    for e, p in mine:
        if e.id in replace_ids:
            before = day_service.snapshot(e)
            day_service.remove_part(db, actor, e, p)
            audit.record(
                db,
                actor=actor,
                entity="meal_entry",
                entity_id=e.id,
                action="replaced",
                before=before,
            )
    entry.participants.append(
        MealParticipant(user_id=actor.user_id, state=EntryState.PLANNED.value, share=offer.share)
    )
    db.flush()
    day_service.apply_shares(
        entry,
        share_rules.rebalance(
            day_service._part_shares(entry), who=actor.user_id, share=offer.share
        ),
    )
    audit.record(
        db,
        actor=actor,
        entity="meal_entry",
        entity_id=entry.id,
        action="joined",
        after=day_service._shares_of(entry),
    )


def respond(
    db: Session,
    actor: Actor,
    offer_id: uuid.UUID,
    action: Action,
    *,
    counter: Counter | None = None,
) -> OfferView:
    """Answer an offer made to the actor: accept, decline or counter (with `counter`)."""
    if action not in (Action.ACCEPT, Action.DECLINE, Action.COUNTER):
        raise Invalid("offer_action_invalid")
    offer = _answerable(db, actor, offer_id, action)
    if action is Action.ACCEPT:
        _accept(db, actor, offer)
        _close(db, actor, offer, OfferState.ACCEPTED, action="accepted")
    elif action is Action.DECLINE:
        _close(db, actor, offer, OfferState.DECLINED, action="declined")
    else:
        _counter(db, actor, offer, counter)
    db.commit()
    return _view(db, actor, offer)


def _counter(db: Session, actor: Actor, offer: Offer, counter: Counter | None) -> None:
    if counter is None or (counter.entry_id is None) == (counter.meal is None):
        raise Invalid("counter_meal_required")
    sender = next(m for m in day_service.others(db, actor) if m.id == offer.from_user_id)
    if counter.entry_id is not None:
        entry, _ = _offerable(db, actor, counter.entry_id, sender.id)
        if (entry.day, entry.slot) != (offer.day, offer.slot):
            raise Invalid("counter_other_slot")
    else:
        assert counter.meal is not None
        meal = replace(counter.meal, day=offer.day, slot=Slot(offer.slot))
        entry = day_service.plan_meal(db, actor, meal)
    _close(db, actor, offer, OfferState.COUNTERED, action="countered")
    _create(db, actor, entry, sender, share=DEFAULT_SHARE, counter_of=offer)


def expire_overdue(db: Session) -> int:
    """Job: write down pending offers whose day is over. Readers already see them as expired."""
    expired = 0
    horizon = clock.now().date() + timedelta(days=1)
    pending = db.scalars(
        select(Offer).where(
            Offer.state == OfferState.PENDING.value,
            Offer.day < horizon,
        )
    )
    for offer in pending:
        receiver = db.get_one(User, offer.to_user_id)
        if rules.is_overdue(offer.day, today=today_for(receiver)):
            _close(db, None, offer, OfferState.EXPIRED, action="expired")
            expired += 1
    db.commit()
    return expired
