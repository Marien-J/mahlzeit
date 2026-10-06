"""Public invite endpoints: look at an invite and accept it."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from mahlzeit.api.deps import Db, set_session_cookie
from mahlzeit.api.routes.me import me_out
from mahlzeit.api.schemas import AcceptInviteIn, InvitePreviewOut, MeOut
from mahlzeit.services import auth, invites, profiles

router = APIRouter(prefix="/invites", tags=["invites"])


@router.get("/{key}", response_model=InvitePreviewOut)
def preview_invite(key: str, db: Db) -> InvitePreviewOut:
    p = invites.preview(db, key)
    return InvitePreviewOut(
        kind=p.kind.value,
        status=p.status.value,
        household_name=p.household_name,
        inviter_name=p.inviter_name,
        language=p.language,
        expires_at=p.expires_at,
    )


@router.post("/accept", response_model=MeOut, status_code=status.HTTP_201_CREATED)
def accept_invite(body: AcceptInviteIn, request: Request, response: Response, db: Db) -> MeOut:
    started = invites.accept(
        db,
        key=body.key,
        email=body.email,
        password=body.password,
        display_name=body.display_name,
        language=body.language,
        time_zone=body.time_zone,
        household_name=body.household_name,
        user_agent=request.headers.get("user-agent"),
    )
    set_session_cookie(response, started.token)
    return me_out(db, profiles.get_me(db, auth.actor_for(started.user)), started.session.csrf_token)
