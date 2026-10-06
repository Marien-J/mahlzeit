from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.orm import Session

from mahlzeit.api.deps import CurrentWrite, Db
from mahlzeit.api.schemas import (
    HouseholdBriefOut,
    MeOut,
    MePatch,
    ProfileOut,
    ProfilePatch,
    UserOut,
)
from mahlzeit.models import Household
from mahlzeit.services import profiles

router = APIRouter(prefix="/me", tags=["me"])


def me_out(db: Session, me: profiles.Me, csrf_token: str) -> MeOut:
    household = db.get_one(Household, me.user.household_id)
    return MeOut(
        user=UserOut.model_validate(me.user),
        profile=ProfileOut.model_validate(me.profile),
        household=HouseholdBriefOut.model_validate(household),
        csrf_token=csrf_token,
    )


@router.patch("", response_model=MeOut)
def update_me(body: MePatch, current: CurrentWrite, db: Db) -> MeOut:
    me = profiles.update_user(db, current.actor, **body.model_dump(exclude_unset=True))
    return me_out(db, me, current.session.csrf_token)


@router.patch("/profile", response_model=MeOut)
def update_profile(body: ProfilePatch, current: CurrentWrite, db: Db) -> MeOut:
    me = profiles.update_profile(db, current.actor, **body.model_dump(exclude_unset=True))
    return me_out(db, me, current.session.csrf_token)
