"""Every tool through the registry: a working call, household isolation, and change records."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from mahlzeit.domain.day import Slot
from mahlzeit.domain.permissions import Client
from mahlzeit.models import ChangeRecord
from mahlzeit.off_client import set_off_client
from mahlzeit.services import day, items, saved_meals
from mahlzeit.services.auth import actor_for
from mahlzeit.services.day import ComponentInput, EntryInput
from mahlzeit.services.items import ItemInput
from mahlzeit.services.saved_meals import Ingredient
from mahlzeit.tools import registry
from mahlzeit.tools.registry import ToolContext, ToolError
from tests import factories
from tests.fakes import FakeOff

TODAY = date(2026, 10, 6)
REGISTRY = registry.load_all()


@dataclass
class World:
    db: Session
    me: factories.Member
    partner: factories.Member

    def ctx(self, member: factories.Member | None = None) -> ToolContext:
        m = member or self.me
        return ToolContext(db=self.db, actor=actor_for(m.user, Client.CONNECTOR), user=m.user)

    def call(
        self, name: str, args: dict[str, Any] | None = None, member: factories.Member | None = None
    ) -> dict[str, Any]:
        return registry.call(self.ctx(member), name, args)

    def oats(self) -> str:
        return str(factories.generic(self.db, self.me.actor, "C133000").id)

    def entry(self, member: factories.Member | None = None, on: date = TODAY) -> str:
        e = day.log_food(
            self.db,
            (member or self.me).actor,
            EntryInput(
                day=on,
                slot=Slot.BREAKFAST,
                components=[ComponentInput(quick_name="Müsli", kcal=400)],
            ),
        )
        return str(e.id)

    def meal(self, member: factories.Member | None = None) -> str:
        m = member or self.me
        oats = factories.generic(self.db, m.actor, "C133000")
        return str(
            saved_meals.create(
                self.db, m.actor, name="Hafer", ingredients=[Ingredient(oats.id, 60)]
            ).id
        )

    def own_item(self, member: factories.Member | None = None) -> str:
        return str(
            items.create(self.db, (member or self.me).actor, ItemInput(names={"de": "Eigenes"})).id
        )


@pytest.fixture
def world(db: Session, clock) -> World:
    set_off_client(FakeOff())
    me, partner = factories.household(db)
    yield World(db, me, partner)
    set_off_client(None)


LABEL = {
    "names": {"de": "Skyr Natur"},
    "category": "dairy_eggs",
    "nutrients": {"kcal": 63, "protein": 11},
}

# One working call per tool. The test below fails when a tool is added without a case here.
CASES: dict[str, Callable[[World], None]] = {
    "search_items": lambda w: assert_(
        w.call("search_items", {"query": "kipfilet"})["items"][0]["names"]["de"]
        == "Hähnchen Brustfilet, roh"
    ),
    "get_item": lambda w: assert_(
        w.call("get_item", {"item_id": w.oats()})["names"]["de"] == "Hafer Flocken"
    ),
    "create_item": lambda w: assert_(w.call("create_item", LABEL)["generic"] is False),
    "update_item": lambda w: assert_(
        w.call("update_item", LABEL | {"item_id": w.own_item(), "brand": "Arla"})["brand"] == "Arla"
    ),
    "lookup_barcode": lambda w: assert_(
        w.call("lookup_barcode", {"code": "4008400401621"})["status"] == "draft"
    ),
    "search_online": lambda w: assert_(
        w.call("search_online", {"query": "nutella"})["items"][0]["names"]["de"] == "Nutella"
    ),
    "set_favourite": lambda w: assert_(
        w.call("set_favourite", {"item_id": w.own_item(), "favourite": True}) == {"ok": True}
    ),
    "get_day": lambda w: assert_(len(w.call("get_day", {})["people"]) == 2),
    "get_household_snapshot": lambda w: assert_(
        w.call("get_household_snapshot")["not_yet_available"]
        == ["offers", "shopping_list", "stock"]
    ),
    "log_food": lambda w: assert_(
        w.call(
            "log_food",
            {
                "slot": "breakfast",
                "foods": [{"item_id": w.oats(), "amount": 80}],
                "quick_add": [{"name": "Kaffee", "kcal": 5}],
            },
        )["state"]
        == "logged"
    ),
    "log_planned_meal": lambda w: assert_(
        w.call("log_planned_meal", {"entry_id": w.entry(on=date(2026, 10, 8))})["state"] == "logged"
    ),
    "update_entry": lambda w: assert_(
        w.call("update_entry", {"entry_id": w.entry(), "time": "07:45"})["at"] == "07:45:00"
    ),
    "delete_entry": lambda w: assert_(
        w.call("delete_entry", {"entry_id": w.entry()}) == {"ok": True}
    ),
    "copy_meals": lambda w: assert_(
        len(w.call("copy_meals", {"entry_id": w.entry(on=date(2026, 10, 1))})["items"]) == 1
    ),
    "get_targets": lambda w: assert_(w.call("get_targets")["week_pattern"] == "RRRRRRR"),
    "set_targets": lambda w: assert_(
        w.call("set_targets", {"kcal": 2400, "protein": 170, "week_pattern": "TRTRTRR"})[
            "week_pattern"
        ]
        == "TRTRTRR"
    ),
    "set_day_type": lambda w: assert_(
        w.call("set_day_type", {"day_type": "training"}) == {"ok": True}
    ),
    "list_recipes": lambda w: (
        w.meal(),
        assert_(w.call("list_recipes")["items"][0]["name"] == "Hafer"),
    ),
    "get_recipe": lambda w: assert_(
        w.call("get_recipe", {"recipe_id": w.meal()})["ingredients"][0]["amount"] == 60
    ),
    "create_recipe": lambda w: assert_(
        w.call(
            "create_recipe", {"name": "Hafer", "ingredients": [{"item_id": w.oats(), "amount": 50}]}
        )["name"]
        == "Hafer"
    ),
    "update_recipe": lambda w: assert_(
        w.call("update_recipe", {"recipe_id": w.meal(), "name": "Porridge"})["name"] == "Porridge"
    ),
    "delete_recipe": lambda w: assert_(
        w.call("delete_recipe", {"recipe_id": w.meal()}) == {"ok": True}
    ),
}


def assert_(condition: bool) -> None:
    assert condition


def test_every_tool_has_a_case() -> None:
    assert set(CASES) == set(REGISTRY)


@pytest.mark.parametrize("name", sorted(CASES))
def test_tool_works(world: World, name: str) -> None:
    CASES[name](world)


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_tool_definitions(name: str) -> None:
    t = REGISTRY[name]
    assert len(t.description) > 30
    schema = t.input_schema()
    assert schema["type"] == "object"


def test_writes_are_recorded_as_connector(world: World) -> None:
    world.call("log_food", {"slot": "snack", "quick_add": [{"name": "Apfel", "kcal": 80}]})
    change = world.db.scalars(select(ChangeRecord).where(ChangeRecord.entity == "meal_entry")).one()
    assert change.client == "connector" and change.user_id == world.me.user.id


def test_errors_are_codes_not_tracebacks(world: World) -> None:
    with pytest.raises(ToolError) as err:
        world.call("log_food", {"slot": "lunch"})
    assert err.value.as_dict() == {"error": "entry_empty", "detail": {}}
    with pytest.raises(ToolError) as err:
        world.call("log_food", {"slot": "brunch"})
    assert err.value.code == "validation_error"
    with pytest.raises(ToolError) as err:
        world.call("drop_tables")
    assert err.value.code == "unknown_tool"


def test_cannot_change_the_partners_entry(world: World) -> None:
    theirs = world.entry(world.partner)
    with pytest.raises(ToolError) as err:
        world.call("delete_entry", {"entry_id": theirs})
    assert err.value.code == "entry_not_yours"


# --- household isolation: every tool that takes an id --------------------------------------


def _uuid_fields(schema: dict[str, Any]) -> bool:
    text = repr(schema)
    return "'format': 'uuid'" in text


@pytest.fixture
def stranger(db: Session) -> factories.Member:
    member, _ = factories.household(db, "Stranger", "Friend")
    return member


CROSS: dict[str, Callable[[World, factories.Member], dict[str, Any]]] = {
    "get_item": lambda w, s: {"item_id": w.own_item(s)},
    "update_item": lambda w, s: LABEL | {"item_id": w.own_item(s)},
    "set_favourite": lambda w, s: {"item_id": w.own_item(s), "favourite": True},
    "log_food": lambda w, s: {"slot": "lunch", "foods": [{"item_id": w.own_item(s), "amount": 10}]},
    "log_planned_meal": lambda w, s: {"entry_id": w.entry(s)},
    "update_entry": lambda w, s: {"entry_id": w.entry(s), "name": "mine"},
    "delete_entry": lambda w, s: {"entry_id": w.entry(s)},
    "copy_meals": lambda w, s: {"entry_id": w.entry(s)},
    "get_recipe": lambda w, s: {"recipe_id": w.meal(s)},
    "create_recipe": lambda w, s: {"name": "x", "from_entry_id": w.entry(s)},
    "update_recipe": lambda w, s: {"recipe_id": w.meal(s), "name": "x"},
    "delete_recipe": lambda w, s: {"recipe_id": w.meal(s)},
}


def test_every_tool_taking_an_id_has_a_cross_household_case() -> None:
    with_ids = {name for name, t in REGISTRY.items() if _uuid_fields(t.input_schema())}
    assert with_ids == set(CROSS)


@pytest.mark.parametrize("name", sorted(CROSS))
def test_cannot_reach_another_household(
    world: World, stranger: factories.Member, name: str
) -> None:
    args = CROSS[name](world, stranger)
    with pytest.raises(ToolError) as err:
        world.call(name, args)
    assert err.value.code.endswith("not_found"), err.value.code


def test_saved_meal_of_another_household_cannot_be_logged(
    world: World, stranger: factories.Member
) -> None:
    with pytest.raises(ToolError) as err:
        world.call("log_food", {"slot": "lunch", "saved_meal_id": world.meal(stranger)})
    assert err.value.code.endswith("not_found")


def test_reads_only_show_the_own_household(world: World, stranger: factories.Member) -> None:
    world.entry(stranger)
    world.own_item(stranger)
    assert all(p["entries"] == [] for p in world.call("get_day")["people"])
    assert all(
        i["generic"] or i["names"]["de"] != "Eigenes"
        for i in world.call("search_items", {"query": "eigenes"})["items"]
    )
    assert world.call("list_recipes")["items"] == []
