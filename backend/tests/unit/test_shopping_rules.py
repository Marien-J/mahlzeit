from datetime import UTC, datetime, timedelta

import pytest

from mahlzeit.domain import shopping as rules
from mahlzeit.domain.errors import Invalid

T0 = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


class TestParseEntry:
    @pytest.mark.parametrize(
        ("raw", "quantity", "name"),
        [
            ("Milch", None, "Milch"),
            ("  Milch  ", None, "Milch"),
            ("2 Milch", "2", "Milch"),
            ("2x Milch", "2", "Milch"),
            ("2 x Milch", "2", "Milch"),
            ("3 \u00d7 Joghurt", "3", "Joghurt"),
            ("500 g Hackfleisch", "500 g", "Hackfleisch"),
            ("500g Hackfleisch", "500 g", "Hackfleisch"),
            ("1,5 kg Kartoffeln", "1,5 kg", "Kartoffeln"),
            ("1.5 l Milch", "1.5 l", "Milch"),
            ("2 Stk Paprika", "2 Stk", "Paprika"),
            ("Milch 2", "2", "Milch"),
            ("Milch x2", "2", "Milch"),
            ("Eier 10 Stück", "10 Stück", "Eier"),
            # A number that is part of the name stays in it.
            ("7up", None, "7up"),
            ("Milch 1,5 %", None, "Milch 1,5 %"),
            ("2", None, "2"),
        ],
    )
    def test_splits_a_leading_or_trailing_quantity(
        self, raw: str, quantity: str | None, name: str
    ) -> None:
        assert rules.parse_entry(raw) == rules.Entry(quantity=quantity, name=name)

    def test_rejects_empty_text(self) -> None:
        with pytest.raises(Invalid, match="list_text_empty"):
            rules.parse_entry("   ")


class TestChecks:
    def test_text_is_trimmed_and_limited(self) -> None:
        assert rules.check_text("  Brot ") == "Brot"
        assert len(rules.check_text("x" * 300)) == 120
        with pytest.raises(Invalid, match="list_text_empty"):
            rules.check_text(" ")

    def test_quantity_is_optional_and_short(self) -> None:
        assert rules.check_quantity("  ") is None
        assert rules.check_quantity(None) is None
        assert rules.check_quantity(" 2 Pck ") == "2 Pck"
        assert rules.check_quantity("9" * 100) == "9" * 40

    def test_store_names(self) -> None:
        assert rules.check_store_name("  Hofladen ") == "Hofladen"
        with pytest.raises(Invalid, match="store_name_empty"):
            rules.check_store_name("")


class TestMerge:
    def test_newer_field_change_wins_per_field(self) -> None:
        state = rules.FieldState(
            values={"quantity": "1", "checked": False},
            times={"quantity": T0, "checked": T0},
        )
        later = T0 + timedelta(minutes=1)
        result = rules.merge(state, {"checked": True}, at=later, now=later)
        assert result.changed == {"checked"}
        assert result.state.values == {"quantity": "1", "checked": True}
        assert result.state.times["checked"] == later
        assert result.state.times["quantity"] == T0

    def test_older_change_loses_but_other_fields_still_apply(self) -> None:
        # Partner changed the quantity online at T0+5; an offline check from T0+2 arrives later.
        state = rules.FieldState(
            values={"quantity": "3", "checked": False},
            times={"quantity": T0 + timedelta(minutes=5), "checked": T0},
        )
        now = T0 + timedelta(minutes=10)
        result = rules.merge(
            state, {"quantity": "1", "checked": True}, at=T0 + timedelta(minutes=2), now=now
        )
        assert result.changed == {"checked"}
        assert result.state.values == {"quantity": "3", "checked": True}

    def test_replaying_the_same_change_changes_nothing(self) -> None:
        state = rules.FieldState(values={"checked": False}, times={"checked": T0})
        once = rules.merge(state, {"checked": True}, at=T0 + timedelta(seconds=1), now=T0)
        twice = rules.merge(once.state, {"checked": True}, at=T0 + timedelta(seconds=1), now=T0)
        assert twice.changed == set()
        assert twice.state == once.state

    def test_a_clock_in_the_future_counts_as_now(self) -> None:
        state = rules.FieldState(values={"checked": False}, times={"checked": T0})
        result = rules.merge(state, {"checked": True}, at=T0 + timedelta(days=365), now=T0)
        assert result.state.times["checked"] == T0
        assert result.state.values["checked"] is True

    def test_equal_times_let_the_later_arrival_win(self) -> None:
        state = rules.FieldState(values={"store_id": "a"}, times={"store_id": T0})
        assert rules.merge(state, {"store_id": "b"}, at=T0, now=T0).state.values["store_id"] == "b"

    def test_unknown_fields_are_rejected(self) -> None:
        state = rules.FieldState(values={}, times={})
        with pytest.raises(ValueError):
            rules.merge(state, {"household_id": "x"}, at=T0, now=T0)


class TestOrder:
    def test_aisles_follow_the_category_order_and_checked_items_sink(self) -> None:
        rows = [
            rules.Row(key="b", category="dairy_eggs", checked=False, added=T0),
            rules.Row(key="a", category="produce", checked=True, added=T0),
            rules.Row(key="c", category="produce", checked=False, added=T0 + timedelta(1)),
            rules.Row(key="d", category="produce", checked=False, added=T0),
        ]
        assert [r.key for r in rules.ordered(rows)] == ["d", "c", "b", "a"]
