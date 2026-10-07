"""Day tools: get_day, get_household_snapshot, log_food, log_planned_meal, update_entry,
delete_entry, copy_meals, get_targets, set_targets, set_day_type, and the recipe tools
list_recipes, get_recipe, create_recipe, update_recipe, delete_recipe (recipes and saved meals)."""

from __future__ import annotations

import datetime as dt
import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from mahlzeit import views
from mahlzeit.domain.day import EntryState, Slot
from mahlzeit.domain.errors import Invalid
from mahlzeit.domain.recipes import RecipeKind
from mahlzeit.domain.targets import DayType, Targets
from mahlzeit.services import day, recipes, snapshot, targets
from mahlzeit.services.day import ComponentInput, EntryInput, EntryPatch
from mahlzeit.services.recipes import UNSET, Ingredient, RecipeInput, RecipePatch
from mahlzeit.tools.registry import ToolContext, tool

SlotName = Literal["breakfast", "lunch", "dinner", "snack"]


class FoodIn(BaseModel):
    item_id: uuid.UUID = Field(description="From search_items.")
    amount: float | None = Field(default=None, description="Grams, or millilitres for ml items.")
    serving: str | None = Field(
        default=None, description="A serving label of the item, e.g. 'egg'."
    )
    servings: float | None = Field(
        default=None, description="How many of that serving (default 1)."
    )


class QuickAddIn(BaseModel):
    name: str = Field(max_length=120)
    kcal: float
    protein: float | None = None
    carbs: float | None = None
    fat: float | None = None


def _components(foods: list[FoodIn], quick: list[QuickAddIn]) -> list[ComponentInput]:
    return [
        ComponentInput(
            item_id=f.item_id, amount=f.amount, serving_label=f.serving, serving_count=f.servings
        )
        for f in foods
    ] + [
        ComponentInput(quick_name=q.name, kcal=q.kcal, protein=q.protein, carbs=q.carbs, fat=q.fat)
        for q in quick
    ]


class DayIn(BaseModel):
    day: date | None = Field(default=None, description="ISO date; today when omitted.")


class EmptyIn(BaseModel):
    pass


class LogFoodIn(BaseModel):
    day: date | None = Field(
        default=None, description="ISO date; today when omitted. Future dates are planned."
    )
    slot: SlotName
    time: dt.time | None = Field(
        default=None, description="HH:MM; defaults to 08:00, 12:30, 19:00, or now for snacks."
    )
    name: str | None = Field(
        default=None, max_length=120, description="Optional name such as 'Porridge'."
    )
    eaten_out: bool = Field(
        default=False, description="Eaten at a restaurant or elsewhere (no stock change)."
    )
    foods: list[FoodIn] = Field(default_factory=list, max_length=50)
    quick_add: list[QuickAddIn] = Field(
        default_factory=list,
        max_length=20,
        description="Foods without a catalogue item: name and kcal, macros optional.",
    )
    recipe_id: uuid.UUID | None = Field(
        default=None, description="A recipe or saved meal, from list_recipes."
    )
    portions: float = Field(default=1.0, description="Portions of the recipe.")
    cooked_grams: float | None = Field(
        default=None,
        description="A portion weighed after cooking (needs the recipe's cooked yield); "
        "used instead of portions.",
    )
    joint: bool = Field(
        default=False,
        description="Also for the rest of the household, half and half. Everyone logs it.",
    )


class EntryIdIn(BaseModel):
    entry_id: uuid.UUID


class UpdateEntryIn(BaseModel):
    entry_id: uuid.UUID
    day: date | None = None
    slot: SlotName | None = None
    time: dt.time | None = None
    name: str | None = Field(default=None, max_length=120)
    eaten_out: bool | None = None
    foods: list[FoodIn] | None = Field(
        default=None, description="Replaces all foods of the entry when given."
    )
    quick_add: list[QuickAddIn] | None = None


class CopyMealsIn(BaseModel):
    entry_id: uuid.UUID | None = Field(
        default=None, description="Copy one entry (own or the partner's)."
    )
    source_day: date | None = Field(
        default=None, description="Or copy all of the person's entries of a day."
    )
    day: date | None = Field(default=None, description="Target day; today when omitted.")
    slot: SlotName | None = Field(default=None, description="Target slot for a single entry.")

    @model_validator(mode="after")
    def one_source(self) -> CopyMealsIn:
        if (self.entry_id is None) == (self.source_day is None):
            raise ValueError("give exactly one of entry_id or source_day")
        return self


class SetTargetsIn(BaseModel):
    kcal: float | None = None
    protein: float | None = None
    carbs: float | None = None
    fat: float | None = None
    day_types: list[Literal["training", "rest"]] = Field(default=["training", "rest"], min_length=1)
    valid_from: date | None = Field(
        default=None, description="Today when omitted; earlier days keep their targets."
    )
    week_pattern: str | None = Field(
        default=None, description="Seven letters T or R, Monday first, e.g. 'TRTRTRR'."
    )


class SetDayTypeIn(BaseModel):
    day: date | None = None
    day_type: Literal["training", "rest"] | None = Field(
        description="None returns to the weekly pattern."
    )


class IngredientIn(BaseModel):
    item_id: uuid.UUID
    amount: float = Field(description="Grams or millilitres.")


class RecipeIdIn(BaseModel):
    recipe_id: uuid.UUID


# --- day ------------------------------------------------------------------------------------


@tool(
    "get_day",
    "Both household members' day: entries in time order with foods, what each logged and "
    "planned, targets, what is left, and the projection if everything planned is eaten.",
    DayIn,
    writes=False,
)
def get_day(ctx: ToolContext, args: DayIn) -> views.DayOut:
    result = day.get_day(ctx.db, ctx.actor, args.day or ctx.today)
    return views.day(result, ctx.language, ctx.actor.user_id)


@tool(
    "get_household_snapshot",
    "Everything for 'what should we cook tonight' in one call: both people's remaining macros "
    "today, tonight's dinner plans, open offers, the shopping list, and (in later versions) "
    "stock.",
    EmptyIn,
    writes=False,
)
def get_household_snapshot(ctx: ToolContext, args: EmptyIn) -> views.SnapshotOut:
    return views.snapshot(
        snapshot.household_snapshot(ctx.db, ctx.actor), ctx.language, ctx.actor.user_id
    )


@tool(
    "log_food",
    "Log a meal for the signed-in person: catalogue foods with amounts or servings, quick-add "
    "foods, or a recipe. Past and today are logged; future days are planned (use plan_meal to "
    "plan today).",
    LogFoodIn,
    writes=True,
)
def log_food(ctx: ToolContext, args: LogFoodIn) -> views.EntryOut:
    entry = day.log_food(
        ctx.db,
        ctx.actor,
        EntryInput(
            day=args.day or ctx.today,
            slot=Slot(args.slot),
            at=args.time,
            name=args.name,
            eaten_out=args.eaten_out,
            components=_components(args.foods, args.quick_add),
            recipe_id=args.recipe_id,
            portions=args.portions,
            cooked_grams=args.cooked_grams,
            joint=args.joint,
        ),
    )
    return views.entry(entry, ctx.language, ctx.actor.user_id)


@tool(
    "log_planned_meal",
    "Mark one of the person's planned entries as eaten. On a joint meal everyone's planned part "
    "is logged.",
    EntryIdIn,
    writes=True,
)
def log_planned_meal(ctx: ToolContext, args: EntryIdIn) -> views.EntryOut:
    entry = day.set_state(ctx.db, ctx.actor, args.entry_id, EntryState.LOGGED)
    return views.entry(entry, ctx.language, ctx.actor.user_id)


@tool(
    "update_entry",
    "Change one of the person's entries: day, slot, time, name, eaten out, or replace its foods.",
    UpdateEntryIn,
    writes=True,
)
def update_entry(ctx: ToolContext, args: UpdateEntryIn) -> views.EntryOut:
    components = None
    if args.foods is not None or args.quick_add is not None:
        components = _components(args.foods or [], args.quick_add or [])
    patch = EntryPatch(
        day=args.day,
        slot=Slot(args.slot) if args.slot else None,
        at=args.time,
        name=args.name,
        eaten_out=args.eaten_out,
        components=components,
    )
    entry = day.update_entry(ctx.db, ctx.actor, args.entry_id, patch)
    return views.entry(entry, ctx.language, ctx.actor.user_id)


@tool("delete_entry", "Remove one of the person's entries.", EntryIdIn, writes=True)
def delete_entry(ctx: ToolContext, args: EntryIdIn) -> dict[str, bool]:
    day.delete_entry(ctx.db, ctx.actor, args.entry_id)
    return {"ok": True}


@tool(
    "copy_meals",
    "Repeat an earlier entry, or all of the person's entries of an earlier day, on another day.",
    CopyMealsIn,
    writes=True,
)
def copy_meals(ctx: ToolContext, args: CopyMealsIn) -> list[views.EntryOut]:
    target = args.day or ctx.today
    if args.entry_id is not None:
        entries = [
            day.copy_entry(
                ctx.db,
                ctx.actor,
                args.entry_id,
                day=target,
                slot=Slot(args.slot) if args.slot else None,
            )
        ]
    else:
        assert args.source_day is not None
        entries = day.copy_day(ctx.db, ctx.actor, source_day=args.source_day, day=target)
    return [views.entry(e, ctx.language, ctx.actor.user_id) for e in entries]


# --- targets --------------------------------------------------------------------------------


@tool(
    "get_targets", "The person's target history and weekly training pattern.", EmptyIn, writes=False
)
def get_targets(ctx: ToolContext, args: EmptyIn) -> views.TargetPlanOut:
    return views.target_plan(targets.plan(ctx.db, ctx.actor.user_id))


@tool(
    "set_targets",
    "Set daily targets (kcal, protein, carbs, fat; all optional) for training and/or rest days "
    "from a date on, and optionally the weekly training pattern.",
    SetTargetsIn,
    writes=True,
)
def set_targets(ctx: ToolContext, args: SetTargetsIn) -> views.TargetPlanOut:
    if args.week_pattern is not None:
        targets.set_week_pattern(ctx.db, ctx.actor, args.week_pattern)
    if any(v is not None for v in (args.kcal, args.protein, args.carbs, args.fat)):
        targets.set_targets(
            ctx.db,
            ctx.actor,
            targets=Targets(kcal=args.kcal, protein=args.protein, carbs=args.carbs, fat=args.fat),
            day_types=[DayType(d) for d in args.day_types],
            valid_from=args.valid_from,
        )
    elif args.week_pattern is None:
        raise Invalid("nothing_to_set")
    return views.target_plan(targets.plan(ctx.db, ctx.actor.user_id))


@tool(
    "set_day_type",
    "Make a day a training or rest day, or return it to the weekly pattern.",
    SetDayTypeIn,
    writes=True,
)
def set_day_type(ctx: ToolContext, args: SetDayTypeIn) -> dict[str, bool]:
    targets.set_day_type(
        ctx.db, ctx.actor, args.day or ctx.today, DayType(args.day_type) if args.day_type else None
    )
    return {"ok": True}


# --- recipes and saved meals -----------------------------------------------------------------


class ListRecipesIn(BaseModel):
    kind: Literal["recipe", "saved_meal"] | None = Field(
        default=None, description="Only recipes, or only saved meals (one-serving, for logging)."
    )
    staples_only: bool = Field(default=False, description="Only recipes marked as staples.")


class CreateRecipeIn(BaseModel):
    name: str = Field(max_length=120)
    kind: Literal["recipe", "saved_meal"] = Field(
        default="recipe", description="A saved meal is a one-serving recipe for one-tap logging."
    )
    servings: float = Field(default=1, description="How many servings the ingredients make.")
    cooked_yield_g: float | None = Field(
        default=None, description="Weight of the whole dish after cooking, to log by cooked weight."
    )
    staple: bool = Field(default=False, description="A recipe the household cooks regularly.")
    notes: str | None = Field(default=None, max_length=4000)
    ingredients: list[IngredientIn] = Field(default_factory=list, max_length=50)
    from_entry_id: uuid.UUID | None = Field(
        default=None, description="Save the foods of an entry as a saved meal instead."
    )


class UpdateRecipeIn(BaseModel):
    recipe_id: uuid.UUID
    name: str | None = Field(default=None, max_length=120)
    servings: float | None = None
    cooked_yield_g: float | None = Field(default=None, description="null clears it.")
    staple: bool | None = None
    notes: str | None = Field(default=None, max_length=4000, description="null clears it.")
    ingredients: list[IngredientIn] | None = Field(
        default=None, description="Replaces all ingredients when given."
    )


@tool(
    "list_recipes",
    "The household's recipes and saved meals with ingredients and nutrition per serving "
    "(staples first). Use the ids with plan_meal, log_food and add_recipe_to_list.",
    ListRecipesIn,
    writes=False,
)
def list_recipes(ctx: ToolContext, args: ListRecipesIn) -> list[views.RecipeOut]:
    found = recipes.list_all(
        ctx.db,
        ctx.actor,
        kind=RecipeKind(args.kind) if args.kind else None,
        staples_only=args.staples_only,
    )
    return [views.recipe(r, ctx.language) for r in found]


@tool(
    "get_recipe",
    "One recipe or saved meal with its ingredients, notes and nutrition per serving (and per "
    "100 g cooked when it has a cooked yield).",
    RecipeIdIn,
    writes=False,
)
def get_recipe(ctx: ToolContext, args: RecipeIdIn) -> views.RecipeOut:
    return views.recipe(recipes.get(ctx.db, ctx.actor, args.recipe_id), ctx.language)


@tool(
    "create_recipe",
    "Create a recipe (servings, optional cooked yield, staple flag, notes, catalogue "
    "ingredients), or a one-serving saved meal, or save the foods of an entry as a saved meal.",
    CreateRecipeIn,
    writes=True,
)
def create_recipe(ctx: ToolContext, args: CreateRecipeIn) -> views.RecipeOut:
    if args.from_entry_id is not None:
        recipe = recipes.create_from_entry(ctx.db, ctx.actor, args.from_entry_id, name=args.name)
    else:
        recipe = recipes.create(
            ctx.db,
            ctx.actor,
            RecipeInput(
                name=args.name,
                kind=RecipeKind(args.kind),
                servings=args.servings,
                cooked_yield_g=args.cooked_yield_g,
                staple=args.staple,
                notes=args.notes,
                ingredients=[Ingredient(i.item_id, i.amount) for i in args.ingredients],
            ),
        )
    return views.recipe(recipe, ctx.language)


@tool(
    "update_recipe",
    "Change a recipe: name, servings, cooked yield, staple flag, notes, or replace its "
    "ingredients. Entries made from it earlier keep their own foods.",
    UpdateRecipeIn,
    writes=True,
)
def update_recipe(ctx: ToolContext, args: UpdateRecipeIn) -> views.RecipeOut:
    sent = args.model_fields_set
    recipe = recipes.update(
        ctx.db,
        ctx.actor,
        args.recipe_id,
        RecipePatch(
            name=args.name,
            servings=args.servings,
            cooked_yield_g=args.cooked_yield_g if "cooked_yield_g" in sent else UNSET,
            staple=args.staple,
            notes=args.notes if "notes" in sent else UNSET,
            ingredients=[Ingredient(i.item_id, i.amount) for i in args.ingredients]
            if args.ingredients is not None
            else None,
        ),
    )
    return views.recipe(recipe, ctx.language)


@tool(
    "delete_recipe",
    "Delete a recipe or saved meal. Entries logged from it stay as they are.",
    RecipeIdIn,
    writes=True,
)
def delete_recipe(ctx: ToolContext, args: RecipeIdIn) -> dict[str, bool]:
    recipes.delete(ctx.db, ctx.actor, args.recipe_id)
    return {"ok": True}
