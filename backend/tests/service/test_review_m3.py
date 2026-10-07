"""Regressions found by reviewing M3: each test names what went wrong."""

from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from mahlzeit.domain.day import EntryState, Slot
from mahlzeit.domain.errors import Invalid
from mahlzeit.services import day, recipes
from mahlzeit.services.day import ComponentInput, EntryInput, EntryPatch
from tests import factories

TODAY = date(2026, 10, 6)
CHICKEN, RICE = "V416100", "C352000"


def column(db: Session, member: factories.Member, on: date = TODAY):
    return next(p for p in day.get_day(db, member.actor, on).people if p.user.id == member.user.id)


def joint_dinner(db: Session, member: factories.Member, on: date = TODAY, **kw):
    chicken = factories.generic(db, member.actor, CHICKEN)
    return day.log_food(
        db,
        member.actor,
        EntryInput(
            day=on,
            slot=Slot.DINNER,
            components=[
                ComponentInput(item_id=chicken.id, amount=400),
                ComponentInput(quick_name="Sauce", kcal=200, protein=4),
            ],
            joint=True,
            **kw,
        ),
    )


class TestCopyingASharedMeal:
    def test_copying_my_part_of_a_shared_meal_copies_my_part_not_the_dish(
        self, db: Session, clock
    ) -> None:
        jonas, _ = factories.household(db)
        yesterday = TODAY - timedelta(days=1)
        source = joint_dinner(db, jonas, on=yesterday)
        day.set_share(db, jonas.actor, source.id, 0.7)
        mine_before = column(db, jonas, yesterday).logged.values.kcal
        copy = day.copy_entry(db, jonas.actor, source.id, day=TODAY)
        assert len(copy.participants) == 1
        assert column(db, jonas).logged.values.kcal == pytest.approx(mine_before)

    def test_a_weighed_amount_is_what_gets_copied(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        yesterday = TODAY - timedelta(days=1)
        source = joint_dinner(db, jonas, on=yesterday)
        chicken = source.components[0]
        day.set_exact_amounts(db, jonas.actor, source.id, {chicken.id: 300})
        copy = day.copy_entry(db, jonas.actor, source.id, day=TODAY)
        assert copy.components[0].amount == pytest.approx(300)
        assert copy.components[1].quick_kcal == pytest.approx(100)  # the sauce by share

    def test_copying_the_partners_shared_meal_takes_their_part(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        yesterday = TODAY - timedelta(days=1)
        source = joint_dinner(db, jonas, on=yesterday)
        day.delete_entry(db, sam.actor, source.id)  # Sam was not there; Jonas ate it alone
        day.set_share(db, jonas.actor, source.id, 1.0)
        copy = day.copy_entry(db, sam.actor, source.id, day=TODAY)
        assert copy.components[0].amount == pytest.approx(400)

    def test_copying_a_day_with_a_shared_meal(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        yesterday = TODAY - timedelta(days=1)
        joint_dinner(db, jonas, on=yesterday)
        before = column(db, jonas, yesterday).logged.values.kcal
        day.copy_day(db, jonas.actor, source_day=yesterday, day=TODAY)
        assert column(db, jonas).logged.values.kcal == pytest.approx(before)


class TestEatenAndNameOnlyMeals:
    def test_a_plan_for_a_later_day_cannot_be_eaten_yet(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        plan = day.plan_meal(
            db,
            jonas.actor,
            EntryInput(day=TODAY + timedelta(days=1), slot=Slot.DINNER, name="Pizza", joint=True),
        )
        with pytest.raises(Invalid, match="eaten_in_future"):
            day.set_state(db, jonas.actor, plan.id, EntryState.LOGGED)

    def test_an_eaten_name_only_meal_can_still_be_edited(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        plan = day.plan_meal(db, jonas.actor, EntryInput(day=TODAY, slot=Slot.DINNER, name="Pizza"))
        day.set_state(db, jonas.actor, plan.id, EntryState.LOGGED)
        same = [ComponentInput(quick_name="Pizza")]
        moved = day.update_entry(db, jonas.actor, plan.id, EntryPatch(at=None, components=same))
        assert moved.components[0].quick_kcal is None
        filled = day.update_entry(
            db,
            jonas.actor,
            plan.id,
            EntryPatch(components=[ComponentInput(quick_name="Pizza", kcal=900)]),
        )
        assert filled.components[0].quick_kcal == 900
        assert "kcal" not in column(db, jonas).logged.incomplete

    def test_copying_a_name_only_plan_to_a_past_day_keeps_it(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        plan = day.plan_meal(db, jonas.actor, EntryInput(day=TODAY, slot=Slot.DINNER, name="Pizza"))
        copy = day.copy_entry(db, jonas.actor, plan.id, day=TODAY - timedelta(days=2))
        assert copy.components[0].quick_name == "Pizza" and copy.components[0].quick_kcal is None


class TestSmallerOnes:
    def test_dropping_an_entry_on_itself_changes_nothing(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        e = day.log_food(
            db,
            jonas.actor,
            EntryInput(
                day=TODAY, slot=Slot.LUNCH, components=[ComponentInput(quick_name="x", kcal=1)]
            ),
        )
        assert day.move_entry(db, jonas.actor, e.id, before_id=e.id) == []

    def test_a_big_recipe_goes_on_the_list_whole(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        rice = factories.generic(db, jonas.actor, RICE)
        cookies = factories.recipe(db, jonas.actor, "Cookies", (rice, 500), servings=24)
        added = recipes.add_to_list(db, jonas.actor, cookies.id)
        assert [r.quantity for r in added.added] == ["500 g"]

    def test_the_plan_range_cannot_run_past_the_calendar(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        with pytest.raises(Invalid, match="range_invalid"):
            day.get_plan(db, jonas.actor, date(9999, 12, 31), 7)

    def test_a_weighed_amount_stays_with_its_component_when_another_of_the_same_item_goes(
        self, db: Session, clock
    ) -> None:
        jonas, _ = factories.household(db)
        chicken = factories.generic(db, jonas.actor, CHICKEN)
        entry = day.log_food(
            db,
            jonas.actor,
            EntryInput(
                day=TODAY,
                slot=Slot.DINNER,
                components=[
                    ComponentInput(item_id=chicken.id, amount=200),
                    ComponentInput(item_id=chicken.id, amount=100),
                ],
                joint=True,
            ),
        )
        second = entry.components[1]
        day.set_exact_amounts(db, jonas.actor, entry.id, {second.id: 80})
        kept = day.update_entry(
            db,
            jonas.actor,
            entry.id,
            EntryPatch(components=[ComponentInput(item_id=chicken.id, amount=100)]),
        )
        mine = day.participant_of(kept, jonas.user.id)
        assert mine is not None
        assert [x.amount for x in mine.exact_amounts] == [80]
        assert kept.components[0].id == second.id
