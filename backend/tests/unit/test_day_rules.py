from datetime import date, time
from typing import ClassVar

import pytest

from mahlzeit.domain.day import (
    MAX_PLAN_DAYS,
    Slot,
    check_amount,
    check_entry_date,
    check_plan_date,
    default_time,
    entry_state_for,
    retime,
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


class TestPlanDates:
    def test_today_and_up_to_30_days_ahead(self) -> None:
        check_plan_date(TODAY, today=TODAY)
        check_plan_date(date(2026, 11, 5), today=TODAY)

    def test_a_plan_is_for_today_or_later(self) -> None:
        with pytest.raises(Invalid, match="plan_in_past"):
            check_plan_date(date(2026, 10, 5), today=TODAY)

    def test_not_beyond_the_horizon(self) -> None:
        with pytest.raises(Invalid, match="date_too_far_ahead"):
            check_plan_date(date(2026, 11, 6), today=TODAY)


def t(hhmm: str) -> time:
    return time.fromisoformat(hhmm)


class TestRetime:
    """Dragging an entry changes its time so that the order on screen is the order of the day."""

    day: ClassVar[list[tuple[str, time]]] = [
        ("breakfast", t("08:00")),
        ("lunch", t("12:30")),
        ("dinner", t("19:00")),
    ]

    def test_between_two_entries_takes_the_middle(self) -> None:
        assert retime(self.day, "dinner", before="lunch") == {"dinner": t("10:15")}

    def test_to_the_top_goes_half_an_hour_ahead_of_the_first(self) -> None:
        assert retime(self.day, "dinner", before="breakfast") == {"dinner": t("07:30")}

    def test_to_the_bottom_goes_half_an_hour_after_the_last(self) -> None:
        assert retime(self.day, "breakfast", before=None) == {"breakfast": t("19:30")}

    def test_an_entry_already_in_place_keeps_its_time(self) -> None:
        assert retime(self.day, "lunch", before="dinner") == {}
        assert retime(self.day, "dinner", before=None) == {}
        assert retime(self.day, "breakfast", before="lunch") == {}

    def test_equal_times_move_to_the_front(self) -> None:
        tied = [("a", t("12:30")), ("b", t("12:30"))]
        assert retime(tied, "b", before="a") == {"b": t("12:00")}

    def test_no_minute_between_pushes_the_later_entries_on(self) -> None:
        crowded = [("a", t("12:30")), ("b", t("12:31")), ("c", t("20:00"))]
        assert retime(crowded, "c", before="b") == {"c": t("12:31"), "b": t("12:32")}

    def test_the_bottom_is_capped_at_the_end_of_the_day(self) -> None:
        late = [("a", t("08:00")), ("b", t("23:50"))]
        assert retime(late, "a", before=None) == {"a": t("23:59")}

    def test_no_room_at_the_end_of_the_day(self) -> None:
        full = [("a", t("08:00")), ("b", t("23:58")), ("c", t("23:59"))]
        with pytest.raises(Invalid, match="reorder_no_room"):
            retime(full, "a", before="c")

    def test_the_entry_it_goes_before_must_be_on_the_day(self) -> None:
        with pytest.raises(Invalid, match="order_invalid"):
            retime(self.day, "dinner", before="elsewhere")
        with pytest.raises(Invalid, match="order_invalid"):
            retime(self.day, "elsewhere", before="lunch")


def test_dropping_an_entry_on_itself_is_no_move() -> None:
    order = [("a", t("08:00")), ("b", t("12:30"))]
    assert retime(order, "b", before="b") == {}
