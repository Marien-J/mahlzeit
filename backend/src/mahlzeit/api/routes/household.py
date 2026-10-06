from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from mahlzeit.api.deps import Current, CurrentWrite, Db
from mahlzeit.api.schemas import (
    HouseholdOut,
    HouseholdPatch,
    InviteCreateIn,
    InviteOut,
    IssuedInviteOut,
    MemberOut,
)
from mahlzeit.domain.accounts import MAX_MEMBERS
from mahlzeit.domain.permissions import Actor
from mahlzeit.models import Household
from mahlzeit.services import households, invites

router = APIRouter(prefix="/household", tags=["household"])


def household_out(household: Household, actor: Actor) -> HouseholdOut:
    return HouseholdOut(
        id=household.id,
        name=household.name,
        max_members=MAX_MEMBERS,
        members=[
            MemberOut(
                id=m.id,
                display_name=m.display_name,
                joined_at=m.created_at,
                is_me=m.id == actor.user_id,
            )
            for m in household.members
        ],
    )


@router.get("", response_model=HouseholdOut)
def get_household(current: Current, db: Db) -> HouseholdOut:
    return household_out(households.get(db, current.actor), current.actor)


@router.patch("", response_model=HouseholdOut)
def rename_household(body: HouseholdPatch, current: CurrentWrite, db: Db) -> HouseholdOut:
    return household_out(households.rename(db, current.actor, body.name), current.actor)


@router.get("/invites", response_model=list[InviteOut])
def list_invites(current: Current, db: Db) -> list[InviteOut]:
    return [InviteOut.model_validate(i) for i in invites.list_partner_invites(db, current.actor)]


@router.post("/invites", response_model=IssuedInviteOut, status_code=status.HTTP_201_CREATED)
def create_invite(body: InviteCreateIn, current: CurrentWrite, db: Db) -> IssuedInviteOut:
    issued = invites.create_partner_invite(db, current.actor, note=body.note)
    return IssuedInviteOut(
        invite=InviteOut.model_validate(issued.invite), link=issued.link, code=issued.display_code
    )


@router.delete("/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invite(invite_id: uuid.UUID, current: CurrentWrite, db: Db) -> None:
    invites.revoke_invite(db, current.actor, invite_id)
