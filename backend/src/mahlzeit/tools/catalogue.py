"""Catalogue tools: search_items, get_item, create_item, update_item, lookup_barcode,
search_online, set_favourite."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from mahlzeit import views
from mahlzeit.api import convert
from mahlzeit.api.schemas import ItemIn
from mahlzeit.off_client import get_off_client
from mahlzeit.services import items
from mahlzeit.tools.registry import ToolContext, tool


class SearchItemsIn(BaseModel):
    query: str = Field(
        max_length=100, description="Food name in German, English or Dutch. Typos are fine."
    )
    limit: int = Field(default=10, ge=1, le=50)
    own_only: bool = Field(
        default=False,
        description="Only the household's own items; with an empty query, lists all of them.",
    )


class ItemIdIn(BaseModel):
    item_id: uuid.UUID


class UpdateItemIn(ItemIn):
    item_id: uuid.UUID


class BarcodeIn(BaseModel):
    code: str = Field(max_length=14, description="EAN-8, EAN-13, UPC-A or GTIN-14 digits.")


class SearchOnlineIn(BaseModel):
    query: str = Field(min_length=2, max_length=100)


class FavouriteIn(BaseModel):
    item_id: uuid.UUID
    favourite: bool


@tool(
    "search_items",
    "Search the household's food catalogue (its own items first, then generic foods from the "
    "German BLS database). Returns items with nutrition per 100 g or ml and serving sizes. Use "
    "the item ids with log_food.",
    SearchItemsIn,
    writes=False,
)
def search_items(ctx: ToolContext, args: SearchItemsIn) -> list[views.ItemOut]:
    hits = items.search(ctx.db, ctx.actor, args.query, limit=args.limit, own=args.own_only)
    favs = {h.item.id for h in hits if h.favourite}
    return [views.item(h.item, ctx.language, favs) for h in hits]


@tool(
    "get_item",
    "One catalogue item with its nutrition per 100 g or ml, servings and barcodes.",
    ItemIdIn,
    writes=False,
)
def get_item(ctx: ToolContext, args: ItemIdIn) -> views.ItemOut:
    item = items.get(ctx.db, ctx.actor, args.item_id)
    return views.item(item, ctx.language, items.favourite_ids(ctx.db, ctx.actor))


@tool(
    "create_item",
    "Create a household item from a nutrition label: values per 100 g (or 100 ml), names in any "
    "of de/en/nl, optional serving sizes and barcodes. Energy (kcal) is stored as given.",
    ItemIn,
    writes=True,
)
def create_item(ctx: ToolContext, args: ItemIn) -> views.ItemOut:
    source_id = args.barcodes[0] if args.source == "off" and args.barcodes else None
    item = items.create(
        ctx.db,
        ctx.actor,
        convert.item_input(args),
        source=args.source if source_id else "custom",
        source_id=source_id,
    )
    return views.item(item, ctx.language, items.favourite_ids(ctx.db, ctx.actor))


@tool(
    "update_item",
    "Replace a household item's label data. Generic foods are read-only; "
    "create an own item instead.",
    UpdateItemIn,
    writes=True,
)
def update_item(ctx: ToolContext, args: UpdateItemIn) -> views.ItemOut:
    body = ItemIn.model_validate(args.model_dump(exclude={"item_id"}))
    item = items.update(ctx.db, ctx.actor, args.item_id, convert.item_input(body))
    return views.item(item, ctx.language, items.favourite_ids(ctx.db, ctx.actor))


@tool(
    "lookup_barcode",
    "Look up a barcode: the household's own item if known, else a draft from Open Food Facts "
    "that create_item can save (complete missing label values first).",
    BarcodeIn,
    writes=False,
)
def lookup_barcode(ctx: ToolContext, args: BarcodeIn) -> views.BarcodeOut:
    result = items.lookup_barcode(ctx.db, ctx.actor, args.code, get_off_client())
    return views.barcode(result, ctx.language, items.favourite_ids(ctx.db, ctx.actor))


@tool(
    "search_online",
    "Search Open Food Facts by name for branded products without a barcode at hand. Rate "
    "limited; prefer search_items for anything already in the catalogue.",
    SearchOnlineIn,
    writes=False,
)
def search_online(ctx: ToolContext, args: SearchOnlineIn) -> list[views.ItemDraftOut]:
    return [
        views.draft(d)
        for d in items.search_online(ctx.db, ctx.actor, args.query, ctx.language, get_off_client())
    ]


@tool(
    "set_favourite",
    "Mark or unmark an item as one of the person's favourites.",
    FavouriteIn,
    writes=True,
)
def set_favourite(ctx: ToolContext, args: FavouriteIn) -> dict[str, Literal[True]]:
    items.set_favourite(ctx.db, ctx.actor, args.item_id, args.favourite)
    return {"ok": True}
