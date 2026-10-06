"""Generic foods: global, read-only items loaded from the curated BLS seed."""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from mahlzeit import clock
from mahlzeit.models import Item, ServingSize
from mahlzeit.services.items import search_text_for


@cache
def generic_foods() -> list[dict[str, Any]]:
    data = resources.files("mahlzeit.seed").joinpath("generic_foods.json").read_text("utf-8")
    foods: list[dict[str, Any]] = json.loads(data)
    return foods


def load_generic_foods(db: Session) -> int:
    """Insert or update every seed item by (source, source_id). Safe to run on every start."""
    existing = {
        (i.source, i.source_id): i
        for i in db.scalars(select(Item).where(Item.household_id.is_(None)))
    }
    for food in generic_foods():
        item = existing.get((food["source"], food["source_id"]))
        if item is None:
            item = Item(household_id=None, source=food["source"], source_id=food["source_id"])
            db.add(item)
        names = food["names"]
        item.name_de, item.name_en, item.name_nl = names.get("de"), names.get("en"), names.get("nl")
        item.category = food["category"]
        item.base_unit = "g"
        item.tracking_mode = food.get("tracking_mode", "counted")
        for name, value in food["nutrients"].items():
            setattr(item, name, value)
        item.search_text = search_text_for(item)
        item.updated_at = clock.now()
        wanted = [(label, float(amount)) for label, amount in food.get("servings", [])]
        if [(s.label, s.amount) for s in item.servings] != wanted:
            item.servings = [
                ServingSize(label=label, amount=amount, position=i)
                for i, (label, amount) in enumerate(wanted)
            ]
    db.commit()
    return len(generic_foods())


def favourite_seed_ids() -> set[tuple[str, str]]:
    return {(f["source"], f["source_id"]) for f in generic_foods() if f.get("favourite")}
