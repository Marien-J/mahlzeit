from typing import ClassVar

import pytest

from mahlzeit.domain.nutrition import (
    NUTRIENTS,
    Nutrients,
    Part,
    intake,
    per_cooked_gram,
    per_serving,
    total,
)

OATS = Nutrients(
    kcal=372, protein=13.5, carbs=58.7, sugar=0.7, fat=7.0, sat_fat=1.3, fibre=10.0, salt=0.02
)
MILK = Nutrients(
    kcal=64, protein=3.3, carbs=4.8, sugar=4.8, fat=3.5, sat_fat=2.3, fibre=0, salt=0.1
)


class TestScaling:
    def test_per_100_to_amount(self) -> None:
        n = OATS.scaled(50)
        assert n.kcal == pytest.approx(186)
        assert n.protein == pytest.approx(6.75)

    def test_missing_values_stay_missing(self) -> None:
        assert OATS.scaled(50).alcohol is None

    def test_energy_is_never_recomputed_from_macros(self) -> None:
        odd = Nutrients(kcal=10, protein=50, carbs=50, fat=50)
        assert odd.scaled(100).kcal == 10


class TestTotals:
    def test_sums_known_values(self) -> None:
        t = total([OATS.scaled(50), MILK.scaled(200)])
        assert t.values.kcal == pytest.approx(186 + 128)
        assert t.values.protein == pytest.approx(6.75 + 6.6)

    def test_reports_which_nutrients_are_incomplete(self) -> None:
        t = total([OATS.scaled(50), Nutrients(kcal=100)])
        assert "protein" in t.incomplete
        assert "kcal" not in t.incomplete
        assert t.values.protein == pytest.approx(6.75)  # roughly right beats exact

    def test_empty_total_is_zero_and_complete(self) -> None:
        t = total([])
        assert t.values.kcal == 0
        assert t.incomplete == frozenset()

    def test_nutrient_names(self) -> None:
        assert NUTRIENTS == (
            "kcal",
            "protein",
            "carbs",
            "sugar",
            "fat",
            "sat_fat",
            "fibre",
            "salt",
            "alcohol",
        )


class TestRecipes:
    def test_per_serving(self) -> None:
        dish = total([OATS.scaled(100), MILK.scaled(400)])
        assert per_serving(dish.values, servings=2).kcal == pytest.approx((372 + 256) / 2)

    def test_per_cooked_gram_then_portion(self) -> None:
        dish = total([OATS.scaled(100), MILK.scaled(400)])
        per100 = per_cooked_gram(dish.values, cooked_yield_g=500)
        assert per100.scaled(250).kcal == pytest.approx((372 + 256) / 2)

    @pytest.mark.parametrize("servings", [0, -1])
    def test_rejects_non_positive_servings(self, servings: float) -> None:
        with pytest.raises(ValueError):
            per_serving(OATS, servings=servings)


class TestIntake:
    PARTS: ClassVar[list[Part]] = [
        Part(key="oats", nutrients=OATS.scaled(100)),
        Part(key="milk", nutrients=MILK.scaled(400)),
    ]

    def test_whole_dish_for_one_person(self) -> None:
        assert intake(self.PARTS, share=1).values.kcal == pytest.approx(628)

    def test_half_and_half(self) -> None:
        assert intake(self.PARTS, share=0.5).values.kcal == pytest.approx(314)

    def test_exact_amount_overrides_share_for_one_component(self) -> None:
        # Shares by feel, but the weigher put exactly 60 g of oats (of 100 g) on their plate.
        got = intake(self.PARTS, share=0.5, exact_fraction={"oats": 0.6})
        assert got.values.kcal == pytest.approx(372 * 0.6 + 256 * 0.5)

    @pytest.mark.parametrize("share", [0, -0.1, 1.01])
    def test_share_bounds(self, share: float) -> None:
        with pytest.raises(ValueError):
            intake(self.PARTS, share=share)
