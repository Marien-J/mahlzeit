import pytest

from mahlzeit.domain import recipes
from mahlzeit.domain.errors import Invalid
from mahlzeit.domain.recipes import RecipeKind


class TestFields:
    def test_a_recipe_has_a_name_and_a_sensible_number_of_servings(self) -> None:
        assert recipes.check_name("  Chili ") == "Chili"
        assert recipes.check_servings(RecipeKind.RECIPE, 4) == 4
        assert recipes.check_servings(RecipeKind.RECIPE, 0.5) == 0.5

    def test_a_name_is_required(self) -> None:
        with pytest.raises(Invalid, match="recipe_name_required"):
            recipes.check_name("  ")

    @pytest.mark.parametrize("servings", [0, -1, 101])
    def test_servings_bounds(self, servings: float) -> None:
        with pytest.raises(Invalid, match="servings_invalid"):
            recipes.check_servings(RecipeKind.RECIPE, servings)

    def test_a_saved_meal_is_one_serving(self) -> None:
        assert recipes.check_servings(RecipeKind.SAVED_MEAL, 1) == 1
        with pytest.raises(Invalid, match="servings_invalid"):
            recipes.check_servings(RecipeKind.SAVED_MEAL, 2)

    def test_cooked_yield_is_optional_and_positive(self) -> None:
        assert recipes.check_cooked_yield(None) is None
        assert recipes.check_cooked_yield(1200) == 1200
        for bad in (0, -5, 200_000):
            with pytest.raises(Invalid, match="cooked_yield_invalid"):
                recipes.check_cooked_yield(bad)

    def test_notes_are_trimmed_and_may_be_empty(self) -> None:
        assert recipes.check_notes("  slow  ") == "slow"
        assert recipes.check_notes("   ") is None
        assert recipes.check_notes(None) is None
        assert len(recipes.check_notes("x" * 5000) or "") == recipes.MAX_NOTES


class TestPortions:
    def test_a_cooked_weight_is_a_share_of_the_whole_dish(self) -> None:
        # A dish of 4 servings that weighs 1200 g cooked: 300 g is one serving.
        assert recipes.portions_from_cooked(300, cooked_yield_g=1200, servings=4) == 1
        assert recipes.portions_from_cooked(450, cooked_yield_g=1200, servings=4) == 1.5

    def test_it_needs_the_cooked_yield(self) -> None:
        with pytest.raises(Invalid, match="cooked_yield_missing"):
            recipes.portions_from_cooked(300, cooked_yield_g=None, servings=4)

    def test_it_needs_a_weight(self) -> None:
        with pytest.raises(Invalid, match="amount_invalid"):
            recipes.portions_from_cooked(0, cooked_yield_g=1200, servings=4)

    def test_portions_are_bounded(self) -> None:
        assert recipes.check_portions(0.5) == 0.5
        for bad in (0, -1, 21):
            with pytest.raises(Invalid, match="portions_invalid"):
                recipes.check_portions(bad)


class TestScaling:
    def test_amounts_follow_the_portions_asked_for(self) -> None:
        # A recipe for 4: two portions need half of everything.
        assert recipes.scale([("rice", 400), ("beans", 200)], servings=4, portions=2) == [
            ("rice", 200),
            ("beans", 100),
        ]

    def test_the_same_item_twice_is_added_up(self) -> None:
        merged = recipes.combine([("oil", 10), ("rice", 100), ("oil", 15)])
        assert merged == [("oil", 25), ("rice", 100)]


class TestQuantityText:
    @pytest.mark.parametrize(
        ("amount", "unit", "language", "text"),
        [
            (250, "g", "de", "250 g"),
            (249.6, "g", "en", "250 g"),
            (12.6, "g", "en", "13 g"),
            (2.5, "g", "en", "2.5 g"),
            (2.5, "g", "de", "2,5 g"),
            (2.5, "g", "nl", "2,5 g"),
            (1000, "g", "de", "1 kg"),
            (1250, "g", "de", "1,25 kg"),
            (1250, "g", "en", "1.25 kg"),
            (500, "ml", "de", "500 ml"),
            (1500, "ml", "en", "1.5 l"),
        ],
    )
    def test_readable_on_a_shopping_list(
        self, amount: float, unit: str, language: str, text: str
    ) -> None:
        assert recipes.quantity_text(amount, unit, language) == text
