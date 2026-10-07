"""The plan (meals for the coming days) and offers between members."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, status

from mahlzeit import views
from mahlzeit.api import convert
from mahlzeit.api.deps import Current, CurrentWrite, Db
from mahlzeit.api.schemas import OfferIn, OfferResponseIn
from mahlzeit.domain.offers import Action
from mahlzeit.services import day, offers

router = APIRouter(tags=["plan"])


@router.get("/plan", response_model=views.PlanOut)
def get_plan(start: date, current: Current, db: Db, days: int = 7) -> views.PlanOut:
    """Every entry of the household for `days` days from `start`, with the open offers."""
    return views.plan(
        day.get_plan(db, current.actor, start, days),
        offers.list_offers(db, current.actor),
        current.user.language,
        current.user.id,
    )


@router.get("/offers", response_model=list[views.OfferOut])
def list_offers(current: Current, db: Db, closed: bool = False) -> list[views.OfferOut]:
    """Offers to or from me: the open ones, or with `closed` also the last two weeks'."""
    found = offers.list_offers(db, current.actor, include_closed=closed)
    return [views.offer(v, current.user.language, current.user.id) for v in found]


@router.post("/offers", response_model=views.OfferOut, status_code=status.HTTP_201_CREATED)
def send_offer(body: OfferIn, current: CurrentWrite, db: Db) -> views.OfferOut:
    sent = offers.send(
        db, current.actor, entry_id=body.entry_id, to_user_id=body.to_user_id, share=body.share
    )
    return views.offer(sent, current.user.language, current.user.id)


@router.get("/offers/{offer_id}", response_model=views.OfferOut)
def get_offer(offer_id: uuid.UUID, current: Current, db: Db) -> views.OfferOut:
    found = offers.get(db, current.actor, offer_id)
    return views.offer(found, current.user.language, current.user.id)


@router.post("/offers/{offer_id}/respond", response_model=views.OfferOut)
def respond_to_offer(
    offer_id: uuid.UUID, body: OfferResponseIn, current: CurrentWrite, db: Db
) -> views.OfferOut:
    answered = offers.respond(
        db, current.actor, offer_id, Action(body.action), counter=convert.counter(body)
    )
    return views.offer(answered, current.user.language, current.user.id)


@router.post("/offers/{offer_id}/withdraw", response_model=views.OfferOut)
def withdraw_offer(offer_id: uuid.UUID, current: CurrentWrite, db: Db) -> views.OfferOut:
    withdrawn = offers.withdraw(db, current.actor, offer_id)
    return views.offer(withdrawn, current.user.language, current.user.id)
