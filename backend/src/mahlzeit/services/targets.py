"""A person's optional targets, their history, and training and rest days."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from mahlzeit import clock
from mahlzeit.domain import targets as rules
from mahlzeit.domain.errors import Invalid
from mahlzeit.domain.permissions import Actor
from mahlzeit.domain.targets import DayType, Targets
from mahlzeit.models import DayTypeOverride, Profile, TargetSet, User
from mahlzeit.services import audit


def today_for(user: User) -> date:
    return clock.now().astimezone(ZoneInfo(user.time_zone)).date()


@dataclass(frozen=True)
class TargetPlan:
    week_pattern: str
    history: list[rules.TargetSet]


def _sets(db: Session, user_id: object) -> list[rules.TargetSet]:
    rows = db.scalars(
        select(TargetSet).where(TargetSet.user_id == user_id).order_by(TargetSet.valid_from)
    )
    return [
        rules.TargetSet(
            valid_from=r.valid_from,
            day_type=DayType(r.day_type),
            targets=Targets(kcal=r.kcal, protein=r.protein, carbs=r.carbs, fat=r.fat),
        )
        for r in rows
    ]


def plan(db: Session, user_id: object) -> TargetPlan:
    profile = db.get_one(Profile, user_id)
    return TargetPlan(week_pattern=profile.week_pattern, history=_sets(db, user_id))


def _check(t: Targets) -> None:
    for name in ("kcal", "protein", "carbs", "fat"):
        value = getattr(t, name)
        limit = 10_000 if name == "kcal" else 1_000
        if value is not None and not 0 <= value <= limit:
            raise Invalid("target_invalid", nutrient=name)


def set_targets(
    db: Session,
    actor: Actor,
    *,
    targets: Targets,
    day_types: list[DayType],
    valid_from: date | None = None,
) -> TargetPlan:
    """Targets from a date on (default today). Earlier days keep the targets valid back then."""
    _check(targets)
    if not day_types:
        raise Invalid("day_type_required")
    user = db.get_one(User, actor.user_id)
    start = valid_from or today_for(user)
    for day_type in day_types:
        values = {
            "kcal": targets.kcal,
            "protein": targets.protein,
            "carbs": targets.carbs,
            "fat": targets.fat,
        }
        db.execute(
            insert(TargetSet)
            .values(
                user_id=actor.user_id,
                valid_from=start,
                day_type=day_type.value,
                created_at=clock.now(),
                **values,
            )
            .on_conflict_do_update(
                index_elements=["user_id", "valid_from", "day_type"], set_=values
            )
        )
        audit.record(
            db,
            actor=actor,
            entity="targets",
            entity_id=actor.user_id,
            action="set",
            after={"valid_from": start.isoformat(), "day_type": day_type.value, **values},
        )
    db.commit()
    return plan(db, actor.user_id)


def set_week_pattern(db: Session, actor: Actor, pattern: str) -> TargetPlan:
    try:
        cleaned = rules.parse_week_pattern(pattern)
    except ValueError as err:
        raise Invalid("week_pattern_invalid") from err
    profile = db.get_one(Profile, actor.user_id)
    if profile.week_pattern != cleaned:
        audit.record(
            db,
            actor=actor,
            entity="profile",
            entity_id=actor.user_id,
            action="updated",
            before={"week_pattern": profile.week_pattern},
            after={"week_pattern": cleaned},
        )
        profile.week_pattern = cleaned
        db.commit()
    return plan(db, actor.user_id)


def set_day_type(db: Session, actor: Actor, day: date, day_type: DayType | None) -> None:
    """Override one day's type, or None to go back to the weekly pattern."""
    db.execute(
        delete(DayTypeOverride).where(
            DayTypeOverride.user_id == actor.user_id, DayTypeOverride.day == day
        )
    )
    if day_type is not None:
        db.add(DayTypeOverride(user_id=actor.user_id, day=day, day_type=day_type.value))
    audit.record(
        db,
        actor=actor,
        entity="day_type",
        entity_id=actor.user_id,
        action="set",
        after={"day": day.isoformat(), "day_type": day_type.value if day_type else None},
    )
    db.commit()


def day_type_of(db: Session, user_id: object, day: date) -> DayType:
    profile = db.get_one(Profile, user_id)
    override = db.get(DayTypeOverride, (user_id, day))
    return rules.day_type_for(
        day,
        pattern=profile.week_pattern,
        override=DayType(override.day_type) if override else None,
        has_workout=False,  # workouts arrive in M5
    )


def targets_on(db: Session, user_id: object, day: date) -> tuple[DayType, Targets | None]:
    day_type = day_type_of(db, user_id, day)
    return day_type, rules.target_for(day, day_type, _sets(db, user_id))
