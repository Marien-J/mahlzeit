"""Every tool through the registry: a working call, household isolation, and change records."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from mahlzeit.domain.day import Slot
from mahlzeit.domain.permissions import Client
from mahlzeit.ids import uuid7
from mahlzeit.models import ChangeRecord
from mahlzeit.off_client import set_off_client
from mahlzeit.services import day, items, offers, shopping, stock
from mahlzeit.services.auth import actor_for
from mahlzeit.services.day import ComponentInput, EntryInput
from mahlzeit.services.items import ItemInput
from mahlzeit.services.shopping import Op
from mahlzeit.services.stock import LineInput, PurchaseInput
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
        return str(factories.saved_meal(self.db, m.actor, "Hafer", (oats, 60)).id)

    def recipe(self, member: factories.Member | None = None) -> str:
        m = member or self.me
        oats = factories.generic(self.db, m.actor, "C133000")
        return str(factories.recipe(self.db, m.actor, "Porridge", (oats, 100), servings=2).id)

    def planned(
        self,
        member: factories.Member | None = None,
        *,
        joint: bool = False,
        slot: Slot = Slot.DINNER,
    ) -> day.MealEntry:
        e = day.plan_meal(
            self.db,
            (member or self.me).actor,
            EntryInput(
                day=TODAY,
                slot=slot,
                name="Pasta",
                components=[
                    ComponentInput(
                        item_id=factories.generic(self.db, self.me.actor, "C352000").id, amount=200
                    )
                ],
                joint=joint,
            ),
        )
        return e

    def offer(self, sender: factories.Member | None = None) -> str:
        """A pending offer from `sender` to the other person in their household."""
        s = sender or self.partner
        (to,) = day.others(self.db, s.actor)
        sent = offers.send(self.db, s.actor, entry_id=self.planned(s).id, to_user_id=to.id)
        return str(sent.offer.id)

    def list_item(self, member: factories.Member | None = None, text: str = "Milch") -> str:
        op = Op(kind="add", id=uuid7(), fields={"text": text})
        shopping.apply(self.db, (member or self.me).actor, [op])
        return str(op.id)

    def olive_oil(self) -> str:
        return str(factories.generic(self.db, self.me.actor, "Q120000").id)

    def bought(self, item_id: str, amount: float) -> None:
        stock.record_purchase(
            self.db,
            self.me.actor,
            PurchaseInput(id=uuid7(), lines=[LineInput(item_id=uuid.UUID(item_id), amount=amount)]),
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
        w.call("get_household_snapshot")["not_yet_available"] == []
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
        w.call("log_planned_meal", {"entry_id": str(w.planned().id)})["state"] == "logged"
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
    "get_meal_plan": lambda w: assert_(len(w.call("get_meal_plan", {"days": 3})["days"]) == 3),
    "plan_meal": lambda w: assert_(
        w.call("plan_meal", {"slot": "dinner", "name": "Pizza"})["state"] == "planned"
    ),
    "set_share": lambda w: assert_(
        w.call("set_share", {"entry_id": str(w.planned(joint=True).id), "share": 0.7})["share"]
        == 0.7
    ),
    "set_exact_amounts": lambda w: assert_(
        w.call(
            "set_exact_amounts",
            {
                "entry_id": str(e.id),
                "amounts": [{"component_id": str(e.components[0].id), "amount": 150}],
            },
        )["participants"][0]["exact_amounts"]
        == {str(e.components[0].id): 150}
        if (e := w.planned(joint=True))
        else None
    ),
    "move_entry": lambda w: assert_(
        [
            m["at"]
            for m in w.call(
                "move_entry",
                {"entry_id": str(w.planned(slot=Slot.DINNER).id), "before_id": w.entry()},
            )["items"]
        ]
        == ["07:30:00"]
    ),
    "add_recipe_to_list": lambda w: assert_(
        w.call("add_recipe_to_list", {"recipe_id": w.recipe(), "portions": 2})["added"][0][
            "quantity"
        ]
        == "100 g"
    ),
    "list_offers": lambda w: (
        w.offer(),
        assert_(w.call("list_offers")["items"][0]["incoming"] is True),
    ),
    "send_offer": lambda w: assert_(
        w.call("send_offer", {"entry_id": str(w.planned().id)})["state"] == "pending"
    ),
    "respond_to_offer": lambda w: assert_(
        w.call("respond_to_offer", {"offer_id": w.offer(), "action": "accept"})["state"]
        == "accepted"
    ),
    "withdraw_offer": lambda w: assert_(
        w.call("withdraw_offer", {"offer_id": w.offer(w.me)})["state"] == "withdrawn"
    ),
    "get_shopping_list": lambda w: (
        w.list_item(w.partner),
        assert_(w.call("get_shopping_list")["items"][0]["text"] == "Milch"),
    ),
    "add_list_items": lambda w: assert_(
        [
            (i["text"], i["quantity"], i["store_id"] is not None)
            for i in w.call(
                "add_list_items", {"items": [{"text": "2 Brot", "store": "aldi"}, {"text": "Eier"}]}
            )["list"]["items"]
        ]
        == [("Brot", "2", True), ("Eier", None, False)]
    ),
    "check_list_items": lambda w: assert_(
        w.call("check_list_items", {"ids": [w.list_item()]})["list"]["items"][0]["checked"]
    ),
    "update_list_items": lambda w: assert_(
        w.call(
            "update_list_items",
            {"changes": [{"id": w.list_item(), "quantity": "3", "category": "dairy_eggs"}]},
        )["list"]["items"][0]["quantity"]
        == "3"
    ),
    "remove_list_items": lambda w: assert_(
        w.call("remove_list_items", {"ids": [w.list_item()]})["list"]["items"] == []
    ),
    "record_purchase": lambda w: assert_(
        [
            (ln["amount"], ln["price_cents"])
            for ln in w.call(
                "record_purchase",
                {
                    "store": "lidl",
                    "lines": [
                        {"item_id": w.oats(), "quantity": "500 g", "price_cents": 129},
                        {"text": "Kerzen"},
                    ],
                },
            )["lines"]
        ]
        == [(500, 129), (None, None)]
    ),
    "get_stock": lambda w: (
        w.bought(w.oats(), 500),
        assert_(w.call("get_stock")["rows"][0]["level"] == 500),
    ),
    "adjust_stock": lambda w: (
        w.bought(w.oats(), 500),
        assert_(w.call("adjust_stock", {"item_id": w.oats(), "count": 300})["level"] == 300),
    ),
    "set_tracking_mode": lambda w: assert_(
        w.call("set_tracking_mode", {"item_id": w.oats(), "mode": "status"})["status"] == "ok"
    ),
    "mark_pantry_checked": lambda w: (
        w.bought(w.oats(), 500),
        assert_(
            w.call("mark_pantry_checked", {"category": "dry_goods", "counts": {w.oats(): 100}})[
                "category"
            ]
            == "dry_goods"
        ),
        assert_(w.call("get_stock")["rows"][0]["level"] == 100),
    ),
    "get_list_suggestions": lambda w: (
        w.call("adjust_stock", {"item_id": w.olive_oil(), "status": "out"}),
        assert_([s["reason"] for s in w.call("get_list_suggestions")["suggestions"]] == ["out"]),
    ),
    "get_stock_report": lambda w: (
        w.bought(w.oats(), 500),
        assert_(w.call("get_stock_report")["rows"][0]["purchased"] == 500),
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
    "plan_meal": lambda w, s: {"slot": "dinner", "recipe_id": w.recipe(s)},
    "set_share": lambda w, s: {"entry_id": str(w.planned(s).id), "share": 0.5},
    "set_exact_amounts": lambda w, s: {"entry_id": str(w.planned(s).id), "amounts": []},
    "move_entry": lambda w, s: {"entry_id": str(w.planned(s).id), "before_id": None},
    "add_recipe_to_list": lambda w, s: {"recipe_id": w.recipe(s)},
    "send_offer": lambda w, s: {
        "entry_id": str(w.planned(s).id),
        "to_user_id": str(day.others(w.db, s.actor)[0].id),
    },
    "respond_to_offer": lambda w, s: {"offer_id": w.offer(s), "action": "accept"},
    "withdraw_offer": lambda w, s: {"offer_id": w.offer(s)},
    "add_list_items": lambda w, s: {"items": [{"text": "x", "item_id": w.own_item(s)}]},
    "check_list_items": lambda w, s: {"ids": [w.list_item(s)]},
    "update_list_items": lambda w, s: {"changes": [{"id": w.list_item(s), "quantity": "9"}]},
    "remove_list_items": lambda w, s: {"ids": [w.list_item(s)]},
    "record_purchase": lambda w, s: {"lines": [{"item_id": w.own_item(s), "amount": 1}]},
    "adjust_stock": lambda w, s: {"item_id": w.own_item(s), "count": 1},
    "set_tracking_mode": lambda w, s: {"item_id": w.own_item(s), "mode": "status"},
    "mark_pantry_checked": lambda w, s: {"category": "other", "counts": {w.own_item(s): 1}},
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
        world.call("log_food", {"slot": "lunch", "recipe_id": world.meal(stranger)})
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


def test_unknown_store_names_are_errors(world: World) -> None:
    with pytest.raises(ToolError) as err:
        world.call("add_list_items", {"items": [{"text": "Brot", "store": "Harrods"}]})
    assert err.value.code == "store_not_found"


def test_the_list_of_another_household_stays_hidden(
    world: World, stranger: factories.Member
) -> None:
    world.list_item(stranger, "Geheim")
    assert world.call("get_shopping_list")["items"] == []
    assert world.call("get_household_snapshot")["shopping_list"]["items"] == []


def test_a_pending_offer_shows_up_with_its_meal_and_effect(world: World) -> None:
    world.offer()
    (offer,) = world.call("list_offers")["items"]
    assert offer["incoming"] and offer["state"] == "pending"
    assert offer["meal"]["name"] == "Pasta" and offer["effect"]["incoming"]["values"]["kcal"] > 0
    assert world.call("get_household_snapshot")["offers"][0]["id"] == offer["id"]


def test_without_a_partner_there_is_nobody_to_offer_to(db: Session, clock) -> None:
    (alone,) = factories.household(db, "Alone")
    ctx = ToolContext(db=db, actor=actor_for(alone.user, Client.CONNECTOR), user=alone.user)
    meal = day.plan_meal(
        db,
        alone.actor,
        EntryInput(
            day=TODAY, slot=Slot.DINNER, components=[ComponentInput(quick_name="x", kcal=1)]
        ),
    )
    with pytest.raises(ToolError) as err:
        registry.call(ctx, "send_offer", {"entry_id": str(meal.id)})
    assert err.value.code == "no_partner"
