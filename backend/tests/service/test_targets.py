from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from mahlzeit.domain.errors import Invalid
from mahlzeit.domain.targets import DayType, Targets
from mahlzeit.models import ChangeRecord
from mahlzeit.services import targets
from tests import factories

TODAY = date(2026, 10, 6)  # the clock fixture's day, a Tuesday


class TestTargets:
    def test_no_targets_by_default(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        assert targets.targets_on(db, jonas.user.id, TODAY) == (DayType.REST, None)

    def test_training_and_rest_targets(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        targets.set_targets(
            db, jonas.actor, targets=Targets(kcal=2800, protein=180), day_types=[DayType.TRAINING]
        )
        targets.set_targets(
            db, jonas.actor, targets=Targets(kcal=2300, protein=170), day_types=[DayType.REST]
        )
        targets.set_week_pattern(db, jonas.actor, "TTRTRRR")  # Tuesday trains
        assert targets.targets_on(db, jonas.user.id, TODAY) == (
            DayType.TRAINING,
            Targets(kcal=2800, protein=180),
        )
        assert targets.targets_on(db, jonas.user.id, date(2026, 10, 7)) == (
            DayType.REST,
            Targets(kcal=2300, protein=170),
        )

    def test_past_days_keep_their_targets(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        both = [DayType.TRAINING, DayType.REST]
        targets.set_targets(
            db, jonas.actor, targets=Targets(kcal=2500), day_types=both, valid_from=date(2026, 9, 1)
        )
        targets.set_targets(db, jonas.actor, targets=Targets(kcal=2200), day_types=both)
        assert targets.targets_on(db, jonas.user.id, date(2026, 10, 5))[1] == Targets(kcal=2500)
        assert targets.targets_on(db, jonas.user.id, TODAY)[1] == Targets(kcal=2200)

    def test_setting_the_same_day_again_replaces(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        targets.set_targets(db, jonas.actor, targets=Targets(kcal=2500), day_types=[DayType.REST])
        plan = targets.set_targets(
            db, jonas.actor, targets=Targets(kcal=2400), day_types=[DayType.REST]
        )
        assert [s.targets.kcal for s in plan.history] == [2400]

    def test_override_one_day(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        targets.set_day_type(db, jonas.actor, TODAY, DayType.TRAINING)
        assert targets.day_type_of(db, jonas.user.id, TODAY) is DayType.TRAINING
        targets.set_day_type(db, jonas.actor, TODAY, None)
        assert targets.day_type_of(db, jonas.user.id, TODAY) is DayType.REST

    def test_validation(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        with pytest.raises(Invalid):
            targets.set_targets(db, jonas.actor, targets=Targets(kcal=-5), day_types=[DayType.REST])
        with pytest.raises(Invalid):
            targets.set_targets(db, jonas.actor, targets=Targets(kcal=5), day_types=[])
        with pytest.raises(Invalid) as err:
            targets.set_week_pattern(db, jonas.actor, "TTTT")
        assert err.value.code == "week_pattern_invalid"

    def test_changes_are_recorded(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        targets.set_targets(db, jonas.actor, targets=Targets(kcal=2300), day_types=[DayType.REST])
        change = db.scalars(select(ChangeRecord).where(ChangeRecord.entity == "targets")).one()
        assert change.after["kcal"] == 2300 and change.client == "ui"
