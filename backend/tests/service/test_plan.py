"""Planning, joint meals with shares and exact amounts, and dragging entries into order."""

from datetime import date, time, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from mahlzeit.domain.day import EntryState, Slot
from mahlzeit.domain.errors import Forbidden, Invalid, NotFound
from mahlzeit.domain.targets import DayType, Targets
from mahlzeit.models import ChangeRecord
from mahlzeit.services import day, targets
from mahlzeit.services.day import ComponentInput, EntryInput, EntryPatch
from tests import factories

TODAY = date(2026, 10, 6)
TOMORROW = TODAY + timedelta(days=1)
OATS, CHICKEN, RICE = "C133000", "V416100", "C352000"


def plan(db: Session, member: factories.Member, on: date, slot: Slot = Slot.DINNER, **kw):
    return day.plan_meal(db, member.actor, EntryInput(day=on, slot=slot, **kw))


def quick(name: str = "Bowl", kcal: float = 800, **macros: float) -> ComponentInput:
    return ComponentInput(quick_name=name, kcal=kcal, **macros)


def column(db: Session, member: factories.Member, on: date = TODAY):
    return next(p for p in day.get_day(db, member.actor, on).people if p.user.id == member.user.id)


class TestPlanning:
    def test_a_plan_for_today_is_planned_not_eaten(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        entry = plan(db, jonas, TODAY, components=[quick()])
        part = day.participant_of(entry, jonas.user.id)
        assert part is not None and part.state == EntryState.PLANNED
        assert entry.at == time(19, 0)
        mine = column(db, jonas)
        assert mine.logged.values.kcal == 0 and mine.planned.values.kcal == 800

    def test_the_projection_shows_the_day_if_everything_planned_is_eaten(
        self, db: Session, clock
    ) -> None:
        jonas, _ = factories.household(db)
        targets.set_targets(db, jonas.actor, targets=Targets(kcal=2500), day_types=[DayType.REST])
        plan(db, jonas, TODAY, components=[quick(kcal=900)])
        mine = column(db, jonas)
        assert mine.remaining and mine.remaining.kcal == 2500
        assert mine.projection and mine.projection.kcal == 1600

    def test_a_plan_from_a_recipe_scales_it_to_the_portions(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        chicken, rice = (factories.generic(db, jonas.actor, c) for c in (CHICKEN, RICE))
        chili = factories.recipe(db, jonas.actor, "Chili", (chicken, 400), (rice, 200), servings=4)
        entry = plan(db, jonas, TOMORROW, recipe_id=chili.id, portions=2)
        assert entry.name == "Chili" and entry.recipe_id == chili.id and entry.recipe_portions == 2
        assert [c.amount for c in entry.components] == [200, 100]

    def test_a_plan_can_be_just_a_name(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        entry = plan(db, jonas, TOMORROW, name="Pizza from the oven")
        assert [c.quick_name for c in entry.components] == ["Pizza from the oven"]
        tomorrow = column(db, jonas, TOMORROW)
        assert "kcal" in tomorrow.planned.incomplete  # unknown, not zero

    def test_eating_it_needs_no_numbers_either(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        entry = plan(db, jonas, TODAY, name="Pizza")
        eaten = day.set_state(db, jonas.actor, entry.id, EntryState.LOGGED)
        part = day.participant_of(eaten, jonas.user.id)
        assert part is not None and part.state == EntryState.LOGGED

    def test_logging_a_food_still_needs_kcal(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        with pytest.raises(Invalid, match="quick_add_invalid"):
            day.log_food(
                db,
                jonas.actor,
                EntryInput(day=TODAY, slot=Slot.LUNCH, components=[ComponentInput(quick_name="x")]),
            )

    def test_plans_are_for_today_up_to_30_days_ahead(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        with pytest.raises(Invalid, match="plan_in_past"):
            plan(db, jonas, TODAY - timedelta(days=1), components=[quick()])
        plan(db, jonas, TODAY + timedelta(days=30), components=[quick()])
        with pytest.raises(Invalid, match="date_too_far_ahead"):
            plan(db, jonas, TODAY + timedelta(days=31), components=[quick()])

    def test_an_empty_plan_is_refused(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        with pytest.raises(Invalid, match="entry_empty"):
            plan(db, jonas, TOMORROW)

    def test_a_portion_by_cooked_weight(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        chicken = factories.generic(db, jonas.actor, CHICKEN)
        chili = factories.recipe(
            db, jonas.actor, "Chili", (chicken, 800), servings=4, cooked_yield_g=1200
        )
        e = day.log_food(
            db,
            jonas.actor,
            EntryInput(day=TODAY, slot=Slot.DINNER, recipe_id=chili.id, cooked_grams=450),
        )
        assert e.recipe_portions == 1.5 and e.components[0].amount == pytest.approx(300)

    def test_a_cooked_weight_needs_the_recipes_cooked_yield(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        chicken = factories.generic(db, jonas.actor, CHICKEN)
        chili = factories.recipe(db, jonas.actor, "Chili", (chicken, 800))
        with pytest.raises(Invalid, match="cooked_yield_missing"):
            day.log_food(
                db,
                jonas.actor,
                EntryInput(day=TODAY, slot=Slot.DINNER, recipe_id=chili.id, cooked_grams=300),
            )

    def test_moving_a_planned_meal_to_today_keeps_it_planned(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        entry = plan(db, jonas, TOMORROW, components=[quick()])
        moved = day.update_entry(db, jonas.actor, entry.id, EntryPatch(day=TODAY))
        part = day.participant_of(moved, jonas.user.id)
        assert part is not None and part.state == EntryState.PLANNED

    def test_a_logged_meal_moved_to_the_future_becomes_a_plan(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        entry = day.log_food(
            db, jonas.actor, EntryInput(day=TODAY, slot=Slot.LUNCH, components=[quick()])
        )
        moved = day.update_entry(db, jonas.actor, entry.id, EntryPatch(day=TOMORROW))
        part = day.participant_of(moved, jonas.user.id)
        assert part is not None and part.state == EntryState.PLANNED and part.logged_at is None


class TestPlanOverview:
    def test_every_day_of_the_range_with_both_peoples_entries(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        plan(db, jonas, TODAY, components=[quick("A")])
        plan(db, sam, TOMORROW, components=[quick("B")])
        result = day.get_plan(db, jonas.actor, TODAY, 7)
        assert [d.day for d in result.days] == [TODAY + timedelta(days=i) for i in range(7)]
        assert [len(d.entries) for d in result.days] == [1, 1, 0, 0, 0, 0, 0]
        assert {m.id for m in result.members} == {jonas.user.id, sam.user.id}

    def test_the_range_is_limited(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        for days in (0, 32):
            with pytest.raises(Invalid, match="range_invalid"):
                day.get_plan(db, jonas.actor, TODAY, days)

    def test_another_households_plans_are_not_in_it(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        stranger, _ = factories.household(db)
        plan(db, stranger, TODAY, components=[quick()])
        assert all(not d.entries for d in day.get_plan(db, jonas.actor, TODAY, 3).days)


class TestJointMeals:
    def test_a_joint_meal_is_in_both_columns_half_and_half(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        entry = plan(db, jonas, TODAY, components=[quick(kcal=1000, protein=80)], joint=True)
        assert {p.user_id for p in entry.participants} == {jonas.user.id, sam.user.id}
        assert [p.share for p in entry.participants] == [0.5, 0.5]
        for member in (jonas, sam):
            assert column(db, member).planned.values.kcal == 500

    def test_it_needs_someone_to_share_with(self, db: Session, clock) -> None:
        (loner,) = factories.household(db, "Loner")
        with pytest.raises(Invalid, match="no_partner"):
            plan(db, loner, TODAY, components=[quick()], joint=True)

    def test_eaten_by_one_is_eaten_by_both(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        entry = plan(db, jonas, TODAY, components=[quick(kcal=1000)], joint=True)
        day.set_state(db, sam.actor, entry.id, EntryState.LOGGED)
        for member in (jonas, sam):
            mine = column(db, member)
            assert mine.logged.values.kcal == 500 and mine.planned.values.kcal == 0

    def test_a_skipped_part_stays_skipped(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        entry = plan(db, jonas, TODAY, components=[quick(kcal=1000)], joint=True)
        day.set_state(db, sam.actor, entry.id, EntryState.SKIPPED)
        day.set_state(db, jonas.actor, entry.id, EntryState.LOGGED)
        part = day.participant_of(day.get_entry(db, jonas.actor, entry.id), sam.user.id)
        assert part is not None and part.state == EntryState.SKIPPED

    def test_logging_for_both_logs_both(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        day.log_food(
            db,
            jonas.actor,
            EntryInput(day=TODAY, slot=Slot.LUNCH, components=[quick(kcal=600)], joint=True),
        )
        assert column(db, sam).logged.values.kcal == 300

    def test_each_person_can_remove_their_own_part(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        entry = plan(db, jonas, TODAY, components=[quick(kcal=1000)], joint=True)
        day.delete_entry(db, sam.actor, entry.id)
        left = day.get_entry(db, jonas.actor, entry.id)
        assert [p.user_id for p in left.participants] == [jonas.user.id]
        assert left.participants[0].share == 1.0  # the whole dish is theirs now
        assert column(db, sam).entries == []
        day.delete_entry(db, jonas.actor, entry.id)
        with pytest.raises(NotFound):
            day.get_entry(db, jonas.actor, entry.id)


class TestShares:
    def test_my_share_sets_my_partners_planned_share_to_the_rest(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        entry = plan(db, jonas, TODAY, components=[quick(kcal=1000)], joint=True)
        day.set_share(db, jonas.actor, entry.id, 0.7)
        assert column(db, jonas).planned.values.kcal == pytest.approx(700)
        assert column(db, sam).planned.values.kcal == pytest.approx(300)

    def test_an_eaten_part_is_not_changed_behind_its_owner(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        entry = plan(db, jonas, TODAY, components=[quick(kcal=1000)], joint=True)
        day.set_state(db, sam.actor, entry.id, EntryState.LOGGED)
        day.set_state(db, jonas.actor, entry.id, EntryState.PLANNED)  # not eaten after all
        day.set_share(db, jonas.actor, entry.id, 0.8)
        assert column(db, sam).logged.values.kcal == pytest.approx(500)

    def test_bounds(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        entry = plan(db, jonas, TODAY, components=[quick()], joint=True)
        for bad in (0, 0.01, 0.99, 1.5):
            with pytest.raises(Invalid, match="share_invalid"):
                day.set_share(db, jonas.actor, entry.id, bad)

    def test_only_someone_on_the_meal_can_set_a_share(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        entry = plan(db, jonas, TODAY, components=[quick()])
        with pytest.raises(Forbidden, match="entry_not_yours"):
            day.set_share(db, sam.actor, entry.id, 0.5)

    def test_another_household_cannot_see_the_meal(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        stranger, _ = factories.household(db)
        entry = plan(db, jonas, TODAY, components=[quick()], joint=True)
        for attempt in (
            lambda: day.set_share(db, stranger.actor, entry.id, 0.5),
            lambda: day.set_exact_amounts(db, stranger.actor, entry.id, {}),
            lambda: day.move_entry(db, stranger.actor, entry.id, before_id=None),
        ):
            with pytest.raises(NotFound):
                attempt()


class TestExactAmounts:
    def joint_dish(self, db: Session, jonas: factories.Member):
        chicken, rice = (factories.generic(db, jonas.actor, c) for c in (CHICKEN, RICE))
        entry = plan(
            db,
            jonas,
            TODAY,
            components=[
                ComponentInput(item_id=chicken.id, amount=400),
                ComponentInput(item_id=rice.id, amount=200),
            ],
            joint=True,
        )
        return chicken, rice, entry

    def test_a_weighed_amount_replaces_the_share_for_that_component(
        self, db: Session, clock
    ) -> None:
        jonas, sam = factories.household(db)
        chicken, rice, entry = self.joint_dish(db, jonas)
        chicken_part = next(c for c in entry.components if c.item_id == chicken.id)
        day.set_exact_amounts(db, sam.actor, entry.id, {chicken_part.id: 300})
        expected = chicken.kcal * 3 + rice.kcal * 2 * 0.5
        assert column(db, sam).planned.values.kcal == pytest.approx(expected)
        # Jonas still goes by his share: he did not weigh.
        assert column(db, jonas).planned.values.kcal == pytest.approx(
            chicken.kcal * 4 * 0.5 + rice.kcal * 2 * 0.5
        )

    def test_clearing_it_goes_back_to_the_share(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        chicken, rice, entry = self.joint_dish(db, jonas)
        part = entry.components[0]
        day.set_exact_amounts(db, sam.actor, entry.id, {part.id: 300})
        day.set_exact_amounts(db, sam.actor, entry.id, {part.id: None})
        assert column(db, sam).planned.values.kcal == pytest.approx(
            chicken.kcal * 4 * 0.5 + rice.kcal * 2 * 0.5
        )

    def test_it_survives_changing_the_time_of_the_meal(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        chicken, rice, entry = self.joint_dish(db, jonas)
        day.set_exact_amounts(db, sam.actor, entry.id, {entry.components[0].id: 300})
        same = [ComponentInput(item_id=c.item_id, amount=c.amount) for c in entry.components]
        day.update_entry(db, jonas.actor, entry.id, EntryPatch(at=time(18, 0), components=same))
        expected = chicken.kcal * 3 + rice.kcal * 2 * 0.5
        assert column(db, sam).planned.values.kcal == pytest.approx(expected)

    def test_a_quick_add_cannot_be_weighed(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        entry = plan(db, jonas, TODAY, components=[quick()], joint=True)
        with pytest.raises(Invalid, match="exact_amount_invalid"):
            day.set_exact_amounts(db, jonas.actor, entry.id, {entry.components[0].id: 100})

    def test_a_component_of_another_meal_is_refused(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        chicken = factories.generic(db, jonas.actor, CHICKEN)
        a = plan(db, jonas, TODAY, components=[ComponentInput(item_id=chicken.id, amount=100)])
        b = plan(
            db,
            jonas,
            TODAY,
            Slot.LUNCH,
            components=[ComponentInput(item_id=chicken.id, amount=100)],
        )
        with pytest.raises(Invalid, match="exact_amount_invalid"):
            day.set_exact_amounts(db, jonas.actor, a.id, {b.components[0].id: 50})


class TestDragging:
    def three_meals(self, db: Session, jonas: factories.Member):
        return [
            day.log_food(
                db,
                jonas.actor,
                EntryInput(day=TODAY, slot=slot, name=slot.value, components=[quick(slot.value)]),
            )
            for slot in (Slot.BREAKFAST, Slot.LUNCH, Slot.DINNER)
        ]

    def test_dragging_dinner_above_lunch_gives_it_a_time_in_between(
        self, db: Session, clock
    ) -> None:
        jonas, _ = factories.household(db)
        _, lunch, dinner = self.three_meals(db, jonas)
        changed = day.move_entry(db, jonas.actor, dinner.id, before_id=lunch.id)
        assert [(e.id, e.at) for e in changed] == [(dinner.id, time(10, 15))]
        assert [e.name for e in column(db, jonas).entries] == ["breakfast", "dinner", "lunch"]

    def test_dragging_to_the_end(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        breakfast, *_ = self.three_meals(db, jonas)
        day.move_entry(db, jonas.actor, breakfast.id, before_id=None)
        assert [e.name for e in column(db, jonas).entries] == ["lunch", "dinner", "breakfast"]

    def test_the_move_is_recorded(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        _, lunch, dinner = self.three_meals(db, jonas)
        day.move_entry(db, jonas.actor, dinner.id, before_id=lunch.id)
        record = db.scalars(
            select(ChangeRecord).where(
                ChangeRecord.action == "moved", ChangeRecord.entity_id == dinner.id
            )
        ).one()
        assert record.before == {"at": "19:00"} and record.after == {"at": "10:15"}

    def test_only_the_actors_own_day_counts(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        _, _, dinner = self.three_meals(db, jonas)
        theirs = day.log_food(
            db, sam.actor, EntryInput(day=TODAY, slot=Slot.LUNCH, components=[quick("sam")])
        )
        with pytest.raises(Forbidden):
            day.move_entry(db, sam.actor, dinner.id, before_id=None)
        with pytest.raises(Invalid, match="order_invalid"):
            day.move_entry(db, jonas.actor, dinner.id, before_id=theirs.id)
