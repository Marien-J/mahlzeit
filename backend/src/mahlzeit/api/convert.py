"""Request bodies → service inputs. Shared by the REST routes and the connector tools."""

from __future__ import annotations

from mahlzeit.api import schemas
from mahlzeit.domain.catalogue import BaseUnit, Category, TrackingMode
from mahlzeit.domain.day import Slot
from mahlzeit.domain.nutrition import Nutrients
from mahlzeit.services.day import ComponentInput, EntryInput, EntryPatch
from mahlzeit.services.items import ItemInput
from mahlzeit.services.shopping import Op


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
        saved_meal_id=body.saved_meal_id,
        portions=body.portions,
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
