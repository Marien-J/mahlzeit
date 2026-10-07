"""Request bodies → service inputs. Shared by the REST routes and the connector tools."""

from __future__ import annotations

from datetime import date

from mahlzeit.api import schemas
from mahlzeit.domain.catalogue import BaseUnit, Category, TrackingMode
from mahlzeit.domain.day import Slot
from mahlzeit.domain.nutrition import Nutrients
from mahlzeit.domain.recipes import RecipeKind
from mahlzeit.services.day import ComponentInput, EntryInput, EntryPatch
from mahlzeit.services.items import ItemInput
from mahlzeit.services.offers import Counter
from mahlzeit.services.recipes import UNSET, Ingredient, RecipeInput, RecipePatch
from mahlzeit.services.shopping import Op
from mahlzeit.services.stock import LineInput, PurchaseInput


def item_input(body: schemas.ItemIn) -> ItemInput:
    return ItemInput(
        names={str(k): v for k, v in body.names.items()},
        brand=body.brand,
        category=Category(body.category),
        base_unit=BaseUnit(body.base_unit),
        nutrients=Nutrients(**body.nutrients.model_dump()),
        package_size=body.package_size,
        servings=[(s.label, s.amount) for s in body.servings],
        barcodes=list(body.barcodes),
        tracking_mode=TrackingMode(body.tracking_mode),
        image_url=body.image_url,
    )


def component(c: schemas.ComponentIn) -> ComponentInput:
    return ComponentInput(**c.model_dump())


def entry_input(body: schemas.EntryIn) -> EntryInput:
    return EntryInput(
        day=body.day,
        slot=Slot(body.slot),
        at=body.at,
        name=body.name,
        eaten_out=body.eaten_out,
        components=[component(c) for c in body.components],
        recipe_id=body.recipe_id,
        portions=body.portions,
        cooked_grams=body.cooked_grams,
        plan=body.plan,
        joint=body.joint,
    )


def entry_patch(body: schemas.EntryPatchIn) -> EntryPatch:
    return EntryPatch(
        day=body.day,
        slot=Slot(body.slot) if body.slot else None,
        at=body.at,
        name=body.name,
        eaten_out=body.eaten_out,
        components=[component(c) for c in body.components] if body.components is not None else None,
    )


def list_op(o: schemas.ListOpIn) -> Op:
    return Op(kind=o.kind, id=o.id, at=o.at, fields=o.fields.model_dump(exclude_unset=True))


def recipe_input(body: schemas.RecipeIn) -> RecipeInput:
    return RecipeInput(
        name=body.name,
        kind=RecipeKind(body.kind),
        servings=body.servings,
        cooked_yield_g=body.cooked_yield_g,
        staple=body.staple,
        notes=body.notes,
        ingredients=[Ingredient(i.item_id, i.amount) for i in body.ingredients],
    )


def recipe_patch(body: schemas.RecipePatchIn) -> RecipePatch:
    sent = body.model_fields_set
    return RecipePatch(
        name=body.name,
        servings=body.servings,
        cooked_yield_g=body.cooked_yield_g if "cooked_yield_g" in sent else UNSET,
        staple=body.staple,
        notes=body.notes if "notes" in sent else UNSET,
        ingredients=[Ingredient(i.item_id, i.amount) for i in body.ingredients]
        if body.ingredients is not None
        else None,
    )


def counter(body: schemas.OfferResponseIn) -> Counter | None:
    """The meal sent back with a counter-offer. Its day and slot come from the offer."""
    if body.counter_meal is None:
        return Counter(entry_id=body.counter_entry_id) if body.counter_entry_id else None
    meal = body.counter_meal
    return Counter(
        entry_id=body.counter_entry_id,
        meal=EntryInput(
            day=date.min,  # replaced by the offer's day and slot
            slot=Slot.DINNER,
            at=meal.at,
            name=meal.name,
            components=[component(c) for c in meal.components],
            recipe_id=meal.recipe_id,
            portions=meal.portions,
            cooked_grams=meal.cooked_grams,
        ),
    )


def purchase_input(body: schemas.PurchaseIn) -> PurchaseInput:
    return PurchaseInput(
        id=body.id,
        store_id=body.store_id,
        day=body.day,
        lines=[LineInput(**line.model_dump()) for line in body.lines],
    )
