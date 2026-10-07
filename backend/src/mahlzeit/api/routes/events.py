from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from mahlzeit.api import events
from mahlzeit.api.deps import COOKIE
from mahlzeit.db import get_db
from mahlzeit.domain.errors import Unauthorized
from mahlzeit.services import auth

router = APIRouter(tags=["events"])


def _session(
    request: Request,
    # Function scope: the database session closes before the stream starts, so an open
    # stream never holds a connection.
    db: Annotated[Session, Depends(get_db, scope="function")],
) -> auth.CurrentSession:
    return auth.resolve(db, request.cookies.get(COOKIE))


def _still_signed_in(app: FastAPI, token: str | None) -> bool:
    provider = app.dependency_overrides.get(get_db, get_db)
    sessions = provider()
    db = next(sessions)
    try:
        auth.resolve(db, token)
        return True
    except Unauthorized:
        return False
    finally:
        sessions.close()


@router.get(
    "/events",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def event_stream(
    request: Request, current: Annotated[auth.CurrentSession, Depends(_session)]
) -> StreamingResponse:
    """Server-sent events for the household: `change` with the kind of thing that changed
    (`{"entity": "list_item"}`, `"*"` for everything). The app refetches what it shows."""
    broker: events.Broker = request.app.state.events
    household_id = current.actor.household_id
    token = request.cookies.get(COOKIE)
    queue = broker.subscribe(household_id)

    async def check() -> bool:
        return await run_in_threadpool(_still_signed_in, request.app, token)

    async def body() -> AsyncIterator[str]:
        try:
            async for chunk in events.stream(queue, check):
                yield chunk
        finally:
            broker.unsubscribe(household_id, queue)

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
