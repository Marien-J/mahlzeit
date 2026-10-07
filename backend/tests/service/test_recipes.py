from datetime import date

import pytest
from sqlalchemy.orm import Session

from mahlzeit.domain.day import Slot
from mahlzeit.domain.errors import Invalid, NotFound
from mahlzeit.domain.recipes import RecipeKind
from mahlzeit.services import day, recipes, shopping
from mahlzeit.services.day import EntryInput
from mahlzeit.services.recipes import Ingredient, RecipeInput, RecipePatch
from tests import factories

TODAY = date(2026, 10, 6)
OATS, CHICKEN, RICE, OIL = "C133000", "V416100", "C352000", "Q120000"


def foods(db: Session, member: factories.Member, *codes: str):
    return [factories.generic(db, member.actor, c) for c in codes]


class TestRecipes:
    def test_servings_cooked_yield_staple_and_notes(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        chicken, rice = foods(db, jonas, CHICKEN, RICE)
        chili = recipes.create(
            db,
            jonas.actor,
            RecipeInput(
                name=" Chili ",
                servings=4,
                cooked_yield_g=1200,
                staple=True,
                notes="  Simmer for an hour.  ",
                ingredients=[Ingredient(chicken.id, 400), Ingredient(rice.id, 200)],
            ),
        )
        assert (chili.name, chili.kind, chili.servings) == ("Chili", "recipe", 4)
        assert (
            chili.cooked_yield_g == 1200 and chili.staple and chili.notes == "Simmer for an hour."
        )

    def test_nutrition_is_computed_from_the_ingredients(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        chicken, rice = foods(db, jonas, CHICKEN, RICE)
        chili = factories.recipe(
            db, jonas.actor, "Chili", (chicken, 400), (rice, 200), servings=4, cooked_yield_g=1200
        )
        dish = chicken.kcal * 4 + rice.kcal * 2
        assert recipes.dish_nutrition(chili).values.kcal == pytest.approx(dish)
        assert recipes.nutrition(chili).values.kcal == pytest.approx(dish / 4)
        per_100 = recipes.nutrition_per_100g_cooked(chili)
        assert per_100 is not None and per_100.kcal == pytest.approx(dish / 12)

    def test_without_a_cooked_yield_there_is_no_per_100g(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        (chicken,) = foods(db, jonas, CHICKEN)
        assert (
            recipes.nutrition_per_100g_cooked(
                factories.recipe(db, jonas.actor, "Chicken", (chicken, 200))
            )
            is None
        )

    def test_a_saved_meal_is_one_serving(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        (oats,) = foods(db, jonas, OATS)
        with pytest.raises(Invalid, match="servings_invalid"):
            recipes.create(
                db,
                jonas.actor,
                RecipeInput(
                    name="Oats",
                    kind=RecipeKind.SAVED_MEAL,
                    servings=2,
                    ingredients=[Ingredient(oats.id, 50)],
                ),
            )

    def test_a_recipe_needs_ingredients_and_a_name(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        with pytest.raises(Invalid, match="recipe_empty"):
            recipes.create(db, jonas.actor, RecipeInput(name="Air"))
        (oats,) = foods(db, jonas, OATS)
        with pytest.raises(Invalid, match="recipe_name_required"):
            recipes.create(
                db, jonas.actor, RecipeInput(name=" ", ingredients=[Ingredient(oats.id, 50)])
            )

    def test_update_changes_what_is_sent_and_clears_what_is_null(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        (chicken,) = foods(db, jonas, CHICKEN)
        r = factories.recipe(db, jonas.actor, "Chili", (chicken, 400), cooked_yield_g=900)
        r = recipes.update(db, jonas.actor, r.id, RecipePatch(staple=True, servings=3))
        assert (r.staple, r.servings, r.cooked_yield_g) == (True, 3, 900)
        r = recipes.update(db, jonas.actor, r.id, RecipePatch(cooked_yield_g=None))
        assert r.cooked_yield_g is None and r.staple
        r = recipes.update(db, jonas.actor, r.id, RecipePatch(notes="x"))
        r = recipes.update(db, jonas.actor, r.id, RecipePatch(notes=None))
        assert r.notes is None

    def test_the_list_shows_staples_first(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        (oats,) = foods(db, jonas, OATS)
        factories.recipe(db, jonas.actor, "Aaa", (oats, 50))
        factories.recipe(db, jonas.actor, "Zzz", (oats, 50), staple=True)
        factories.saved_meal(db, jonas.actor, "Mmm", (oats, 50))
        assert [r.name for r in recipes.list_all(db, jonas.actor)] == ["Zzz", "Aaa", "Mmm"]
        only = recipes.list_all(db, jonas.actor, kind=RecipeKind.SAVED_MEAL)
        assert [r.name for r in only] == ["Mmm"]
        assert [r.name for r in recipes.list_all(db, jonas.actor, staples_only=True)] == ["Zzz"]

    def test_deleting_keeps_what_was_eaten(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        (oats,) = foods(db, jonas, OATS)
        r = factories.recipe(db, jonas.actor, "Oats", (oats, 100), servings=1)
        e = day.log_food(
            db, jonas.actor, EntryInput(day=TODAY, slot=Slot.BREAKFAST, recipe_id=r.id)
        )
        recipes.delete(db, jonas.actor, r.id)
        db.expire_all()  # the database sets the link to null
        kept = day.get_entry(db, jonas.actor, e.id)
        assert kept.recipe_id is None and kept.components[0].amount == 100

    def test_another_household_cannot_reach_it(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        stranger, _ = factories.household(db)
        (oats,) = foods(db, jonas, OATS)
        r = factories.recipe(db, jonas.actor, "Oats", (oats, 100))
        assert recipes.list_all(db, stranger.actor) == []
        for attempt in (
            lambda: recipes.get(db, stranger.actor, r.id),
            lambda: recipes.update(db, stranger.actor, r.id, RecipePatch(name="x")),
            lambda: recipes.delete(db, stranger.actor, r.id),
            lambda: recipes.add_to_list(db, stranger.actor, r.id),
        ):
            with pytest.raises(NotFound):
                attempt()

    def test_cannot_use_another_households_item(self, db: Session) -> None:
        from mahlzeit.services import items
        from mahlzeit.services.items import ItemInput

        jonas, _ = factories.household(db)
        stranger, _ = factories.household(db)
        theirs = items.create(db, stranger.actor, ItemInput(names={"de": "Geheim"}))
        with pytest.raises(NotFound):
            recipes.create(
                db, jonas.actor, RecipeInput(name="Spy", ingredients=[Ingredient(theirs.id, 10)])
            )


class TestAddToList:
    def chili(self, db: Session, jonas: factories.Member):
        chicken, rice, oil = foods(db, jonas, CHICKEN, RICE, OIL)
        return (
            factories.recipe(
                db,
                jonas.actor,
                "Chili",
                (chicken, 400),
                (rice, 200),
                (oil, 15),
                (oil, 10),
                servings=4,
            ),
            chicken,
            rice,
            oil,
        )

    def test_puts_the_ingredients_for_the_whole_recipe_on_the_list(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        chili, chicken, rice, oil = self.chili(db, jonas)
        result = recipes.add_to_list(db, jonas.actor, chili.id, language="de")
        by_item = {r.item_id: r for r in result.added}
        assert by_item[chicken.id].quantity == "400 g"
        assert by_item[rice.id].quantity == "200 g"
        assert by_item[oil.id].quantity == "25 g"  # listed twice, added up
        assert {r.origin for r in result.added} == {"recipe"}
        assert result.already_listed == []
        assert len(shopping.open_items(db, jonas.actor)) == 3

    def test_scales_to_the_portions_and_the_language(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        chili, chicken, *_ = self.chili(db, jonas)
        result = recipes.add_to_list(db, jonas.actor, chili.id, portions=10, language="en")
        by_item = {r.item_id: r for r in result.added}
        assert by_item[chicken.id].quantity == "1 kg"

    def test_what_is_on_the_list_already_is_left_alone(self, db: Session) -> None:
        jonas, sam = factories.household(db)
        chili, *_ = self.chili(db, jonas)
        recipes.add_to_list(db, jonas.actor, chili.id)
        again = recipes.add_to_list(db, sam.actor, chili.id)
        assert again.added == [] and len(again.already_listed) == 3
        assert len(shopping.open_items(db, jonas.actor)) == 3

    def test_the_portions_are_bounded(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        chili, *_ = self.chili(db, jonas)
        with pytest.raises(Invalid, match="portions_invalid"):
            recipes.add_to_list(db, jonas.actor, chili.id, portions=0)
