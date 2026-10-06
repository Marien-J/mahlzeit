from __future__ import annotations

from fastapi import APIRouter

from mahlzeit import views
from mahlzeit.api.deps import Current, CurrentWrite, Db
from mahlzeit.api.schemas import TargetsIn, WeekPatternIn
from mahlzeit.domain.targets import DayType, Targets
from mahlzeit.services import targets

router = APIRouter(prefix="/targets", tags=["targets"])


@router.get("", response_model=views.TargetPlanOut)
def get_targets(current: Current, db: Db) -> views.TargetPlanOut:
    return views.target_plan(targets.plan(db, current.user.id))


@router.put("", response_model=views.TargetPlanOut)
def set_targets(body: TargetsIn, current: CurrentWrite, db: Db) -> views.TargetPlanOut:
    plan = targets.set_targets(
        db,
        current.actor,
        targets=Targets(kcal=body.kcal, protein=body.protein, carbs=body.carbs, fat=body.fat),
        day_types=[DayType(d) for d in body.day_types],
        valid_from=body.valid_from,
    )
    return views.target_plan(plan)


@router.put("/week-pattern", response_model=views.TargetPlanOut)
def set_week_pattern(body: WeekPatternIn, current: CurrentWrite, db: Db) -> views.TargetPlanOut:
    return views.target_plan(targets.set_week_pattern(db, current.actor, body.pattern))
