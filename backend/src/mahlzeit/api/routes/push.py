from __future__ import annotations

from fastapi import APIRouter, Request, status

from mahlzeit.api.deps import Current, CurrentWrite, Db
from mahlzeit.api.schemas import PushStatusOut, PushSubscriptionIn, PushUnsubscribeIn
from mahlzeit.config import get_settings
from mahlzeit.services import push

router = APIRouter(prefix="/push", tags=["push"])


@router.get("", response_model=PushStatusOut)
def push_status(current: Current, db: Db) -> PushStatusOut:
    s = get_settings()
    return PushStatusOut(
        configured=s.push_enabled,
        public_key=s.vapid_public_key if s.push_enabled else None,
        devices=push.count(db, current.actor),
    )


@router.post("/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
def subscribe(body: PushSubscriptionIn, request: Request, current: CurrentWrite, db: Db) -> None:
    push.subscribe(
        db,
        current.actor,
        endpoint=body.endpoint,
        p256dh=body.keys.p256dh,
        auth=body.keys.auth,
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/subscriptions/remove", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe(body: PushUnsubscribeIn, current: CurrentWrite, db: Db) -> None:
    push.unsubscribe(db, current.actor, endpoint=body.endpoint)


@router.post("/test", status_code=status.HTTP_202_ACCEPTED)
def send_test(current: CurrentWrite, db: Db) -> None:
    push.send_test(db, current.actor)
