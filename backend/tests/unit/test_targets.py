from datetime import date
from typing import ClassVar

import pytest

from mahlzeit.domain.nutrition import Nutrients
from mahlzeit.domain.targets import (
    DayType,
    Targets,
    TargetSet,
    day_type_for,
    parse_week_pattern,
    remaining,
    target_for,
)

MON = date(2026, 10, 5)  # a Monday


class TestWeekPattern:
    def test_default_is_rest(self) -> None:
        assert day_type_for(MON, pattern="RRRRRRR") is DayType.REST

    def test_pattern_is_monday_first(self) -> None:
        pattern = "TRTRTRR"
        assert day_type_for(MON, pattern=pattern) is DayType.TRAINING
        assert day_type_for(date(2026, 10, 6), pattern=pattern) is DayType.REST

    def test_override_wins(self) -> None:
        assert day_type_for(MON, pattern="TTTTTTT", override=DayType.REST) is DayType.REST

    def test_logged_workout_makes_training_unless_overridden(self) -> None:
        assert day_type_for(MON, pattern="RRRRRRR", has_workout=True) is DayType.TRAINING
        assert (
            day_type_for(MON, pattern="RRRRRRR", has_workout=True, override=DayType.REST)
            is DayType.REST
        )

    @pytest.mark.parametrize("bad", ["", "TTT", "TRTRTRX", "trtrtrr8"])
    def test_rejects_bad_patterns(self, bad: str) -> None:
        with pytest.raises(ValueError):
            parse_week_pattern(bad)

    def test_accepts_lowercase(self) -> None:
        assert parse_week_pattern("trtrtrr") == "TRTRTRR"


def _set(
    valid_from: date, day_type: DayType, kcal: float | None, protein: float | None = None
) -> TargetSet:
    return TargetSet(
        valid_from=valid_from, day_type=day_type, targets=Targets(kcal=kcal, protein=protein)
    )


class TestTargetHistory:
    SETS: ClassVar[list[TargetSet]] = [
        _set(date(2026, 1, 1), DayType.TRAINING, 2800, 180),
        _set(date(2026, 1, 1), DayType.REST, 2300, 170),
        _set(date(2026, 6, 1), DayType.TRAINING, 3000, 190),
    ]

    def test_uses_the_set_valid_on_that_day(self) -> None:
        assert target_for(date(2026, 5, 31), DayType.TRAINING, self.SETS).kcal == 2800
        assert target_for(date(2026, 6, 1), DayType.TRAINING, self.SETS).kcal == 3000

    def test_day_types_have_separate_history(self) -> None:
        assert target_for(date(2026, 7, 1), DayType.REST, self.SETS).kcal == 2300

    def test_before_any_set_there_are_no_targets(self) -> None:
        assert target_for(date(2025, 12, 31), DayType.REST, self.SETS) is None

    def test_no_sets_means_no_targets(self) -> None:
        assert target_for(MON, DayType.REST, []) is None


class TestRemaining:
    def test_target_minus_logged(self) -> None:
        left = remaining(
            Targets(kcal=2000, protein=150, carbs=None, fat=70),
            Nutrients(kcal=1500, protein=160, fat=20),
        )
        assert left.kcal == 500
        assert left.protein == -10  # over target shows as negative
        assert left.carbs is None  # no target, nothing left to show
        assert left.fat == 50

    def test_no_targets_means_nothing_remaining(self) -> None:
        assert remaining(None, Nutrients(kcal=100)) is None
