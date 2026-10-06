"""Shopping list tools: get_shopping_list, add_list_items, check_list_items, update_list_items,
remove_list_items. They send the same operations as the app (services/shopping.apply)."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from mahlzeit import clock, views
from mahlzeit.domain.catalogue import Category
from mahlzeit.domain.errors import NotFound
from mahlzeit.ids import uuid7
from mahlzeit.services import items, shopping
from mahlzeit.services.shopping import Op
from mahlzeit.tools.registry import ToolContext, tool

CATEGORY_HELP = "Aisle: " + ", ".join(c.value for c in Category) + "."
STORE_HELP = (
    "Store by name: ALDI, Lidl, EDEKA, REWE, Netto, Penny, dm, other, or one of the "
    "household's own stores from get_shopping_list. Empty string clears it."
)


class EmptyIn(BaseModel):
    pass


class NewListItem(BaseModel):
    text: str = Field(
        max_length=200,
        description="What to buy, e.g. 'Milch' or '2 Milch' or '500 g Hackfleisch'; a leading "
        "or trailing quantity is split off.",
    )
    item_id: uuid.UUID | None = Field(default=None, description="A catalogue item, optional.")
    quantity: str | None = Field(default=None, max_length=80)
    store: str | None = Field(default=None, max_length=80, description=STORE_HELP)
    category: str | None = Field(default=None, max_length=20, description=CATEGORY_HELP)


class AddListItemsIn(BaseModel):
    items: list[NewListItem] = Field(min_length=1, max_length=50)


class CheckListItemsIn(BaseModel):
    ids: list[uuid.UUID] = Field(
        min_length=1, max_length=100, description="From get_shopping_list."
    )
    checked: bool = Field(default=True, description="False unchecks.")


class ListItemChange(BaseModel):
    id: uuid.UUID
    text: str | None = Field(default=None, max_length=200)
    quantity: str | None = Field(default=None, max_length=80, description="Empty string clears.")
    store: str | None = Field(default=None, max_length=80, description=STORE_HELP)
    category: str | None = Field(default=None, max_length=20, description=CATEGORY_HELP)


class UpdateListItemsIn(BaseModel):
    changes: list[ListItemChange] = Field(min_length=1, max_length=50)


class RemoveListItemsIn(BaseModel):
    ids: list[uuid.UUID] = Field(
        min_length=1, max_length=100, description="From get_shopping_list."
    )


def _store_id(ctx: ToolContext, name: str) -> uuid.UUID | None:
    wanted = name.strip().casefold()
    if not wanted:
        return None
    for s in shopping.stores(ctx.db, ctx.actor):
        if wanted in {(s.key or "").casefold(), (s.name or "").casefold()}:
            return s.id
    raise NotFound("store_not_found", store=name)


def _existing(ctx: ToolContext, ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """Unknown ids are an error the model can read, not a silent per-item status."""
    for item_id in ids:
        shopping.get_row(ctx.db, ctx.actor, item_id)
    return ids


def _run(ctx: ToolContext, ops: list[Op]) -> views.ListOpsOut:
    results = shopping.apply(ctx.db, ctx.actor, ops, language=ctx.language)
    rows, stores = shopping.open_items(ctx.db, ctx.actor), shopping.stores(ctx.db, ctx.actor)
    return views.ListOpsOut(
        results=[views.list_op_result(r) for r in results],
        list=views.shopping_list(rows, stores, clock.now()),
    )


@tool(
    "get_shopping_list",
    "The household's shared shopping list, aisle by aisle with checked items last, plus the "
    "stores to choose from. Item ids are needed to check, change or remove items.",
    EmptyIn,
    writes=False,
)
def get_shopping_list(ctx: ToolContext, args: EmptyIn) -> views.ListOut:
    rows, stores = shopping.open_items(ctx.db, ctx.actor), shopping.stores(ctx.db, ctx.actor)
    return views.shopping_list(rows, stores, clock.now())


@tool(
    "add_list_items",
    "Put things on the shared shopping list. Each result says 'applied' or why not. The aisle "
    "and store default to where the household put the same thing last time.",
    AddListItemsIn,
    writes=True,
)
def add_list_items(ctx: ToolContext, args: AddListItemsIn) -> views.ListOpsOut:
    ops = []
    for new in args.items:
        fields: dict[str, Any] = {"text": new.text}
        if new.item_id:
            fields["item_id"] = items.get(ctx.db, ctx.actor, new.item_id).id
        if new.quantity:
            fields["quantity"] = new.quantity
        if new.store is not None:
            fields["store_id"] = _store_id(ctx, new.store)
        if new.category:
            fields["category"] = new.category
        ops.append(Op(kind="add", id=uuid7(), fields=fields))
    return _run(ctx, ops)


@tool(
    "check_list_items",
    "Tick items off the shopping list (bought or found at home), or untick them.",
    CheckListItemsIn,
    writes=True,
)
def check_list_items(ctx: ToolContext, args: CheckListItemsIn) -> views.ListOpsOut:
    return _run(
        ctx,
        [
            Op(kind="update", id=i, fields={"checked": args.checked})
            for i in _existing(ctx, args.ids)
        ],
    )


@tool(
    "update_list_items",
    "Change the text, quantity, store or aisle of list items. Only the fields given change.",
    UpdateListItemsIn,
    writes=True,
)
def update_list_items(ctx: ToolContext, args: UpdateListItemsIn) -> views.ListOpsOut:
    _existing(ctx, [c.id for c in args.changes])
    ops = []
    for change in args.changes:
        fields: dict[str, Any] = {}
        if change.text is not None:
            fields["text"] = change.text
        if change.quantity is not None:
            fields["quantity"] = change.quantity
        if change.store is not None:
            fields["store_id"] = _store_id(ctx, change.store)
        if change.category is not None:
            fields["category"] = change.category
        ops.append(Op(kind="update", id=change.id, fields=fields))
    return _run(ctx, ops)


@tool(
    "remove_list_items",
    "Take items off the shopping list for good.",
    RemoveListItemsIn,
    writes=True,
)
def remove_list_items(ctx: ToolContext, args: RemoveListItemsIn) -> views.ListOpsOut:
    return _run(ctx, [Op(kind="remove", id=i) for i in _existing(ctx, args.ids)])
