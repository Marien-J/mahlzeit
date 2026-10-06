from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from mahlzeit.api.deps import (
    Current,
    CurrentWrite,
    Db,
    clear_session_cookie,
    client_ip,
    set_session_cookie,
)
from mahlzeit.api.routes.me import me_out
from mahlzeit.api.schemas import (
    LoginIn,
    MeOut,
    PasswordChangeIn,
    ResetConfirmIn,
    ResetRequestIn,
)
from mahlzeit.services import auth, profiles

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, request: Request, response: Response, db: Db) -> MeOut:
    started = auth.login(
        db,
        email=body.email,
        password=body.password,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    set_session_cookie(response, started.token)
    me = profiles.get_me(db, auth.actor_for(started.user))
    return me_out(db, me, started.session.csrf_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(current: CurrentWrite, response: Response, db: Db) -> None:
    auth.logout(db, current)
    clear_session_cookie(response)


@router.get("/me", response_model=MeOut)
def me(current: Current, db: Db) -> MeOut:
    return me_out(db, profiles.get_me(db, current.actor), current.session.csrf_token)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: PasswordChangeIn, current: CurrentWrite, db: Db) -> None:
    auth.change_password(db, current, old=body.current_password, new=body.new_password)


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
def request_reset(body: ResetRequestIn, db: Db) -> None:
    auth.request_password_reset(db, email=body.email)


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_reset(body: ResetConfirmIn, db: Db) -> None:
    auth.confirm_password_reset(db, token=body.token, new=body.password)
