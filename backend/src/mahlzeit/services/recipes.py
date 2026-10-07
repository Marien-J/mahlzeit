"""Recipes and saved meals: ingredients from the catalogue, nutrition computed from them.

A saved meal is a one-serving recipe for one-tap logging (kind `saved_meal`); a recipe has
servings, an optional cooked yield and can be marked as a staple for planning. Both live in one
table and use the same service.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from mahlzeit import clock
from mahlzeit.domain import day as day_rules
from mahlzeit.domain import recipes as rules
from mahlzeit.domain.errors import Invalid, NotFound
from mahlzeit.domain.nutrition import Nutrients, Totals, per_cooked_gram, per_serving, total
from mahlzeit.domain.permissions import Actor, require_household
from mahlzeit.domain.recipes import RecipeKind
from mahlzeit.ids import uuid7
from mahlzeit.models import Recipe, RecipeIngredient, ShoppingListItem
from mahlzeit.services import audit, items, shopping
from mahlzeit.services.day import get_entry

ENTITY = "recipe"


class _Unset(Enum):
    UNSET = 0


UNSET = _Unset.UNSET
"""Marks a field that was not sent, as opposed to sent as null (which clears it)."""


@dataclass(frozen=True)
class Ingredient:
    item_id: uuid.UUID
    amount: float


@dataclass
class RecipeInput:
    name: str
    kind: RecipeKind = RecipeKind.RECIPE
    servings: float = 1.0
    cooked_yield_g: float | None = None
    staple: bool = False
    notes: str | None = None
    ingredients: list[Ingredient] = field(default_factory=list)


@dataclass
class RecipePatch:
    name: str | None = None
    servings: float | None = None
    cooked_yield_g: float | _Unset | None = UNSET
    staple: bool | None = None
    notes: str | _Unset | None = UNSET
    ingredients: list[Ingredient] | None = None


@dataclass(frozen=True)
class AddedToList:
    added: list[ShoppingListItem]
    already_listed: list[str]


# --- reading ----------------------------------------------------------------------------------


def _load(db: Session, recipe_id: uuid.UUID) -> Recipe | None:
    return db.scalars(
        select(Recipe)
        .where(Recipe.id == recipe_id)
        .options(selectinload(Recipe.ingredients).selectinload(RecipeIngredient.item))
    ).first()


def get(db: Session, actor: Actor, recipe_id: uuid.UUID) -> Recipe:
    recipe = _load(db, recipe_id)
    if recipe is None:
        raise NotFound("recipe_not_found")
    require_household(actor, recipe.household_id)
    return recipe


def list_all(
    db: Session, actor: Actor, *, kind: RecipeKind | None = None, staples_only: bool = False
) -> list[Recipe]:
    """Staples first, then by name."""
    query = select(Recipe).where(Recipe.household_id == actor.household_id)
    if kind is not None:
        query = query.where(Recipe.kind == kind.value)
    if staples_only:
        query = query.where(Recipe.staple.is_(True))
    return list(
        db.scalars(
            query.order_by(Recipe.staple.desc(), Recipe.name).options(
                selectinload(Recipe.ingredients).selectinload(RecipeIngredient.item)
            )
        )
    )


def dish_nutrition(recipe: Recipe) -> Totals:
    return total(items.nutrients_of(i.item).scaled(i.amount) for i in recipe.ingredients)


def nutrition(recipe: Recipe) -> Totals:
    """Per serving."""
    dish = dish_nutrition(recipe)
    return Totals(per_serving(dish.values, servings=recipe.servings), dish.incomplete)


def nutrition_per_100g_cooked(recipe: Recipe) -> Nutrients | None:
    if recipe.cooked_yield_g is None:
        return None
    return per_cooked_gram(dish_nutrition(recipe).values, cooked_yield_g=recipe.cooked_yield_g)


# --- writing ----------------------------------------------------------------------------------


def _ingredients(db: Session, actor: Actor, given: list[Ingredient]) -> list[RecipeIngredient]:
    if not given:
        raise Invalid("recipe_empty")
    result = []
    for pos, ing in enumerate(given):
        item = items.get(db, actor, ing.item_id)
        result.append(
            RecipeIngredient(
                item_id=item.id, item=item, amount=day_rules.check_amount(ing.amount), position=pos
            )
        )
    return result


def _snapshot(recipe: Recipe) -> dict[str, Any]:
    return {
        "name": recipe.name,
        "kind": recipe.kind,
        "servings": recipe.servings,
        "cooked_yield_g": recipe.cooked_yield_g,
        "staple": recipe.staple,
        "ingredients": len(recipe.ingredients),
    }


def create(db: Session, actor: Actor, data: RecipeInput) -> Recipe:
    kind = RecipeKind(data.kind)
    recipe = Recipe(
        household_id=actor.household_id,
        kind=kind.value,
        name=rules.check_name(data.name),
        servings=rules.check_servings(kind, data.servings),
        cooked_yield_g=rules.check_cooked_yield(data.cooked_yield_g),
        staple=data.staple,
        notes=rules.check_notes(data.notes),
        created_by=actor.user_id,
        ingredients=_ingredients(db, actor, data.ingredients),
    )
    db.add(recipe)
    db.flush()
    audit.record(
        db,
        actor=actor,
        entity=ENTITY,
        entity_id=recipe.id,
        action="created",
        after=_snapshot(recipe),
    )
    db.commit()
    return get(db, actor, recipe.id)


def create_from_entry(
    db: Session, actor: Actor, entry_id: uuid.UUID, *, name: str | None = None
) -> Recipe:
    """Save what was in an entry as a saved meal. Quick-adds have no item, so they are left out."""
    entry = get_entry(db, actor, entry_id)
    ingredients = [
        Ingredient(c.item_id, c.amount)
        for c in entry.components
        if c.item_id is not None and c.amount is not None
    ]
    return create(
        db,
        actor,
        RecipeInput(
            name=name or entry.name or "", kind=RecipeKind.SAVED_MEAL, ingredients=ingredients
        ),
    )


def update(db: Session, actor: Actor, recipe_id: uuid.UUID, patch: RecipePatch) -> Recipe:
    recipe = get(db, actor, recipe_id)
    kind = RecipeKind(recipe.kind)
    before = _snapshot(recipe)
    if patch.name is not None:
        recipe.name = rules.check_name(patch.name)
    if patch.servings is not None:
        recipe.servings = rules.check_servings(kind, patch.servings)
    if patch.cooked_yield_g is not UNSET:
        assert not isinstance(patch.cooked_yield_g, _Unset)
        recipe.cooked_yield_g = rules.check_cooked_yield(patch.cooked_yield_g)
    if patch.staple is not None:
        recipe.staple = patch.staple
    if patch.notes is not UNSET:
        assert not isinstance(patch.notes, _Unset)
        recipe.notes = rules.check_notes(patch.notes)
    if patch.ingredients is not None:
        recipe.ingredients = _ingredients(db, actor, patch.ingredients)
    recipe.updated_at = clock.now()
    audit.record(
        db,
        actor=actor,
        entity=ENTITY,
        entity_id=recipe.id,
        action="updated",
        before=before,
        after=_snapshot(recipe),
    )
    db.commit()
    return get(db, actor, recipe.id)


def delete(db: Session, actor: Actor, recipe_id: uuid.UUID) -> None:
    """Entries made from it stay as they are: they hold their own copy of the foods."""
    recipe = get(db, actor, recipe_id)
    audit.record(
        db,
        actor=actor,
        entity=ENTITY,
        entity_id=recipe.id,
        action="deleted",
        before=_snapshot(recipe),
    )
    db.delete(recipe)
    db.commit()


def add_to_list(
    db: Session,
    actor: Actor,
    recipe_id: uuid.UUID,
    *,
    portions: float | None = None,
    language: str = "de",
) -> AddedToList:
    """Put the ingredients for `portions` (default: the whole recipe) on the shopping list.

    Without stock (M4) 'missing' means not on the list yet: an item that is already there, ticked
    or not, is left alone and reported."""
    recipe = get(db, actor, recipe_id)
    wanted = rules.check_portions(portions if portions is not None else recipe.servings)
    amounts = rules.combine(
        rules.scale(
            [(i.item_id, i.amount) for i in recipe.ingredients],
            servings=recipe.servings,
            portions=wanted,
        )
    )
    by_item = {i.item_id: i.item for i in recipe.ingredients}
    on_list = {r.item_id for r in shopping.open_items(db, actor) if r.item_id is not None}
    ops: list[shopping.Op] = []
    already: list[str] = []
    for item_id, amount in amounts:
        item = by_item[item_id]
        if item_id in on_list:
            already.append(items.name_of(item, language))
            continue
        ops.append(
            shopping.Op(
                "add",
                uuid7(),
                fields={
                    "item_id": item_id,
                    "quantity": rules.quantity_text(amount, item.base_unit, language),
                },
            )
        )
    shopping.apply(db, actor, ops, language=language, origin="recipe")
    added = [shopping.get_row(db, actor, op.id) for op in ops]
    return AddedToList(added=added, already_listed=already)
