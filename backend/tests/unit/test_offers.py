from datetime import date

import pytest

from mahlzeit.domain import offers
from mahlzeit.domain.errors import Conflict, Forbidden, Invalid
from mahlzeit.domain.nutrition import Nutrients
from mahlzeit.domain.offers import Action, OfferState, PlannedPart
from mahlzeit.domain.targets import Targets

TODAY = date(2026, 10, 6)


class TestTransitions:
    @pytest.mark.parametrize(
        ("action", "expected"),
        [
            (Action.ACCEPT, OfferState.ACCEPTED),
            (Action.DECLINE, OfferState.DECLINED),
            (Action.COUNTER, OfferState.COUNTERED),
        ],
    )
    def test_the_receiver_answers_a_pending_offer(
        self, action: Action, expected: OfferState
    ) -> None:
        assert offers.next_state(OfferState.PENDING, action, is_sender=False) == expected

    def test_the_sender_withdraws_a_pending_offer(self) -> None:
        state = offers.next_state(OfferState.PENDING, Action.WITHDRAW, is_sender=True)
        assert state == OfferState.WITHDRAWN

    def test_time_expires_it(self) -> None:
        assert offers.next_state(OfferState.PENDING, Action.EXPIRE) == OfferState.EXPIRED

    @pytest.mark.parametrize("action", [Action.ACCEPT, Action.DECLINE, Action.COUNTER])
    def test_the_sender_cannot_answer_their_own_offer(self, action: Action) -> None:
        with pytest.raises(Forbidden, match="offer_not_yours"):
            offers.next_state(OfferState.PENDING, action, is_sender=True)

    def test_the_receiver_cannot_withdraw(self) -> None:
        with pytest.raises(Forbidden, match="offer_not_yours"):
            offers.next_state(OfferState.PENDING, Action.WITHDRAW, is_sender=False)

    @pytest.mark.parametrize(
        "state",
        [
            OfferState.ACCEPTED,
            OfferState.DECLINED,
            OfferState.COUNTERED,
            OfferState.WITHDRAWN,
            OfferState.EXPIRED,
        ],
    )
    @pytest.mark.parametrize("action", list(Action))
    def test_only_a_pending_offer_can_change(self, state: OfferState, action: Action) -> None:
        with pytest.raises(Conflict, match="offer_not_pending"):
            offers.next_state(state, action, is_sender=action is Action.WITHDRAW)


class TestExpiry:
    def test_an_offer_lasts_until_the_day_ends(self) -> None:
        assert not offers.is_overdue(TODAY, today=TODAY)
        assert not offers.is_overdue(date(2026, 10, 7), today=TODAY)
        assert offers.is_overdue(date(2026, 10, 5), today=TODAY)

    def test_a_pending_offer_for_a_past_day_reads_as_expired(self) -> None:
        past = date(2026, 10, 5)
        assert offers.effective_state(OfferState.PENDING, past, today=TODAY) == OfferState.EXPIRED
        assert offers.effective_state(OfferState.PENDING, TODAY, today=TODAY) == OfferState.PENDING

    def test_an_answered_offer_keeps_its_state(self) -> None:
        past = date(2026, 10, 5)
        assert offers.effective_state(OfferState.ACCEPTED, past, today=TODAY) == OfferState.ACCEPTED


class TestWhoIsOffered:
    def test_not_to_oneself(self) -> None:
        with pytest.raises(Invalid, match="offer_to_self"):
            offers.check_receiver("me", "me")
        offers.check_receiver("me", "you")


class TestReplacedByAccept:
    def mine(self, key: str, slot: str, state: str = "planned") -> PlannedPart:
        return PlannedPart(key=key, slot=slot, state=state)

    def test_the_receivers_planned_meal_in_that_slot_is_replaced(self) -> None:
        parts = [self.mine("a", "dinner"), self.mine("b", "lunch")]
        assert offers.replaced_by_accept("dinner", parts) == ["a"]

    def test_logged_and_skipped_entries_are_never_replaced(self) -> None:
        parts = [self.mine("a", "dinner", "logged"), self.mine("b", "dinner", "skipped")]
        assert offers.replaced_by_accept("dinner", parts) == []

    def test_snacks_replace_nothing_because_there_can_be_several(self) -> None:
        assert offers.replaced_by_accept("snack", [self.mine("a", "snack")]) == []


class TestEffectOnTheReceiversDay:
    goal = Targets(kcal=2500, protein=180, carbs=None, fat=70)

    def test_no_targets_no_effect(self) -> None:
        after = offers.projection_after_accept(
            None, replaced=Nutrients(kcal=0), incoming=Nutrients(kcal=500)
        )
        assert after is None

    def test_the_share_comes_off_what_is_left(self) -> None:
        before = Targets(kcal=900, protein=60, carbs=None, fat=20)
        after = offers.projection_after_accept(
            before,
            replaced=Nutrients(),
            incoming=Nutrients(kcal=400, protein=35, carbs=40, fat=12),
        )
        assert after == Targets(kcal=500, protein=25, carbs=None, fat=8)

    def test_a_replaced_plan_is_given_back(self) -> None:
        before = Targets(kcal=900, protein=60, carbs=None, fat=20)
        after = offers.projection_after_accept(
            before,
            replaced=Nutrients(kcal=700, protein=40, fat=30),
            incoming=Nutrients(kcal=400, protein=35, fat=12),
        )
        assert after == Targets(kcal=1200, protein=65, carbs=None, fat=38)

    def test_unknown_values_count_as_zero(self) -> None:
        before = Targets(kcal=900, protein=None, carbs=None, fat=None)
        after = offers.projection_after_accept(
            before, replaced=Nutrients(), incoming=Nutrients(kcal=None, protein=30)
        )
        assert after == Targets(kcal=900, protein=None, carbs=None, fat=None)
