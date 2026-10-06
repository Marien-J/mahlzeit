from datetime import date, time

import pytest

from mahlzeit.domain.day import (
    MAX_PLAN_DAYS,
    Slot,
    check_amount,
    check_entry_date,
    default_time,
    entry_state_for,
)
from mahlzeit.domain.errors import Invalid

TODAY = date(2026, 10, 6)


class TestSlots:
    @pytest.mark.parametrize(
        ("slot", "expected"),
        [(Slot.BREAKFAST, time(8, 0)), (Slot.LUNCH, time(12, 30)), (Slot.DINNER, time(19, 0))],
    )
    def test_anchor_defaults(self, slot: Slot, expected: time) -> None:
        assert default_time(slot, now=time(15, 7)) == expected

    def test_snack_defaults_to_now(self) -> None:
        assert default_time(Slot.SNACK, now=time(15, 7, 42)) == time(15, 7)


class TestDates:
    def test_past_and_today_and_up_to_30_days_ahead(self) -> None:
        check_entry_date(date(2020, 1, 1), today=TODAY)
        check_entry_date(TODAY, today=TODAY)
        check_entry_date(date(2026, 11, 5), today=TODAY)
        assert MAX_PLAN_DAYS == 30

    def test_too_far_ahead(self) -> None:
        with pytest.raises(Invalid) as err:
            check_entry_date(date(2026, 11, 6), today=TODAY)
        assert err.value.code == "date_too_far_ahead"

    def test_future_entries_are_planned_by_default(self) -> None:
        assert entry_state_for(date(2026, 10, 7), today=TODAY) == "planned"
        assert entry_state_for(TODAY, today=TODAY) == "logged"
        assert entry_state_for(date(2026, 10, 5), today=TODAY) == "logged"


class TestAmounts:
    def test_grams(self) -> None:
        assert check_amount(150) == 150

    @pytest.mark.parametrize("amount", [0, -5, 100_001])
    def test_bounds(self, amount: float) -> None:
        with pytest.raises(Invalid) as err:
            check_amount(amount)
        assert err.value.code == "amount_invalid"
