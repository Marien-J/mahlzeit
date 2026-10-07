from datetime import date, time, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mahlzeit.domain.day import EntryState, Slot
from mahlzeit.domain.errors import Forbidden, Invalid, NotFound
from mahlzeit.domain.targets import DayType, Targets
from mahlzeit.models import ChangeRecord, MealEntry
from mahlzeit.services import day, recipes, snapshot, targets
from mahlzeit.services.day import ComponentInput, EntryInput, EntryPatch
from mahlzeit.services.recipes import Ingredient, RecipeInput, RecipePatch
from tests import factories

TODAY = date(2026, 10, 6)
OATS, EGG, CHICKEN, RICE, BROCCOLI, OLIVE_OIL = (
    "C133000",
    "E111100",
    "V416100",
    "C352000",
    "G312100",
    "Q120000",
)


def log(
    db: Session,
    member: factories.Member,
    slot: Slot,
    *components: ComponentInput,
    on: date = TODAY,
    **kw,
):
    return day.log_food(
        db, member.actor, EntryInput(day=on, slot=slot, components=list(components), **kw)
    )


class TestLogging:
    def test_a_full_day_matches_a_hand_calculation(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        oats, egg, chicken, rice = (
            factories.generic(db, jonas.actor, c) for c in (OATS, EGG, CHICKEN, RICE)
        )
        log(
            db,
            jonas,
            Slot.BREAKFAST,
            ComponentInput(item_id=oats.id, amount=80),
            ComponentInput(item_id=egg.id, serving_label="egg", serving_count=2),
        )
        log(
            db,
            jonas,
            Slot.LUNCH,
            ComponentInput(item_id=chicken.id, amount=200),
            ComponentInput(item_id=rice.id, amount=100),
        )
        log(db, jonas, Slot.SNACK, ComponentInput(quick_name="Protein bar", kcal=210, protein=20))
        me = day.get_day(db, jonas.actor, TODAY).people[0]

        # By hand from the BLS values per 100 g:
        kcal = oats.kcal * 0.8 + egg.kcal * 1.1 + chicken.kcal * 2 + rice.kcal * 1 + 210
        protein = oats.protein * 0.8 + egg.protein * 1.1 + chicken.protein * 2 + rice.protein + 20
        assert me.logged.values.kcal == pytest.approx(kcal)
        assert me.logged.values.protein == pytest.approx(protein)
        assert "sugar" in me.logged.incomplete  # the quick-add has no sugar value
        assert [e.slot for e in me.entries] == ["breakfast", "lunch", "snack"]

    def test_default_times(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        clock.set(clock.current.replace(hour=13, minute=17))  # 15:17 in Berlin
        b = log(
            db,
            jonas,
            Slot.BREAKFAST,
            ComponentInput(item_id=factories.generic(db, jonas.actor, OATS).id, amount=50),
        )
        s = log(db, jonas, Slot.SNACK, ComponentInput(quick_name="Apfel", kcal=80))
        assert b.at == time(8, 0)
        assert s.at == time(15, 17)

    def test_future_days_are_planned_and_can_be_eaten(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        tomorrow = TODAY + timedelta(days=1)
        e = log(db, jonas, Slot.DINNER, ComponentInput(quick_name="Pizza", kcal=900), on=tomorrow)
        assert e.participants[0].state == EntryState.PLANNED
        assert day.get_day(db, jonas.actor, tomorrow).people[0].logged.values.kcal == 0
        assert day.get_day(db, jonas.actor, tomorrow).people[0].planned.values.kcal == 900
        day.set_state(db, jonas.actor, e.id, EntryState.LOGGED)
        assert day.get_day(db, jonas.actor, tomorrow).people[0].logged.values.kcal == 900

    def test_not_more_than_30_days_ahead(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        with pytest.raises(Invalid) as err:
            log(
                db,
                jonas,
                Slot.DINNER,
                ComponentInput(quick_name="x", kcal=1),
                on=TODAY + timedelta(days=31),
            )
        assert err.value.code == "date_too_far_ahead"

    def test_past_days_can_be_logged(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        e = log(db, jonas, Slot.DINNER, ComponentInput(quick_name="x", kcal=1), on=date(2026, 1, 1))
        assert e.participants[0].state == EntryState.LOGGED

    @pytest.mark.parametrize(
        "bad",
        [
            ComponentInput(quick_name="", kcal=100),
            ComponentInput(quick_name="x"),
            ComponentInput(quick_name="x", kcal=-1),
            ComponentInput(quick_name="x", kcal=10, protein=-1),
        ],
    )
    def test_quick_add_validation(self, db: Session, clock, bad: ComponentInput) -> None:
        jonas, _ = factories.household(db)
        with pytest.raises(Invalid):
            log(db, jonas, Slot.SNACK, bad)

    def test_item_needs_an_amount_or_known_serving(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        oats = factories.generic(db, jonas.actor, OATS)
        with pytest.raises(Invalid) as err:
            log(db, jonas, Slot.BREAKFAST, ComponentInput(item_id=oats.id))
        assert err.value.code == "amount_required"
        with pytest.raises(Invalid) as err:
            log(db, jonas, Slot.BREAKFAST, ComponentInput(item_id=oats.id, serving_label="egg"))
        assert err.value.code == "serving_unknown"

    def test_empty_entry(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        with pytest.raises(Invalid) as err:
            log(db, jonas, Slot.BREAKFAST)
        assert err.value.code == "entry_empty"

    def test_logging_never_needs_targets_or_complete_data(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        log(db, jonas, Slot.SNACK, ComponentInput(quick_name="Something", kcal=100))
        me = day.get_day(db, jonas.actor, TODAY).people[0]
        assert me.targets is None and me.remaining is None
        assert me.logged.values.kcal == 100


class TestTwoColumns:
    def test_both_people_see_both_columns(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        log(db, jonas, Slot.LUNCH, ComponentInput(quick_name="Bowl", kcal=700))
        log(db, sam, Slot.LUNCH, ComponentInput(quick_name="Soup", kcal=300))
        view = day.get_day(db, sam.actor, TODAY)
        assert [p.user.display_name for p in view.people] == [
            "Partner",
            "Jonas",
        ]  # the viewer first
        assert [p.logged.values.kcal for p in view.people] == [300, 700]

    def test_remaining_and_projection(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        targets.set_targets(
            db,
            jonas.actor,
            targets=Targets(kcal=2000, protein=150),
            day_types=[DayType.TRAINING, DayType.REST],
        )
        log(db, jonas, Slot.LUNCH, ComponentInput(quick_name="Bowl", kcal=700, protein=50))
        tomorrow = TODAY + timedelta(days=1)
        me = day.get_day(db, jonas.actor, TODAY).people[0]
        assert me.remaining == Targets(kcal=1300, protein=100)
        assert me.projection == Targets(kcal=1300, protein=100)
        dinner = log(
            db,
            jonas,
            Slot.DINNER,
            ComponentInput(quick_name="Plan", kcal=800, protein=60),
            on=tomorrow,
        )
        day.update_entry(db, jonas.actor, dinner.id, EntryPatch(day=TODAY))
        day.set_state(db, jonas.actor, dinner.id, EntryState.PLANNED)
        me = day.get_day(db, jonas.actor, TODAY).people[0]
        assert me.remaining == Targets(kcal=1300, protein=100)
        assert me.projection == Targets(kcal=500, protein=40)

    def test_cannot_change_the_partners_entry(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        e = log(db, jonas, Slot.LUNCH, ComponentInput(quick_name="Bowl", kcal=700))
        for attempt in (
            lambda: day.update_entry(db, sam.actor, e.id, EntryPatch(name="mine now")),
            lambda: day.delete_entry(db, sam.actor, e.id),
            lambda: day.set_state(db, sam.actor, e.id, EntryState.SKIPPED),
        ):
            with pytest.raises(Forbidden) as err:
                attempt()
            assert err.value.code == "entry_not_yours"

    def test_another_household_sees_nothing(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        stranger, _ = factories.household(db)
        e = log(db, jonas, Slot.LUNCH, ComponentInput(quick_name="Bowl", kcal=700))
        assert all(p.entries == [] for p in day.get_day(db, stranger.actor, TODAY).people)
        for attempt in (
            lambda: day.get_entry(db, stranger.actor, e.id),
            lambda: day.update_entry(db, stranger.actor, e.id, EntryPatch(name="x")),
            lambda: day.delete_entry(db, stranger.actor, e.id),
            lambda: day.copy_entry(db, stranger.actor, e.id, day=TODAY),
        ):
            with pytest.raises(NotFound):
                attempt()

    def test_cannot_log_another_households_item(self, db: Session, clock) -> None:
        from mahlzeit.services import items
        from mahlzeit.services.items import ItemInput

        jonas, _ = factories.household(db)
        stranger, _ = factories.household(db)
        theirs = items.create(db, stranger.actor, ItemInput(names={"de": "Geheim"}))
        with pytest.raises(NotFound):
            log(db, jonas, Slot.SNACK, ComponentInput(item_id=theirs.id, amount=10))


class TestEditing:
    def test_update_records_before_and_after(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        chicken = factories.generic(db, jonas.actor, CHICKEN)
        e = log(db, jonas, Slot.LUNCH, ComponentInput(item_id=chicken.id, amount=150))
        updated = day.update_entry(
            db,
            jonas.actor,
            e.id,
            EntryPatch(
                at=time(13, 5),
                eaten_out=True,
                components=[ComponentInput(item_id=chicken.id, amount=180)],
            ),
        )
        assert (
            updated.at == time(13, 5) and updated.eaten_out and updated.components[0].amount == 180
        )
        change = db.scalars(
            select(ChangeRecord).where(
                ChangeRecord.entity_id == e.id, ChangeRecord.action == "updated"
            )
        ).one()
        assert change.before["components"][0]["amount"] == 150
        assert change.after["components"][0]["amount"] == 180

    def test_delete(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        e = log(db, jonas, Slot.SNACK, ComponentInput(quick_name="x", kcal=10))
        day.delete_entry(db, jonas.actor, e.id)
        assert db.scalar(select(func.count()).select_from(MealEntry)) == 0


class TestCopy:
    def test_copy_an_entry_to_today(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        old = log(
            db,
            sam,
            Slot.DINNER,
            ComponentInput(quick_name="Curry", kcal=650),
            on=TODAY - timedelta(days=3),
        )
        copy = day.copy_entry(db, jonas.actor, old.id, day=TODAY)
        assert copy.day == TODAY and copy.slot == "dinner" and copy.at == old.at
        assert copy.participants[0].user_id == jonas.user.id

    def test_copy_a_whole_day(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        yesterday = TODAY - timedelta(days=1)
        log(db, jonas, Slot.BREAKFAST, ComponentInput(quick_name="Müsli", kcal=400), on=yesterday)
        log(db, jonas, Slot.LUNCH, ComponentInput(quick_name="Bowl", kcal=700), on=yesterday)
        copies = day.copy_day(db, jonas.actor, source_day=yesterday, day=TODAY)
        assert [c.slot for c in copies] == ["breakfast", "lunch"]
        assert day.get_day(db, jonas.actor, TODAY).people[0].logged.values.kcal == 1100

    def test_nothing_to_copy(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        with pytest.raises(Invalid):
            day.copy_day(db, jonas.actor, source_day=TODAY - timedelta(days=1), day=TODAY)


class TestSavedMeals:
    def test_save_and_log_with_one_tap(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        oats, egg = (
            factories.generic(db, jonas.actor, OATS),
            factories.generic(db, jonas.actor, EGG),
        )
        meal = factories.saved_meal(db, jonas.actor, "Usual breakfast", (oats, 80), (egg, 110))
        expected = oats.kcal * 0.8 + egg.kcal * 1.1
        assert recipes.nutrition(meal).values.kcal == pytest.approx(expected)
        e = day.log_food(
            db, sam.actor, EntryInput(day=TODAY, slot=Slot.BREAKFAST, recipe_id=meal.id)
        )
        assert e.name == "Usual breakfast" and e.recipe_id == meal.id
        assert day.get_day(db, sam.actor, TODAY).people[0].logged.values.kcal == pytest.approx(
            expected
        )

    def test_half_portion(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        oats = factories.generic(db, jonas.actor, OATS)
        meal = factories.saved_meal(db, jonas.actor, "Oats", (oats, 100))
        e = day.log_food(
            db,
            jonas.actor,
            EntryInput(day=TODAY, slot=Slot.BREAKFAST, recipe_id=meal.id, portions=0.5),
        )
        assert e.components[0].amount == 50

    def test_save_from_an_entry_skips_quick_adds(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        e = log(
            db,
            jonas,
            Slot.BREAKFAST,
            ComponentInput(item_id=factories.generic(db, jonas.actor, OATS).id, amount=60),
            ComponentInput(quick_name="Coffee", kcal=5),
            name="Frühstück",
        )
        meal = recipes.create_from_entry(db, jonas.actor, e.id)
        assert meal.name == "Frühstück" and len(meal.ingredients) == 1

    def test_logging_a_saved_meal_keeps_its_amounts_when_the_meal_changes(
        self, db: Session, clock
    ) -> None:
        jonas, _ = factories.household(db)
        oats = factories.generic(db, jonas.actor, OATS)
        meal = factories.saved_meal(db, jonas.actor, "Oats", (oats, 100))
        e = day.log_food(
            db, jonas.actor, EntryInput(day=TODAY, slot=Slot.BREAKFAST, recipe_id=meal.id)
        )
        recipes.update(db, jonas.actor, meal.id, RecipePatch(ingredients=[Ingredient(oats.id, 40)]))
        assert day.get_entry(db, jonas.actor, e.id).components[0].amount == 100

    def test_cross_household(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        stranger, _ = factories.household(db)
        meal = factories.saved_meal(
            db, jonas.actor, "Mine", (factories.generic(db, jonas.actor, OATS), 50)
        )
        assert recipes.list_all(db, stranger.actor) == []
        for attempt in (
            lambda: recipes.get(db, stranger.actor, meal.id),
            lambda: recipes.update(db, stranger.actor, meal.id, RecipePatch(name="x")),
            lambda: recipes.delete(db, stranger.actor, meal.id),
            lambda: day.log_food(
                db, stranger.actor, EntryInput(day=TODAY, slot=Slot.LUNCH, recipe_id=meal.id)
            ),
        ):
            with pytest.raises(NotFound):
                attempt()

    def test_validation(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        with pytest.raises(Invalid):
            recipes.create(db, jonas.actor, RecipeInput(name=" ", ingredients=[]))


class TestSnapshot:
    def test_tonight_and_remaining_for_both(self, db: Session, clock) -> None:
        jonas, sam = factories.household(db)
        targets.set_targets(db, jonas.actor, targets=Targets(kcal=2500), day_types=[DayType.REST])
        log(db, jonas, Slot.LUNCH, ComponentInput(quick_name="Bowl", kcal=700))
        log(db, sam, Slot.DINNER, ComponentInput(quick_name="Lasagne", kcal=800))
        snap = snapshot.household_snapshot(db, jonas.actor)
        assert [p.remaining.kcal if p.remaining else None for p in snap.today.people] == [
            1800,
            None,
        ]
        assert [e.name for e in snap.tonight] == [None]
        assert snap.not_yet_available == ("stock",)
        assert snap.shopping_list == []
