from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, status

from mahlzeit import views
from mahlzeit.api import convert
from mahlzeit.api.deps import Current, CurrentWrite, Db
from mahlzeit.api.schemas import AddToListIn, RecipeIn, RecipePatchIn, SaveAsMealIn
from mahlzeit.domain.recipes import RecipeKind
from mahlzeit.services import recipes

router = APIRouter(tags=["recipes"])


@router.get("/recipes", response_model=list[views.RecipeOut])
def list_recipes(
    current: Current,
    db: Db,
    kind: Literal["recipe", "saved_meal"] | None = None,
    staples_only: bool = False,
) -> list[views.RecipeOut]:
    found = recipes.list_all(
        db, current.actor, kind=RecipeKind(kind) if kind else None, staples_only=staples_only
    )
    return [views.recipe(r, current.user.language) for r in found]


@router.post("/recipes", response_model=views.RecipeOut, status_code=status.HTTP_201_CREATED)
def create_recipe(body: RecipeIn, current: CurrentWrite, db: Db) -> views.RecipeOut:
    recipe = recipes.create(db, current.actor, convert.recipe_input(body))
    return views.recipe(recipe, current.user.language)


@router.get("/recipes/{recipe_id}", response_model=views.RecipeOut)
def get_recipe(recipe_id: uuid.UUID, current: Current, db: Db) -> views.RecipeOut:
    return views.recipe(recipes.get(db, current.actor, recipe_id), current.user.language)


@router.patch("/recipes/{recipe_id}", response_model=views.RecipeOut)
def update_recipe(
    recipe_id: uuid.UUID, body: RecipePatchIn, current: CurrentWrite, db: Db
) -> views.RecipeOut:
    recipe = recipes.update(db, current.actor, recipe_id, convert.recipe_patch(body))
    return views.recipe(recipe, current.user.language)


@router.delete("/recipes/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe(recipe_id: uuid.UUID, current: CurrentWrite, db: Db) -> None:
    recipes.delete(db, current.actor, recipe_id)


@router.post("/recipes/{recipe_id}/add-to-list", response_model=views.AddedToListOut)
def add_to_list(
    recipe_id: uuid.UUID, body: AddToListIn, current: CurrentWrite, db: Db
) -> views.AddedToListOut:
    result = recipes.add_to_list(
        db, current.actor, recipe_id, portions=body.portions, language=current.user.language
    )
    return views.added_to_list(result)


@router.post(
    "/entries/{entry_id}/save-as-meal",
    response_model=views.RecipeOut,
    status_code=status.HTTP_201_CREATED,
)
def save_entry_as_meal(
    entry_id: uuid.UUID, body: SaveAsMealIn, current: CurrentWrite, db: Db
) -> views.RecipeOut:
    recipe = recipes.create_from_entry(db, current.actor, entry_id, name=body.name)
    return views.recipe(recipe, current.user.language)
