"""Request dependencies: database session, the signed-in user, CSRF."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from mahlzeit.config import get_settings
from mahlzeit.db import get_db
from mahlzeit.domain.errors import Forbidden
from mahlzeit.services import auth

COOKIE = "mahlzeit_session"
CSRF_HEADER = "X-CSRF-Token"

Db = Annotated[Session, Depends(get_db)]


def current_session(request: Request, db: Db) -> auth.CurrentSession:
    return auth.resolve(db, request.cookies.get(COOKIE))


def current_session_for_write(
    request: Request, current: Annotated[auth.CurrentSession, Depends(current_session)]
) -> auth.CurrentSession:
    sent = request.headers.get(CSRF_HEADER, "")
    if not secrets.compare_digest(sent.encode(), current.session.csrf_token.encode()):
        raise Forbidden("csrf_failed")
    return current


Current = Annotated[auth.CurrentSession, Depends(current_session)]
CurrentWrite = Annotated[auth.CurrentSession, Depends(current_session_for_write)]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        COOKIE,
        token,
        max_age=settings.session_days * 24 * 3600,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        COOKIE, httponly=True, secure=settings.secure_cookies, samesite="lax", path="/"
    )
