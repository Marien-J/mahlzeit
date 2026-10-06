from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy.orm import Session

from mahlzeit import clock, views
from mahlzeit.api import convert
from mahlzeit.api.deps import Current, CurrentWrite, Db
from mahlzeit.api.schemas import ListOpsIn, StoreIn
from mahlzeit.domain.permissions import Actor
from mahlzeit.services import shopping

router = APIRouter(tags=["shopping list"])


def _list(db: Session, actor: Actor) -> views.ListOut:
    return views.shopping_list(
        shopping.open_items(db, actor), shopping.stores(db, actor), clock.now()
    )


@router.get("/list", response_model=views.ListOut)
def get_list(current: Current, db: Db) -> views.ListOut:
    return _list(db, current.actor)


@router.post("/list/ops", response_model=views.ListOpsOut)
def apply_list_ops(body: ListOpsIn, current: CurrentWrite, db: Db) -> views.ListOpsOut:
    """Apply changes in order, made online or queued offline. Each change carries the item's
    client-made id and the time it was made, so sending the same batch twice is harmless.
    Answers with each change's outcome and the list as it is now."""
    results = shopping.apply(
        db, current.actor, [convert.list_op(o) for o in body.ops], language=current.user.language
    )
    return views.ListOpsOut(
        results=[views.list_op_result(r) for r in results], list=_list(db, current.actor)
    )


@router.get("/list/history", response_model=list[views.ListMemoryOut])
def list_history(current: Current, db: Db) -> list[views.ListMemoryOut]:
    """What the household has put on the list before, most used first."""
    return [views.list_memory(m) for m in shopping.history(db, current.actor)]


@router.post("/stores", response_model=views.StoreOut, status_code=status.HTTP_201_CREATED)
def create_store(body: StoreIn, current: CurrentWrite, db: Db) -> views.StoreOut:
    return views.store(shopping.create_store(db, current.actor, body.name))


@router.delete("/stores/{store_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_store(store_id: uuid.UUID, current: CurrentWrite, db: Db) -> None:
    shopping.delete_store(db, current.actor, store_id)
