from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from mahlzeit import views
from mahlzeit.api import convert
from mahlzeit.api.deps import Current, CurrentWrite, Db
from mahlzeit.api.schemas import FavouriteIn, ItemIn
from mahlzeit.off_client import get_off_client
from mahlzeit.services import items

router = APIRouter(tags=["catalogue"])


@router.get("/items", response_model=list[views.ItemOut])
def search_items(
    current: Current,
    db: Db,
    q: Annotated[str, Query(max_length=100)] = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
    own: bool = False,
) -> list[views.ItemOut]:
    """`own=true`: only the household's own items (the foods page)."""
    hits = items.search(db, current.actor, q, limit=limit, own=own)
    favs = {h.item.id for h in hits if h.favourite}
    return [views.item(h.item, current.user.language, favs) for h in hits]


@router.get("/items/{item_id}", response_model=views.ItemOut)
def get_item(item_id: uuid.UUID, current: Current, db: Db) -> views.ItemOut:
    item = items.get(db, current.actor, item_id)
    return views.item(item, current.user.language, items.favourite_ids(db, current.actor))


@router.post("/items", response_model=views.ItemOut, status_code=status.HTTP_201_CREATED)
def create_item(body: ItemIn, current: CurrentWrite, db: Db) -> views.ItemOut:
    source_id = body.barcodes[0] if body.source == "off" and body.barcodes else None
    item = items.create(
        db,
        current.actor,
        convert.item_input(body),
        source=body.source if source_id else "custom",
        source_id=source_id,
    )
    return views.item(item, current.user.language, items.favourite_ids(db, current.actor))


@router.put("/items/{item_id}", response_model=views.ItemOut)
def update_item(item_id: uuid.UUID, body: ItemIn, current: CurrentWrite, db: Db) -> views.ItemOut:
    item = items.update(db, current.actor, item_id, convert.item_input(body))
    return views.item(item, current.user.language, items.favourite_ids(db, current.actor))


@router.put("/items/{item_id}/favourite", status_code=status.HTTP_204_NO_CONTENT)
def set_favourite(item_id: uuid.UUID, body: FavouriteIn, current: CurrentWrite, db: Db) -> None:
    items.set_favourite(db, current.actor, item_id, body.on)


@router.get("/barcodes/{code}", response_model=views.BarcodeOut)
def lookup_barcode(code: str, current: Current, db: Db) -> views.BarcodeOut:
    result = items.lookup_barcode(db, current.actor, code, get_off_client())
    return views.barcode(result, current.user.language, items.favourite_ids(db, current.actor))


@router.get("/online-search", response_model=list[views.ItemDraftOut])
def search_online(
    current: Current, db: Db, q: Annotated[str, Query(min_length=2, max_length=100)]
) -> list[views.ItemDraftOut]:
    drafts = items.search_online(db, current.actor, q, current.user.language, get_off_client())
    return [views.draft(d) for d in drafts]
