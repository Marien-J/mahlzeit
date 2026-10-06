from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from mahlzeit import views
from mahlzeit.api.deps import Current, CurrentWrite, Db
from mahlzeit.api.schemas import SaveAsMealIn, SavedMealIn, SavedMealPatchIn
from mahlzeit.services import saved_meals
from mahlzeit.services.saved_meals import Ingredient

router = APIRouter(tags=["saved meals"])


@router.get("/saved-meals", response_model=list[views.SavedMealOut])
def list_saved_meals(current: Current, db: Db) -> list[views.SavedMealOut]:
    return [
        views.saved_meal(r, current.user.language) for r in saved_meals.list_all(db, current.actor)
    ]


@router.post("/saved-meals", response_model=views.SavedMealOut, status_code=status.HTTP_201_CREATED)
def create_saved_meal(body: SavedMealIn, current: CurrentWrite, db: Db) -> views.SavedMealOut:
    recipe = saved_meals.create(
        db,
        current.actor,
        name=body.name,
        ingredients=[Ingredient(i.item_id, i.amount) for i in body.ingredients],
    )
    return views.saved_meal(recipe, current.user.language)


@router.post(
    "/entries/{entry_id}/save-as-meal",
    response_model=views.SavedMealOut,
    status_code=status.HTTP_201_CREATED,
)
def save_entry_as_meal(
    entry_id: uuid.UUID, body: SaveAsMealIn, current: CurrentWrite, db: Db
) -> views.SavedMealOut:
    recipe = saved_meals.create_from_entry(db, current.actor, entry_id, name=body.name)
    return views.saved_meal(recipe, current.user.language)


@router.patch("/saved-meals/{meal_id}", response_model=views.SavedMealOut)
def update_saved_meal(
    meal_id: uuid.UUID, body: SavedMealPatchIn, current: CurrentWrite, db: Db
) -> views.SavedMealOut:
    ingredients = (
        [Ingredient(i.item_id, i.amount) for i in body.ingredients]
        if body.ingredients is not None
        else None
    )
    recipe = saved_meals.update(db, current.actor, meal_id, name=body.name, ingredients=ingredients)
    return views.saved_meal(recipe, current.user.language)


@router.delete("/saved-meals/{meal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_meal(meal_id: uuid.UUID, current: CurrentWrite, db: Db) -> None:
    saved_meals.delete(db, current.actor, meal_id)
