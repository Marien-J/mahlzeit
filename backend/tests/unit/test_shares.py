import pytest

from mahlzeit.domain import shares
from mahlzeit.domain.errors import Invalid
from mahlzeit.domain.shares import MIN_SHARE, PartShare


def part(who: str, share: float, *, logged: bool = False) -> PartShare:
    return PartShare(key=who, share=share, logged=logged)


class TestEqualShares:
    @pytest.mark.parametrize(("people", "each"), [(1, 1.0), (2, 0.5), (4, 0.25)])
    def test_split_evenly(self, people: int, each: float) -> None:
        assert shares.equal(people) == each

    def test_nobody_is_not_a_split(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            shares.equal(0)


class TestCheckShare:
    def test_a_single_person_may_eat_part_of_a_dish(self) -> None:
        assert shares.check(0.4, people=1) == 0.4
        assert shares.check(1, people=1) == 1.0

    def test_a_joint_meal_leaves_every_other_person_something(self) -> None:
        assert shares.check(0.95, people=2) == 0.95
        with pytest.raises(Invalid, match="share_invalid"):
            shares.check(0.96, people=2)
        assert shares.check(0.85, people=4) == 0.85
        with pytest.raises(Invalid, match="share_invalid"):
            shares.check(0.9, people=4)

    @pytest.mark.parametrize("share", [0, -0.2, MIN_SHARE / 2, 1.2])
    def test_out_of_range(self, share: float) -> None:
        with pytest.raises(Invalid, match="share_invalid"):
            shares.check(share, people=1)


class TestRebalance:
    def test_the_partner_takes_the_rest_of_a_planned_dish(self) -> None:
        parts = [part("me", 0.5), part("you", 0.5)]
        assert shares.rebalance(parts, who="me", share=0.7) == {"you": pytest.approx(0.3)}

    def test_a_logged_part_is_never_changed_behind_its_owner(self) -> None:
        parts = [part("me", 0.5), part("you", 0.5, logged=True)]
        assert shares.rebalance(parts, who="me", share=0.7) == {}

    def test_everyone_else_shares_the_rest_in_proportion(self) -> None:
        parts = [part("a", 0.5), part("b", 0.3), part("c", 0.2)]
        assert shares.rebalance(parts, who="a", share=0.2) == {
            "b": pytest.approx(0.48),
            "c": pytest.approx(0.32),
        }

    def test_logged_parts_are_kept_out_of_the_rest(self) -> None:
        parts = [part("a", 0.4), part("b", 0.3, logged=True), part("c", 0.3)]
        assert shares.rebalance(parts, who="a", share=0.5) == {"c": pytest.approx(0.2)}

    def test_nobody_is_pushed_below_the_minimum(self) -> None:
        parts = [part("me", 0.5), part("you", 0.5)]
        assert shares.rebalance(parts, who="me", share=0.97) == {"you": MIN_SHARE}

    def test_a_single_person_has_nobody_to_rebalance(self) -> None:
        assert shares.rebalance([part("me", 1.0)], who="me", share=0.6) == {}


class TestSplitForNewParticipant:
    def test_a_partner_joining_takes_half(self) -> None:
        assert shares.joining([part("me", 1.0)]) == (0.5, {"me": 0.5})

    def test_a_logged_part_keeps_its_share_and_the_newcomer_takes_the_rest(self) -> None:
        mine = part("me", 0.6, logged=True)
        assert shares.joining([mine]) == (pytest.approx(0.4), {})

    def test_three_people(self) -> None:
        assert shares.joining([part("a", 0.5), part("b", 0.5)]) == (
            pytest.approx(1 / 3),
            {"a": pytest.approx(1 / 3), "b": pytest.approx(1 / 3)},
        )


class TestExactAmounts:
    def test_the_fraction_of_a_component_a_person_weighed(self) -> None:
        assert shares.exact_fraction(component_amount=400, eaten=230) == pytest.approx(0.575)

    def test_a_component_without_an_amount_cannot_be_weighed(self) -> None:
        with pytest.raises(Invalid, match="exact_amount_invalid"):
            shares.exact_fraction(component_amount=0, eaten=50)

    @pytest.mark.parametrize("eaten", [0, -1, 100_001])
    def test_bounds(self, eaten: float) -> None:
        with pytest.raises(Invalid, match="exact_amount_invalid"):
            shares.exact_fraction(component_amount=400, eaten=eaten)


class TestNormalize:
    def test_when_a_partner_leaves_the_rest_takes_the_whole_dish(self) -> None:
        assert shares.normalize([part("me", 0.5)]) == {"me": 1.0}

    def test_open_parts_grow_in_proportion_to_fill_what_logged_parts_leave(self) -> None:
        parts = [part("a", 0.2), part("b", 0.2), part("c", 0.3, logged=True)]
        assert shares.normalize(parts) == {"a": pytest.approx(0.35), "b": pytest.approx(0.35)}

    def test_nothing_to_do_when_everyone_has_eaten(self) -> None:
        assert shares.normalize([part("a", 0.4, logged=True)]) == {}


class TestRebalanceKeepsTheDishWhole:
    def test_a_person_held_at_the_minimum_does_not_push_the_total_over_one(self) -> None:
        parts = [part("a", 0.5), part("b", 0.45), part("c", 0.05)]
        new = shares.rebalance(parts, who="a", share=0.85)
        assert new == {"b": pytest.approx(0.10), "c": MIN_SHARE}
        assert 0.85 + sum(new.values()) == pytest.approx(1.0)
