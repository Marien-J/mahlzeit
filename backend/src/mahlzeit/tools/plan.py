"""Plan tools: get_meal_plan, plan_meal, list_offers, send_offer, respond_to_offer, withdraw_offer,
set_share, set_exact_amounts, move_entry, add_recipe_to_list."""

from __future__ import annotations

import datetime as dt
import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from mahlzeit import views
from mahlzeit.domain.day import Slot
from mahlzeit.domain.errors import Invalid
from mahlzeit.domain.offers import Action
from mahlzeit.services import day, offers, recipes
from mahlzeit.services.day import EntryInput
from mahlzeit.services.offers import Counter
from mahlzeit.tools.day import FoodIn, QuickAddIn, SlotName, _components
from mahlzeit.tools.registry import ToolContext, tool


class GetPlanIn(BaseModel):
    start: date | None = Field(default=None, description="First day; today when omitted.")
    days: int = Field(default=7, ge=1, le=31, description="How many days (1 to 31).")


class PlanMealIn(BaseModel):
    day: date | None = Field(default=None, description="ISO date, today or later (up to 30 days).")
    slot: SlotName
    time: dt.time | None = Field(default=None, description="HH:MM; defaults by slot.")
    name: str | None = Field(
        default=None,
        max_length=120,
        description="A name alone is a valid plan ('Pizza from the oven').",
    )
    recipe_id: uuid.UUID | None = Field(default=None, description="A recipe, from list_recipes.")
    portions: float = Field(default=1.0, description="Portions of the recipe.")
    foods: list[FoodIn] = Field(default_factory=list, max_length=50)
    quick_add: list[QuickAddIn] = Field(default_factory=list, max_length=20)
    joint: bool = Field(default=False, description="Also for the rest of the household.")


class ListOffersIn(BaseModel):
    include_closed: bool = Field(
        default=False,
        description="Also answered, withdrawn and expired offers of the last 2 weeks.",
    )


class SendOfferIn(BaseModel):
    entry_id: uuid.UUID = Field(description="One of my planned meals (from get_meal_plan).")
    to_user_id: uuid.UUID | None = Field(
        default=None, description="Who gets the offer; the other person when there is only one."
    )
    share: float = Field(default=0.5, description="The receiver's share of the dish.")


class CounterMealIn(BaseModel):
    time: dt.time | None = None
    name: str | None = Field(default=None, max_length=120)
    recipe_id: uuid.UUID | None = None
    portions: float = 1.0
    foods: list[FoodIn] = Field(default_factory=list, max_length=50)
    quick_add: list[QuickAddIn] = Field(default_factory=list, max_length=20)


class RespondToOfferIn(BaseModel):
    offer_id: uuid.UUID
    action: Literal["accept", "decline", "counter"] = Field(
        description="Accept makes it a joint meal and replaces my own plan for that slot."
    )
    counter_entry_id: uuid.UUID | None = Field(
        default=None, description="For a counter: one of my own plans for the same slot."
    )
    counter_meal: CounterMealIn | None = Field(
        default=None, description="Or a new meal for the same slot."
    )


class OfferIdIn(BaseModel):
    offer_id: uuid.UUID


class SetShareIn(BaseModel):
    entry_id: uuid.UUID
    share: float = Field(description="My share of the dish, 0.05 to 0.95 on a joint meal.")


class ExactAmountIn(BaseModel):
    component_id: uuid.UUID = Field(description="From the entry's components.")
    amount: float | None = Field(
        description="What I weighed out for myself in g or ml; null goes back to my share."
    )


class SetExactAmountsIn(BaseModel):
    entry_id: uuid.UUID
    amounts: list[ExactAmountIn] = Field(max_length=50)


class MoveEntryIn(BaseModel):
    entry_id: uuid.UUID
    before_id: uuid.UUID | None = Field(
        description="Put it before this entry of my day; null puts it last."
    )


class AddRecipeToListIn(BaseModel):
    recipe_id: uuid.UUID
    portions: float | None = Field(default=None, description="Default: the whole recipe.")


def _receiver(ctx: ToolContext, to_user_id: uuid.UUID | None) -> uuid.UUID:
    if to_user_id is not None:
        return to_user_id
    others = day.others(ctx.db, ctx.actor)
    if not others:
        raise Invalid("no_partner")
    if len(others) > 1:
        raise Invalid("offer_receiver_required")
    return others[0].id


# --- plan -----------------------------------------------------------------------------------


@tool(
    "get_meal_plan",
    "The household's meals for a range of days (default the next 7): every planned and eaten "
    "entry with who is on it, their shares and state, plus open offers. Use it to see what is "
    "planned and what is still free.",
    GetPlanIn,
    writes=False,
)
def get_meal_plan(ctx: ToolContext, args: GetPlanIn) -> views.PlanOut:
    result = day.get_plan(ctx.db, ctx.actor, args.start or ctx.today, args.days)
    return views.plan(
        result, offers.list_offers(ctx.db, ctx.actor), ctx.language, ctx.actor.user_id
    )


@tool(
    "plan_meal",
    "Plan a meal for the signed-in person for today or a later day (up to 30 days ahead): a "
    "recipe, catalogue foods, quick-add foods, or just a name. It stays planned until eaten "
    "(log_planned_meal). With joint=true it is a plan for everyone in the household.",
    PlanMealIn,
    writes=True,
)
def plan_meal(ctx: ToolContext, args: PlanMealIn) -> views.EntryOut:
    entry = day.plan_meal(
        ctx.db,
        ctx.actor,
        EntryInput(
            day=args.day or ctx.today,
            slot=Slot(args.slot),
            at=args.time,
            name=args.name,
            components=_components(args.foods, args.quick_add),
            recipe_id=args.recipe_id,
            portions=args.portions,
            joint=args.joint,
        ),
    )
    return views.entry(entry, ctx.language, ctx.actor.user_id)


@tool(
    "set_share",
    "Set my share of a joint meal. Those who have not eaten yet take the rest; an eaten part "
    "is never changed.",
    SetShareIn,
    writes=True,
)
def set_share(ctx: ToolContext, args: SetShareIn) -> views.EntryOut:
    entry = day.set_share(ctx.db, ctx.actor, args.entry_id, args.share)
    return views.entry(entry, ctx.language, ctx.actor.user_id)


@tool(
    "set_exact_amounts",
    "Record what I weighed out for myself of single components of a meal, instead of going by "
    "my share. null for a component goes back to the share.",
    SetExactAmountsIn,
    writes=True,
)
def set_exact_amounts(ctx: ToolContext, args: SetExactAmountsIn) -> views.EntryOut:
    entry = day.set_exact_amounts(
        ctx.db, ctx.actor, args.entry_id, {a.component_id: a.amount for a in args.amounts}
    )
    return views.entry(entry, ctx.language, ctx.actor.user_id)


@tool(
    "move_entry",
    "Reorder my day: put an entry before another entry of mine, or last. Its time changes to "
    "fit between its new neighbours.",
    MoveEntryIn,
    writes=True,
)
def move_entry(ctx: ToolContext, args: MoveEntryIn) -> list[views.EntryOut]:
    moved = day.move_entry(ctx.db, ctx.actor, args.entry_id, before_id=args.before_id)
    return [views.entry(e, ctx.language, ctx.actor.user_id) for e in moved]


@tool(
    "add_recipe_to_list",
    "Put the ingredients of a recipe (for some portions) on the shopping list. Items already on "
    "the list are left alone and named in already_listed.",
    AddRecipeToListIn,
    writes=True,
)
def add_recipe_to_list(ctx: ToolContext, args: AddRecipeToListIn) -> views.AddedToListOut:
    result = recipes.add_to_list(
        ctx.db, ctx.actor, args.recipe_id, portions=args.portions, language=ctx.language
    )
    return views.added_to_list(result)


# --- offers ---------------------------------------------------------------------------------


@tool(
    "list_offers",
    "Offers of a planned meal between household members: the open ones to or from me, each with "
    "the meal and, for an offer to me, what accepting does to my day. include_closed adds the "
    "last two weeks' answered ones.",
    ListOffersIn,
    writes=False,
)
def list_offers(ctx: ToolContext, args: ListOffersIn) -> list[views.OfferOut]:
    found = offers.list_offers(ctx.db, ctx.actor, include_closed=args.include_closed)
    return [views.offer(v, ctx.language, ctx.actor.user_id) for v in found]


@tool(
    "send_offer",
    "Offer one of my planned meals to the other person for its day and slot. They get a "
    "notification. A new offer for the same slot replaces my pending one.",
    SendOfferIn,
    writes=True,
)
def send_offer(ctx: ToolContext, args: SendOfferIn) -> views.OfferOut:
    sent = offers.send(
        ctx.db,
        ctx.actor,
        entry_id=args.entry_id,
        to_user_id=_receiver(ctx, args.to_user_id),
        share=args.share,
    )
    return views.offer(sent, ctx.language, ctx.actor.user_id)


@tool(
    "respond_to_offer",
    "Answer an offer made to me: accept (the meal becomes joint and replaces my own plan for "
    "that slot), decline, or counter with one of my plans for the slot or a new meal.",
    RespondToOfferIn,
    writes=True,
)
def respond_to_offer(ctx: ToolContext, args: RespondToOfferIn) -> views.OfferOut:
    counter = None
    if args.counter_entry_id is not None or args.counter_meal is not None:
        meal = args.counter_meal
        counter = Counter(
            entry_id=args.counter_entry_id,
            meal=EntryInput(
                day=date.min,  # replaced by the offer's day and slot
                slot=Slot.DINNER,
                at=meal.time,
                name=meal.name,
                components=_components(meal.foods, meal.quick_add),
                recipe_id=meal.recipe_id,
                portions=meal.portions,
            )
            if meal
            else None,
        )
    answered = offers.respond(
        ctx.db, ctx.actor, args.offer_id, Action(args.action), counter=counter
    )
    return views.offer(answered, ctx.language, ctx.actor.user_id)


@tool("withdraw_offer", "Withdraw an offer I sent that is still pending.", OfferIdIn, writes=True)
def withdraw_offer(ctx: ToolContext, args: OfferIdIn) -> views.OfferOut:
    withdrawn = offers.withdraw(ctx.db, ctx.actor, args.offer_id)
    return views.offer(withdrawn, ctx.language, ctx.actor.user_id)
