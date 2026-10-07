"""Stock tools: get_stock, record_purchase, adjust_stock, set_tracking_mode,
mark_pantry_checked, get_list_suggestions, get_stock_report."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from mahlzeit import views
from mahlzeit.domain.catalogue import TrackingMode
from mahlzeit.domain.stock import Status
from mahlzeit.ids import uuid7
from mahlzeit.services import stock
from mahlzeit.services.stock import LineInput, PurchaseInput
from mahlzeit.tools.registry import ToolContext, tool
from mahlzeit.tools.shopping import CATEGORY_HELP, _store_id

StatusName = Literal["ok", "low", "out"]


class GetStockIn(BaseModel):
    category: str | None = Field(default=None, max_length=20, description=CATEGORY_HELP)


class PurchaseLineIn(BaseModel):
    item_id: uuid.UUID | None = Field(default=None, description="A catalogue item (search_items).")
    text: str | None = Field(
        default=None, max_length=200, description="Free text for anything not in the catalogue."
    )
    quantity: str | None = Field(
        default=None, max_length=80, description="'500 g', '1,5 kg', '2' (packages); optional."
    )
    amount: float | None = Field(
        default=None, description="Grams or millilitres into stock; read from quantity if omitted."
    )
    price_cents: int | None = Field(default=None, description="Optional.")
    list_item_id: uuid.UUID | None = Field(
        default=None, description="The shopping list item it came from; it leaves the list."
    )


class RecordPurchaseIn(BaseModel):
    lines: list[PurchaseLineIn] = Field(min_length=1, max_length=200)
    store: str | None = Field(default=None, max_length=80, description="ALDI, Lidl, ... optional.")
    day: date | None = Field(default=None, description="Default: today.")
    purchase_id: uuid.UUID | None = Field(
        default=None, description="Optional; repeating a call with the same id records it once."
    )


class AdjustStockIn(BaseModel):
    item_id: uuid.UUID
    count: float | None = Field(default=None, description="What is there now (g or ml).")
    waste: float | None = Field(default=None, description="Thrown away (g or ml).")
    add: float | None = Field(default=None, description="Found more than stock says (g or ml).")
    status: StatusName | None = Field(default=None, description="For status-only items.")


class SetTrackingModeIn(BaseModel):
    item_id: uuid.UUID
    mode: Literal["counted", "status"] | None = Field(
        description="By amount, or only ok/low/out (oil, spices); null: as the item says."
    )


class PantryCheckIn(BaseModel):
    category: str = Field(max_length=20, description=CATEGORY_HELP)
    counts: dict[uuid.UUID, float] = Field(
        default_factory=dict, max_length=500, description="Item id to what is there now."
    )
    statuses: dict[uuid.UUID, StatusName] = Field(default_factory=dict, max_length=500)


class EmptyIn(BaseModel):
    pass


class StockReportIn(BaseModel):
    start: date | None = Field(default=None, description="Default: 30 days before end.")
    end: date | None = Field(default=None, description="Default: today.")


@tool(
    "get_stock",
    "What is in the house, aisle by aisle: amounts of counted items (g or ml, never below "
    "zero) and ok/low/out for status-only items such as oil and spices. Stock is advisory.",
    GetStockIn,
    writes=False,
)
def get_stock(ctx: ToolContext, args: GetStockIn) -> views.StockOut:
    view = stock.get_stock(ctx.db, ctx.actor, language=ctx.language, category=args.category)
    return views.stock_view(view)


@tool(
    "record_purchase",
    "Record a shop: food goes into stock, status-only items become ok, and list items it came "
    "from (list_item_id) leave the shopping list. Prices are optional.",
    RecordPurchaseIn,
    writes=True,
)
def record_purchase(ctx: ToolContext, args: RecordPurchaseIn) -> views.PurchaseOut:
    data = PurchaseInput(
        id=args.purchase_id or uuid7(),
        store_id=_store_id(ctx, args.store) if args.store else None,
        day=args.day,
        lines=[LineInput(**line.model_dump()) for line in args.lines],
    )
    return views.purchase(stock.record_purchase(ctx.db, ctx.actor, data, language=ctx.language))


@tool(
    "adjust_stock",
    "Fix one item's stock: count (what is there now), waste (thrown away), add (found more), or "
    "status (ok, low, out) for status-only items. Exactly one of them.",
    AdjustStockIn,
    writes=True,
)
def adjust_stock(ctx: ToolContext, args: AdjustStockIn) -> views.StockRowOut:
    row = stock.adjust(
        ctx.db,
        ctx.actor,
        args.item_id,
        count=args.count,
        waste=args.waste,
        add=args.add,
        status=Status(args.status) if args.status else None,
        language=ctx.language,
    )
    return views.stock_row(row)


@tool(
    "set_tracking_mode",
    "Track an item in this household by amount ('counted') or only as ok/low/out ('status').",
    SetTrackingModeIn,
    writes=True,
)
def set_tracking_mode(ctx: ToolContext, args: SetTrackingModeIn) -> views.StockRowOut:
    mode = TrackingMode(args.mode) if args.mode else None
    return views.stock_row(
        stock.set_mode(ctx.db, ctx.actor, args.item_id, mode, language=ctx.language)
    )


@tool(
    "mark_pantry_checked",
    "The pantry check of one aisle: set what is there now per item, statuses of status-only "
    "items, and mark the aisle as checked. Items not named are taken as right.",
    PantryCheckIn,
    writes=True,
)
def mark_pantry_checked(ctx: ToolContext, args: PantryCheckIn) -> views.PantryCheckOut:
    check = stock.check_category(
        ctx.db,
        ctx.actor,
        args.category,
        counts=args.counts,
        statuses={k: Status(v) for k, v in args.statuses.items()},
    )
    return views.pantry_check(check)


@tool(
    "get_list_suggestions",
    "Suggestions for the shopping list (never added by themselves): what planned meals of the "
    "coming days need beyond stock, staples low or out, usual purchases not in stock.",
    EmptyIn,
    writes=False,
)
def get_list_suggestions(ctx: ToolContext, args: EmptyIn) -> views.SuggestionsOut:
    found = stock.suggestions(ctx.db, ctx.actor, language=ctx.language)
    return views.suggestions(stock.plan_days(ctx.db, ctx.actor), found)


@tool(
    "get_stock_report",
    "Purchased, logged (eaten at home), wasted and corrected amounts per item over a period, "
    "the shortfall (eaten beyond what stock knew of) and the spend where prices were entered.",
    StockReportIn,
    writes=False,
)
def get_stock_report(ctx: ToolContext, args: StockReportIn) -> views.StockReportOut:
    end = args.end or ctx.today
    start = args.start or end - timedelta(days=29)
    return views.stock_report(
        stock.report(ctx.db, ctx.actor, start=start, end=end, language=ctx.language)
    )
