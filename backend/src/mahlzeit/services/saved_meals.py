"""Saved meals: one-serving recipes for one-tap logging, such as a usual breakfast.

Full recipes (several servings, cooked yield, planning) arrive in M3 on the same table.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from mahlzeit import clock
from mahlzeit.domain import day as day_rules
from mahlzeit.domain.errors import Invalid, NotFound
from mahlzeit.domain.nutrition import Totals, per_serving, total
from mahlzeit.domain.permissions import Actor, require_household
from mahlzeit.models import Recipe, RecipeIngredient
from mahlzeit.services import audit, items
from mahlzeit.services.day import get_entry

KIND = "saved_meal"


@dataclass(frozen=True)
class Ingredient:
    item_id: uuid.UUID
    amount: float


def _load(db: Session, recipe_id: uuid.UUID) -> Recipe | None:
    return db.scalars(
        select(Recipe)
        .where(Recipe.id == recipe_id)
        .options(selectinload(Recipe.ingredients).selectinload(RecipeIngredient.item))
    ).first()


def get(db: Session, actor: Actor, recipe_id: uuid.UUID) -> Recipe:
    recipe = _load(db, recipe_id)
    if recipe is None or recipe.kind != KIND:
        raise NotFound("saved_meal_not_found")
    require_household(actor, recipe.household_id)
    return recipe


def nutrition(recipe: Recipe) -> Totals:
    dish = total(items.nutrients_of(i.item).scaled(i.amount) for i in recipe.ingredients)
    return Totals(per_serving(dish.values, servings=recipe.servings), dish.incomplete)


def list_all(db: Session, actor: Actor) -> list[Recipe]:
    return list(
        db.scalars(
            select(Recipe)
            .where(Recipe.household_id == actor.household_id, Recipe.kind == KIND)
            .order_by(Recipe.name)
            .options(selectinload(Recipe.ingredients).selectinload(RecipeIngredient.item))
        )
    )


def _ingredients(db: Session, actor: Actor, given: list[Ingredient]) -> list[RecipeIngredient]:
    if not given:
        raise Invalid("saved_meal_empty")
    result = []
    for pos, ing in enumerate(given):
        item = items.get(db, actor, ing.item_id)
        result.append(
            RecipeIngredient(
                item_id=item.id, item=item, amount=day_rules.check_amount(ing.amount), position=pos
            )
        )
    return result


def _name(name: str) -> str:
    cleaned = name.strip()[:120]
    if not cleaned:
        raise Invalid("saved_meal_name_required")
    return cleaned


def create(db: Session, actor: Actor, *, name: str, ingredients: list[Ingredient]) -> Recipe:
    recipe = Recipe(
        household_id=actor.household_id,
        kind=KIND,
        name=_name(name),
        servings=1,
        created_by=actor.user_id,
        ingredients=_ingredients(db, actor, ingredients),
    )
    db.add(recipe)
    db.flush()
    audit.record(
        db,
        actor=actor,
        entity="saved_meal",
        entity_id=recipe.id,
        action="created",
        after={"name": recipe.name, "ingredients": len(ingredients)},
    )
    db.commit()
    return get(db, actor, recipe.id)


def create_from_entry(
    db: Session, actor: Actor, entry_id: uuid.UUID, *, name: str | None = None
) -> Recipe:
    """Save what was in a logged entry. Quick-adds have no item, so they are left out."""
    entry = get_entry(db, actor, entry_id)
    ingredients = [
        Ingredient(c.item_id, c.amount)
        for c in entry.components
        if c.item_id is not None and c.amount is not None
    ]
    return create(db, actor, name=name or entry.name or "", ingredients=ingredients)


def update(
    db: Session,
    actor: Actor,
    recipe_id: uuid.UUID,
    *,
    name: str | None = None,
    ingredients: list[Ingredient] | None = None,
) -> Recipe:
    recipe = get(db, actor, recipe_id)
    before = {"name": recipe.name, "ingredients": len(recipe.ingredients)}
    if name is not None:
        recipe.name = _name(name)
    if ingredients is not None:
        recipe.ingredients = _ingredients(db, actor, ingredients)
    recipe.updated_at = clock.now()
    audit.record(
        db,
        actor=actor,
        entity="saved_meal",
        entity_id=recipe.id,
        action="updated",
        before=before,
        after={"name": recipe.name, "ingredients": len(recipe.ingredients)},
    )
    db.commit()
    return get(db, actor, recipe.id)


def delete(db: Session, actor: Actor, recipe_id: uuid.UUID) -> None:
    recipe = get(db, actor, recipe_id)
    audit.record(
        db,
        actor=actor,
        entity="saved_meal",
        entity_id=recipe.id,
        action="deleted",
        before={"name": recipe.name},
    )
    db.delete(recipe)
    db.commit()
