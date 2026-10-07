from datetime import date

import pytest

from mahlzeit.domain import stock
from mahlzeit.domain.errors import Invalid
from mahlzeit.domain.stock import Movement, Reason, Source, Status


class TestQuantityToAmount:
    """'Bought' turns the list's free-text quantities into amounts in the item's unit."""

    @pytest.mark.parametrize(
        ("text", "amount"),
        [
            ("500 g", 500),
            ("500g", 500),
            ("0,5 kg", 500),
            ("1.5 kg", 1500),
            ("250 ml", 250),  # a gram item bought by volume: roughly one gram per millilitre
            ("1 l", 1000),
        ],
    )
    def test_weights_and_volumes(self, text: str, amount: float) -> None:
        assert stock.amount_from_quantity(text, base_unit="g", package_size=None) == amount

    @pytest.mark.parametrize(
        ("text", "amount"),
        [
            ("2", 1000),
            ("2x", 1000),
            ("2 Stk", 1000),
            ("2 Pck", 1000),
            ("3 Dosen", 1500),
            (None, 500),
        ],
    )
    def test_pieces_and_packages_use_the_package_size(
        self, text: str | None, amount: float
    ) -> None:
        assert stock.amount_from_quantity(text, base_unit="g", package_size=500) == amount

    def test_pieces_without_a_package_size_use_the_first_serving(self) -> None:
        assert stock.amount_from_quantity("6", base_unit="g", package_size=None, serving=55) == 330

    def test_unknown_is_unknown(self) -> None:
        assert stock.amount_from_quantity("2", base_unit="g", package_size=None) is None
        assert stock.amount_from_quantity("eine Handvoll", base_unit="g", package_size=500) is None
        assert stock.amount_from_quantity(None, base_unit="g", package_size=None) is None

    def test_litres_for_a_millilitre_item(self) -> None:
        assert stock.amount_from_quantity("1,5 l", base_unit="ml", package_size=None) == 1500


class TestLevels:
    def test_the_level_is_the_sum_and_never_shown_below_zero(self) -> None:
        assert stock.level([500, -200, -100]) == 200
        assert stock.shown(-30) == 0
        assert stock.shown(120) == 120

    def test_a_shortfall_fills_what_was_missing(self) -> None:
        assert stock.shortfall(want=150, level_without=100) == 50
        assert stock.shortfall(want=80, level_without=100) == 0
        assert stock.shortfall(want=50, level_without=-10) == 60  # lands on zero, not below
        assert stock.shortfall(want=0, level_without=-10) == 0

    def test_a_correction_moves_the_level_to_what_is_there(self) -> None:
        assert stock.correction(level_now=300, counted=120) == -180
        assert stock.correction(level_now=-20, counted=0) == 20
        with pytest.raises(Invalid, match="stock_amount_invalid"):
            stock.correction(level_now=0, counted=-5)

    def test_waste_cannot_exceed_what_is_there(self) -> None:
        assert stock.waste(level_now=300, amount=100) == -100
        assert stock.waste(level_now=50, amount=100) == -50
        with pytest.raises(Invalid, match="stock_amount_invalid"):
            stock.waste(level_now=50, amount=0)

    def test_status_items_flip_through_ok_low_out(self) -> None:
        assert stock.next_status(Status.OK) is Status.LOW
        assert stock.next_status(Status.LOW) is Status.OUT
        assert stock.next_status(Status.OUT) is Status.OK
        assert stock.next_status(None) is Status.LOW


class TestStepper:
    def test_a_package_a_serving_or_a_hundred(self) -> None:
        assert stock.step(package_size=500, serving=None) == 500
        assert stock.step(package_size=None, serving=55) == 55
        assert stock.step(package_size=None, serving=None) == 100


class TestConsumption:
    def test_the_whole_dish_once_by_item(self) -> None:
        dish = [("rice", 200.0), ("chicken", 300.0), ("rice", 50.0), (None, None)]
        assert stock.dish_use(dish) == {"rice": 250, "chicken": 300}

    def test_nothing_when_not_eaten_or_eaten_out(self) -> None:
        dish = [("rice", 200.0)]
        assert stock.consumption(dish, eaten=False, eaten_out=False) == {}
        assert stock.consumption(dish, eaten=True, eaten_out=True) == {}
        assert stock.consumption(dish, eaten=True, eaten_out=False) == {"rice": 200}


MON, TUE = date(2026, 10, 5), date(2026, 10, 6)


def changes(result: list[stock.Change]) -> set[tuple[str, date, Source, float]]:
    return {(str(c.item), c.day, c.source, round(c.amount, 6)) for c in result}


class TestEntrySync:
    """An eaten meal's movements follow the meal: what it takes out, on its day, and the
    shortfall it caused, which goes again when the meal does."""

    def test_eating_takes_out_what_is_there_and_fills_the_rest_quietly(self) -> None:
        result = stock.sync_entry(
            booked={},
            shortfalls={},
            wanted={"rice": 300.0, "milk": 200.0},
            day=MON,
            levels={"rice": 500.0, "milk": 50.0},
        )
        assert changes(result) == {
            ("rice", MON, Source.ENTRY, -300),
            ("milk", MON, Source.ENTRY, -200),
            ("milk", MON, Source.SHORTFALL, 150),
        }

    def test_nothing_changes_when_nothing_changed(self) -> None:
        result = stock.sync_entry(
            booked={("rice", MON): -300.0},
            shortfalls={},
            wanted={"rice": 300.0},
            day=MON,
            levels={"rice": 200.0},
        )
        assert result == []

    def test_a_larger_portion_takes_the_difference(self) -> None:
        result = stock.sync_entry(
            booked={("rice", MON): -300.0},
            shortfalls={},
            wanted={"rice": 400.0},
            day=MON,
            levels={"rice": 50.0},
        )
        assert changes(result) == {
            ("rice", MON, Source.ENTRY, -100),
            ("rice", MON, Source.SHORTFALL, 50),
        }

    def test_undoing_a_meal_gives_back_what_it_took_but_not_its_shortfall(self) -> None:
        # 50 g were there, 200 g eaten: 150 g were filled in. Undone, the 50 g are back.
        result = stock.sync_entry(
            booked={("milk", MON): -200.0},
            shortfalls={("milk", MON): 150.0},
            wanted={},
            day=MON,
            levels={"milk": 0.0},
        )
        assert changes(result) == {
            ("milk", MON, Source.ENTRY, 200),
            ("milk", MON, Source.SHORTFALL, -150),
        }

    def test_a_smaller_portion_gives_back_the_shortfall_first(self) -> None:
        result = stock.sync_entry(
            booked={("milk", MON): -200.0},
            shortfalls={("milk", MON): 150.0},
            wanted={"milk": 120.0},
            day=MON,
            levels={"milk": 0.0},
        )
        assert changes(result) == {
            ("milk", MON, Source.ENTRY, 80),
            ("milk", MON, Source.SHORTFALL, -80),
        }

    def test_a_meal_moved_to_another_day_moves_its_movements(self) -> None:
        result = stock.sync_entry(
            booked={("rice", MON): -300.0},
            shortfalls={},
            wanted={"rice": 300.0},
            day=TUE,
            levels={"rice": 200.0},
        )
        assert changes(result) == {
            ("rice", MON, Source.ENTRY, 300),
            ("rice", TUE, Source.ENTRY, -300),
        }

    def test_a_food_swapped_for_another(self) -> None:
        result = stock.sync_entry(
            booked={("rice", MON): -300.0},
            shortfalls={},
            wanted={"pasta": 250.0},
            day=MON,
            levels={"rice": 0.0, "pasta": 1000.0},
        )
        assert changes(result) == {
            ("rice", MON, Source.ENTRY, 300),
            ("pasta", MON, Source.ENTRY, -250),
        }


class TestPurchaseDay:
    def test_today_or_up_to_a_year_back(self) -> None:
        today = date(2026, 10, 7)
        stock.check_purchase_day(today, today=today)
        stock.check_purchase_day(date(2025, 10, 7), today=today)
        for day in (date(2026, 10, 8), date(2025, 10, 6)):
            with pytest.raises(Invalid) as err:
                stock.check_purchase_day(day, today=today)
            assert err.value.code == "purchase_day_invalid"


class TestSuggestions:
    def test_planned_meals_need_what_is_not_in_stock(self) -> None:
        needs = {"rice": 400.0, "chicken": 300.0, "oats": 100.0}
        levels = {"rice": 500.0, "chicken": 100.0}
        assert stock.missing(needs, levels) == {"chicken": 200, "oats": 100}

    def test_usual_purchases_need_some_history(self) -> None:
        assert not stock.is_usual(purchases=2)
        assert stock.is_usual(purchases=3)


def mv(item: str, reason: Reason, amount: float, source: Source = Source.MANUAL) -> Movement:
    return Movement(item=item, reason=reason, source=source, amount=amount, day=date(2026, 10, 6))


class TestReport:
    def test_purchased_logged_wasted_and_corrected_per_item(self) -> None:
        rows = stock.report(
            [
                mv("rice", Reason.PURCHASE, 1000, Source.PURCHASE),
                mv("rice", Reason.CONSUMPTION, -250, Source.ENTRY),
                mv("rice", Reason.CONSUMPTION, -150, Source.ENTRY),
                mv("rice", Reason.CONSUMPTION, 50, Source.ENTRY),  # an entry made smaller
                mv("rice", Reason.WASTE, -100),
                mv("rice", Reason.CORRECTION, -80, Source.PANTRY),
                mv("milk", Reason.CONSUMPTION, -200, Source.ENTRY),
                mv("milk", Reason.CORRECTION, 200, Source.SHORTFALL),
            ]
        )
        assert rows["rice"] == stock.ItemReport(
            purchased=1000, logged=350, wasted=100, corrected=-80, shortfall=0
        )
        assert rows["milk"] == stock.ItemReport(
            purchased=0, logged=200, wasted=0, corrected=0, shortfall=200
        )
