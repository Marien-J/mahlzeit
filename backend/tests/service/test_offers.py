"""Offers between members: send, accept, decline, counter, withdraw, expire."""

from datetime import date, time, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from mahlzeit.domain.day import EntryState, Slot
from mahlzeit.domain.errors import Conflict, Forbidden, Invalid, NotFound
from mahlzeit.domain.offers import Action, OfferState
from mahlzeit.domain.targets import DayType, Targets
from mahlzeit.jobs import worker
from mahlzeit.jobs.registry import Deps
from mahlzeit.models import ChangeRecord, Job, Offer
from mahlzeit.services import day, offers, profiles, push, snapshot, targets
from mahlzeit.services.day import ComponentInput, EntryInput, EntryPatch
from mahlzeit.services.offers import Counter
from tests import factories

TODAY = date(2026, 10, 6)
TOMORROW = TODAY + timedelta(days=1)


def meal(
    db: Session,
    member: factories.Member,
    name: str,
    *,
    on: date = TODAY,
    slot: Slot = Slot.DINNER,
    kcal: float = 1000,
    state_logged: bool = False,
):
    entry = day.plan_meal(
        db,
        member.actor,
        EntryInput(
            day=on,
            slot=slot,
            name=name,
            components=[ComponentInput(quick_name=name, kcal=kcal)],
        ),
    )
    if state_logged:
        entry = day.set_state(db, member.actor, entry.id, EntryState.LOGGED)
    return entry


def state_of(entry, member: factories.Member) -> str | None:
    part = day.participant_of(entry, member.user.id)
    return part.state if part else None


def push_jobs(db: Session) -> list[Job]:
    return list(db.scalars(select(Job).where(Job.kind == "push.deliver").order_by(Job.created_at)))


class TestSending:
    def test_a_pending_offer_with_the_meal_and_a_default_share(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        pasta = meal(db, jonas, "Pasta")
        offer = offers.send(db, jonas.actor, entry_id=pasta.id, to_user_id=sam.user.id)
        assert offer.state is OfferState.PENDING
        assert (offer.offer.day, offer.offer.slot, offer.offer.share) == (TODAY, "dinner", 0.5)
        assert offer.entry is not None and offer.entry.id == pasta.id
        assert offer.effect is None  # the sender does not see the receiver's day

    def test_the_receiver_gets_a_push_message_with_the_meal(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        offers.send(db, jonas.actor, entry_id=meal(db, jonas, "Pasta").id, to_user_id=sam.user.id)
        (job,) = push_jobs(db)
        assert job.payload["user_id"] == str(sam.user.id) and job.payload["message"] == "offer"
        assert job.payload["params"] == {"name": jonas.user.display_name, "meal": "Pasta"}

    def test_no_push_when_the_receiver_switched_it_off(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        profiles.update_profile(db, sam.actor, push_offers=False)
        offers.send(db, jonas.actor, entry_id=meal(db, jonas, "Pasta").id, to_user_id=sam.user.id)
        assert push_jobs(db) == []
        assert offers.pending_count(db, sam.actor) == 1  # the badge is still there

    def test_only_a_planned_meal_of_today_or_later_can_be_offered(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        eaten = meal(db, jonas, "Eaten", state_logged=True)
        with pytest.raises(Invalid, match="offer_meal_not_planned"):
            offers.send(db, jonas.actor, entry_id=eaten.id, to_user_id=sam.user.id)

    def test_not_to_oneself_or_a_stranger(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        stranger, _ = factories.household(db)
        pasta = meal(db, jonas, "Pasta")
        with pytest.raises(Invalid, match="offer_to_self"):
            offers.send(db, jonas.actor, entry_id=pasta.id, to_user_id=jonas.user.id)
        with pytest.raises(NotFound):
            offers.send(db, jonas.actor, entry_id=pasta.id, to_user_id=stranger.user.id)

    def test_not_to_someone_already_on_the_meal(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        joint = day.plan_meal(
            db,
            jonas.actor,
            EntryInput(
                day=TODAY,
                slot=Slot.DINNER,
                components=[ComponentInput(quick_name="x", kcal=1)],
                joint=True,
            ),
        )
        with pytest.raises(Conflict, match="offer_already_joint"):
            offers.send(db, jonas.actor, entry_id=joint.id, to_user_id=sam.user.id)

    def test_only_the_owner_of_the_plan_can_offer_it(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        pasta = meal(db, jonas, "Pasta")
        with pytest.raises(Forbidden, match="entry_not_yours"):
            offers.send(db, sam.actor, entry_id=pasta.id, to_user_id=jonas.user.id)

    def test_a_new_offer_for_the_slot_replaces_the_pending_one(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        first = offers.send(
            db, jonas.actor, entry_id=meal(db, jonas, "Pasta").id, to_user_id=sam.user.id
        )
        # A different plan of Jonas's in the same slot (a snack-free slot may hold two plans).
        second_meal = meal(db, jonas, "Curry")
        second = offers.send(db, jonas.actor, entry_id=second_meal.id, to_user_id=sam.user.id)
        assert offers.get(db, jonas.actor, first.offer.id).state is OfferState.WITHDRAWN
        assert second.state is OfferState.PENDING
        assert [v.offer.id for v in offers.list_offers(db, sam.actor)] == [second.offer.id]

    def test_offers_can_be_sent_again_after_one_was_accepted(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        pasta = meal(db, jonas, "Pasta")
        first = offers.send(db, jonas.actor, entry_id=pasta.id, to_user_id=sam.user.id)
        offers.respond(db, sam.actor, first.offer.id, Action.ACCEPT)
        curry = meal(db, jonas, "Curry")
        again = offers.send(db, jonas.actor, entry_id=curry.id, to_user_id=sam.user.id)
        assert again.state is OfferState.PENDING


class TestAccepting:
    def test_it_makes_the_meal_joint_half_and_half(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        pasta = meal(db, jonas, "Pasta")
        offer = offers.send(db, jonas.actor, entry_id=pasta.id, to_user_id=sam.user.id)
        done = offers.respond(db, sam.actor, offer.offer.id, Action.ACCEPT)
        assert done.state is OfferState.ACCEPTED
        entry = day.get_entry(db, jonas.actor, pasta.id)
        assert {p.user_id: (p.state, p.share) for p in entry.participants} == {
            jonas.user.id: ("planned", 0.5),
            sam.user.id: ("planned", 0.5),
        }

    def test_the_proposed_share_is_the_receivers(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        pasta = meal(db, jonas, "Pasta")
        offer = offers.send(db, jonas.actor, entry_id=pasta.id, to_user_id=sam.user.id, share=0.3)
        offers.respond(db, sam.actor, offer.offer.id, Action.ACCEPT)
        entry = day.get_entry(db, jonas.actor, pasta.id)
        assert {p.user_id: p.share for p in entry.participants} == {
            jonas.user.id: pytest.approx(0.7),
            sam.user.id: 0.3,
        }

    def test_it_replaces_the_receivers_own_plan_for_the_slot(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        pasta, salad = meal(db, jonas, "Pasta"), meal(db, sam, "Salad")
        lunch = meal(db, sam, "Lunch", slot=Slot.LUNCH)
        offer = offers.send(db, jonas.actor, entry_id=pasta.id, to_user_id=sam.user.id)
        offers.respond(db, sam.actor, offer.offer.id, Action.ACCEPT)
        with pytest.raises(NotFound):
            day.get_entry(db, sam.actor, salad.id)  # nobody else was on it, so it is gone
        assert day.get_entry(db, sam.actor, lunch.id)  # another slot is untouched

    def test_a_logged_entry_in_the_slot_is_never_replaced(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        pasta = meal(db, jonas, "Pasta")
        eaten = meal(db, sam, "Eaten", state_logged=True)
        offer = offers.send(db, jonas.actor, entry_id=pasta.id, to_user_id=sam.user.id)
        offers.respond(db, sam.actor, offer.offer.id, Action.ACCEPT)
        assert state_of(day.get_entry(db, sam.actor, eaten.id), sam) == "logged"

    def test_a_snack_replaces_nothing(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        mine, theirs = (meal(db, m, "Nuts", slot=Slot.SNACK) for m in (jonas, sam))
        offer = offers.send(db, jonas.actor, entry_id=mine.id, to_user_id=sam.user.id)
        offers.respond(db, sam.actor, offer.offer.id, Action.ACCEPT)
        assert day.get_entry(db, sam.actor, theirs.id)

    def test_a_plan_shared_with_the_sender_keeps_the_others_part(self, db: Session, clock) -> None:
        jonas, sam, kim = factories.household(db, "Jonas", "Sam", "Kim")
        shared = day.plan_meal(
            db,
            sam.actor,
            EntryInput(
                day=TODAY,
                slot=Slot.DINNER,
                components=[ComponentInput(quick_name="x", kcal=900)],
                joint=True,
            ),
        )
        pasta = meal(db, jonas, "Pasta")
        # Sam is on a joint plan with Jonas and Kim; accepting Jonas's offer leaves that plan.
        with pytest.raises(Conflict, match="offer_already_joint"):
            offers.send(db, sam.actor, entry_id=shared.id, to_user_id=jonas.user.id)
        offer = offers.send(db, jonas.actor, entry_id=pasta.id, to_user_id=sam.user.id)
        offers.respond(db, sam.actor, offer.offer.id, Action.ACCEPT)
        left = day.get_entry(db, kim.actor, shared.id)
        assert {p.user_id for p in left.participants} == {jonas.user.id, kim.user.id}
        assert sum(p.share for p in left.participants) == pytest.approx(1.0)

    def test_pending_offers_of_the_replaced_plan_end(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        pasta, salad = meal(db, jonas, "Pasta"), meal(db, sam, "Salad")
        mine = offers.send(db, jonas.actor, entry_id=pasta.id, to_user_id=sam.user.id)
        theirs = offers.send(db, sam.actor, entry_id=salad.id, to_user_id=jonas.user.id)
        offers.respond(db, sam.actor, mine.offer.id, Action.ACCEPT)
        assert offers.get(db, sam.actor, theirs.offer.id).state is OfferState.WITHDRAWN

    def test_it_shows_the_effect_on_the_receivers_day_first(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        targets.set_targets(db, sam.actor, targets=Targets(kcal=2500), day_types=[DayType.REST])
        pasta = meal(db, jonas, "Pasta", kcal=1000)
        meal(db, sam, "Salad", kcal=400)
        offer = offers.send(db, jonas.actor, entry_id=pasta.id, to_user_id=sam.user.id)
        effect = offers.get(db, sam.actor, offer.offer.id).effect
        assert effect is not None
        assert effect.incoming.values.kcal == 500
        assert effect.projection_before == Targets(kcal=2100, protein=None, carbs=None, fat=None)
        # Accepting gives back the salad's 400 and takes half the pasta.
        assert effect.projection_after is not None and effect.projection_after.kcal == 2000

    def test_without_targets_there_is_no_projection(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        offer = offers.send(
            db, jonas.actor, entry_id=meal(db, jonas, "Pasta").id, to_user_id=sam.user.id
        )
        effect = offers.get(db, sam.actor, offer.offer.id).effect
        assert effect is not None and effect.targets is None and effect.projection_after is None

    def test_only_the_receiver_can_answer(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        offer = offers.send(
            db, jonas.actor, entry_id=meal(db, jonas, "Pasta").id, to_user_id=sam.user.id
        )
        for action in (Action.ACCEPT, Action.DECLINE, Action.COUNTER):
            with pytest.raises(Forbidden, match="offer_not_yours"):
                offers.respond(db, jonas.actor, offer.offer.id, action)

    def test_an_answered_offer_cannot_be_answered_again(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        offer = offers.send(
            db, jonas.actor, entry_id=meal(db, jonas, "Pasta").id, to_user_id=sam.user.id
        )
        offers.respond(db, sam.actor, offer.offer.id, Action.DECLINE)
        with pytest.raises(Conflict, match="offer_not_pending"):
            offers.respond(db, sam.actor, offer.offer.id, Action.ACCEPT)

    def test_decline_leaves_the_senders_plan_alone(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        pasta = meal(db, jonas, "Pasta")
        offer = offers.send(db, jonas.actor, entry_id=pasta.id, to_user_id=sam.user.id)
        done = offers.respond(db, sam.actor, offer.offer.id, Action.DECLINE)
        assert done.state is OfferState.DECLINED
        entry = day.get_entry(db, jonas.actor, pasta.id)
        assert [p.user_id for p in entry.participants] == [jonas.user.id]

    def test_the_meal_must_still_be_there_and_planned(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        pasta = meal(db, jonas, "Pasta")
        offer = offers.send(db, jonas.actor, entry_id=pasta.id, to_user_id=sam.user.id)
        day.set_state(db, jonas.actor, pasta.id, EntryState.LOGGED)  # eaten in the meantime
        assert offers.get(db, sam.actor, offer.offer.id).state is OfferState.WITHDRAWN
        with pytest.raises(Conflict, match="offer_not_pending"):
            offers.respond(db, sam.actor, offer.offer.id, Action.ACCEPT)


class TestCountering:
    def test_with_a_plan_of_ones_own_for_the_slot(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        pasta, curry = meal(db, jonas, "Pasta"), meal(db, sam, "Curry")
        offer = offers.send(db, jonas.actor, entry_id=pasta.id, to_user_id=sam.user.id)
        done = offers.respond(
            db, sam.actor, offer.offer.id, Action.COUNTER, counter=Counter(entry_id=curry.id)
        )
        assert done.state is OfferState.COUNTERED
        (back,) = offers.list_offers(db, jonas.actor)
        assert back.offer.counter_of_id == offer.offer.id
        assert (back.sender.id, back.receiver.id) == (sam.user.id, jonas.user.id)
        assert back.entry is not None and back.entry.id == curry.id

    def test_with_a_new_meal(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        offer = offers.send(
            db, jonas.actor, entry_id=meal(db, jonas, "Pasta").id, to_user_id=sam.user.id
        )
        meal_in = EntryInput(
            day=TOMORROW,  # ignored: the counter is for the offer's slot
            slot=Slot.BREAKFAST,
            name="Soup",
            components=[ComponentInput(quick_name="Soup", kcal=500)],
        )
        offers.respond(db, sam.actor, offer.offer.id, Action.COUNTER, counter=Counter(meal=meal_in))
        (back,) = offers.list_offers(db, jonas.actor)
        assert back.entry is not None
        assert (back.entry.day, back.entry.slot, back.entry.name) == (TODAY, "dinner", "Soup")

    def test_the_counter_gets_a_push_message_too(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        offer = offers.send(
            db, jonas.actor, entry_id=meal(db, jonas, "Pasta").id, to_user_id=sam.user.id
        )
        curry = meal(db, sam, "Curry")
        offers.respond(
            db, sam.actor, offer.offer.id, Action.COUNTER, counter=Counter(entry_id=curry.id)
        )
        last = push_jobs(db)[-1]
        assert last.payload["user_id"] == str(jonas.user.id)
        assert last.payload["message"] == "counter"
        assert last.payload["params"] == {"name": sam.user.display_name, "meal": "Curry"}

    def test_accepting_the_counter_replaces_the_senders_plan(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        pasta, curry = meal(db, jonas, "Pasta"), meal(db, sam, "Curry")
        offer = offers.send(db, jonas.actor, entry_id=pasta.id, to_user_id=sam.user.id)
        offers.respond(
            db, sam.actor, offer.offer.id, Action.COUNTER, counter=Counter(entry_id=curry.id)
        )
        (back,) = offers.list_offers(db, jonas.actor)
        offers.respond(db, jonas.actor, back.offer.id, Action.ACCEPT)
        with pytest.raises(NotFound):
            day.get_entry(db, jonas.actor, pasta.id)
        joint = day.get_entry(db, jonas.actor, curry.id)
        assert {p.user_id for p in joint.participants} == {jonas.user.id, sam.user.id}

    def test_it_needs_exactly_one_meal(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        curry = meal(db, sam, "Curry")
        offer = offers.send(
            db, jonas.actor, entry_id=meal(db, jonas, "Pasta").id, to_user_id=sam.user.id
        )
        meal_in = EntryInput(
            day=TODAY, slot=Slot.DINNER, components=[ComponentInput(quick_name="x", kcal=1)]
        )
        for counter in (None, Counter(), Counter(entry_id=curry.id, meal=meal_in)):
            with pytest.raises(Invalid, match="counter_meal_required"):
                offers.respond(db, sam.actor, offer.offer.id, Action.COUNTER, counter=counter)

    def test_the_meal_must_be_for_the_same_slot(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        lunch = meal(db, sam, "Lunch", slot=Slot.LUNCH)
        offer = offers.send(
            db, jonas.actor, entry_id=meal(db, jonas, "Pasta").id, to_user_id=sam.user.id
        )
        with pytest.raises(Invalid, match="counter_other_slot"):
            offers.respond(
                db, sam.actor, offer.offer.id, Action.COUNTER, counter=Counter(entry_id=lunch.id)
            )


class TestWithdrawing:
    def test_the_sender_withdraws_a_pending_offer(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        offer = offers.send(
            db, jonas.actor, entry_id=meal(db, jonas, "Pasta").id, to_user_id=sam.user.id
        )
        assert offers.withdraw(db, jonas.actor, offer.offer.id).state is OfferState.WITHDRAWN
        assert offers.pending_count(db, sam.actor) == 0

    def test_not_the_receiver_and_not_twice(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        offer = offers.send(
            db, jonas.actor, entry_id=meal(db, jonas, "Pasta").id, to_user_id=sam.user.id
        )
        with pytest.raises(Forbidden, match="offer_not_yours"):
            offers.withdraw(db, sam.actor, offer.offer.id)
        offers.withdraw(db, jonas.actor, offer.offer.id)
        with pytest.raises(Conflict, match="offer_not_pending"):
            offers.withdraw(db, jonas.actor, offer.offer.id)

    def test_changing_the_slot_day_or_removing_the_meal_ends_the_offer(
        self, db: Session, clock
    ) -> None:
        jonas, sam = factories.household(db)
        for change in (
            lambda e: day.update_entry(db, jonas.actor, e.id, EntryPatch(slot=Slot.LUNCH)),
            lambda e: day.update_entry(db, jonas.actor, e.id, EntryPatch(day=TOMORROW)),
            lambda e: day.delete_entry(db, jonas.actor, e.id),
        ):
            pasta = meal(db, jonas, "Pasta")
            offer = offers.send(db, jonas.actor, entry_id=pasta.id, to_user_id=sam.user.id)
            change(pasta)
            db.expire_all()
            assert db.get_one(Offer, offer.offer.id).state == "withdrawn"

    def test_changing_the_time_or_the_foods_keeps_it(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        pasta = meal(db, jonas, "Pasta")
        offer = offers.send(db, jonas.actor, entry_id=pasta.id, to_user_id=sam.user.id)
        day.update_entry(
            db, jonas.actor, pasta.id, EntryPatch(at=time(18, 0), name="Pasta al forno")
        )
        seen = offers.get(db, sam.actor, offer.offer.id)
        assert seen.state is OfferState.PENDING
        assert seen.entry is not None and seen.entry.name == "Pasta al forno"


class TestExpiry:
    def test_it_lasts_until_the_day_ends(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        offer = offers.send(
            db, jonas.actor, entry_id=meal(db, jonas, "Pasta").id, to_user_id=sam.user.id
        )
        clock.advance(timedelta(hours=9))  # 23:00 in Amsterdam, still the same day
        assert offers.get(db, sam.actor, offer.offer.id).state is OfferState.PENDING
        clock.advance(timedelta(hours=2))  # 01:00 the next day
        assert offers.get(db, sam.actor, offer.offer.id).state is OfferState.EXPIRED
        assert offers.list_offers(db, sam.actor) == []
        assert offers.pending_count(db, sam.actor) == 0
        (closed,) = offers.list_offers(db, sam.actor, include_closed=True)
        assert closed.state is OfferState.EXPIRED

    def test_an_expired_offer_cannot_be_accepted(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        pasta = meal(db, jonas, "Pasta")
        offer = offers.send(db, jonas.actor, entry_id=pasta.id, to_user_id=sam.user.id)
        clock.advance(timedelta(days=1))
        with pytest.raises(Conflict, match="offer_not_pending"):
            offers.respond(db, sam.actor, offer.offer.id, Action.ACCEPT)
        row = db.get_one(Offer, offer.offer.id)
        assert row.state == "expired"  # written down on the way
        assert [p.user_id for p in day.get_entry(db, jonas.actor, pasta.id).participants] == [
            jonas.user.id
        ]

    def test_the_hourly_job_writes_it_down(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        today_offer = offers.send(
            db, jonas.actor, entry_id=meal(db, jonas, "Pasta").id, to_user_id=sam.user.id
        )
        tomorrow_offer = offers.send(
            db,
            jonas.actor,
            entry_id=meal(db, jonas, "Curry", on=TOMORROW).id,
            to_user_id=sam.user.id,
        )
        assert offers.expire_overdue(db) == 0
        clock.advance(timedelta(days=1))
        assert offers.expire_overdue(db) == 1
        assert db.get_one(Offer, today_offer.offer.id).state == "expired"
        assert db.get_one(Offer, tomorrow_offer.offer.id).state == "pending"
        record = db.scalars(
            select(ChangeRecord).where(
                ChangeRecord.entity == "offer", ChangeRecord.action == "expired"
            )
        ).one()
        assert record.client == "job" and record.user_id is None
        assert offers.expire_overdue(db) == 0


class TestVisibility:
    def test_only_the_two_people_involved_see_an_offer(self, db: Session, clock) -> None:
        jonas, sam, kim = factories.household(db, "Jonas", "Sam", "Kim")
        offer = offers.send(
            db, jonas.actor, entry_id=meal(db, jonas, "Pasta").id, to_user_id=sam.user.id
        )
        assert offers.list_offers(db, kim.actor) == []
        for attempt in (
            lambda: offers.get(db, kim.actor, offer.offer.id),
            lambda: offers.respond(db, kim.actor, offer.offer.id, Action.ACCEPT),
            lambda: offers.withdraw(db, kim.actor, offer.offer.id),
        ):
            with pytest.raises(NotFound):
                attempt()

    def test_another_household_sees_nothing(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        stranger, other = factories.household(db)
        offer = offers.send(
            db, jonas.actor, entry_id=meal(db, jonas, "Pasta").id, to_user_id=sam.user.id
        )
        assert offers.list_offers(db, stranger.actor) == []
        for attempt in (
            lambda: offers.get(db, stranger.actor, offer.offer.id),
            lambda: offers.respond(db, stranger.actor, offer.offer.id, Action.ACCEPT),
            lambda: offers.withdraw(db, stranger.actor, offer.offer.id),
            lambda: offers.send(
                db, stranger.actor, entry_id=meal(db, jonas, "Other").id, to_user_id=other.user.id
            ),
        ):
            with pytest.raises(NotFound):
                attempt()

    def test_every_change_is_recorded_with_its_client(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        offer = offers.send(
            db, jonas.actor, entry_id=meal(db, jonas, "Pasta").id, to_user_id=sam.user.id
        )
        offers.respond(db, sam.actor, offer.offer.id, Action.ACCEPT)
        actions = db.scalars(
            select(ChangeRecord.action)
            .where(ChangeRecord.entity == "offer")
            .order_by(ChangeRecord.id)
        ).all()
        assert list(actions) == ["sent", "accepted"]


class TestAround:
    def test_the_push_message_is_localised_and_names_the_sender_and_the_meal(
        self, db: Session, clock
    ) -> None:
        from tests.service.test_push import FakeSender

        jonas, sam = factories.household(db)
        push.subscribe(
            db, sam.actor, endpoint="https://push.example/abc", p256dh="BPk-key", auth="secret"
        )
        offers.send(db, jonas.actor, entry_id=meal(db, jonas, "Pasta").id, to_user_id=sam.user.id)
        sender = FakeSender()
        (job,) = push_jobs(db)
        push.deliver(db, job.payload, sender)
        ((_, message),) = sender.sent
        assert (
            message["title"] == f"{jonas.user.display_name} offers you a meal"
        )  # Sam reads English
        assert message["body"] == "Pasta"

    def test_the_snapshot_shows_pending_offers(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        offer = offers.send(
            db, jonas.actor, entry_id=meal(db, jonas, "Pasta").id, to_user_id=sam.user.id
        )
        shown = snapshot.household_snapshot(db, sam.actor).offers
        assert [v.offer.id for v in shown] == [offer.offer.id]

    def test_the_worker_expires_old_offers_every_hour(self, db: Session, clock) -> None:
        from mahlzeit.services import queue

        jonas, sam = factories.household(db)
        offer = offers.send(
            db, jonas.actor, entry_id=meal(db, jonas, "Pasta").id, to_user_id=sam.user.id
        )
        db.query(Job).delete()  # the push message is not what this tests
        clock.advance(timedelta(days=1))
        queue.enqueue(db, "offers.expire")
        db.commit()
        assert worker.run_one(db, Deps())
        assert db.get_one(Offer, offer.offer.id).state == "expired"
