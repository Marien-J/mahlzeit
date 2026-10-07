"""Stock over HTTP, as two phones do it: one shop through 'Bought', three days of logging, the
purchased-versus-logged report, the pantry check and the list suggestions."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests import factories

TODAY = "2026-10-06"


@pytest.fixture
def phones(
    db: Session, make_client: Callable[[], TestClient], clock
) -> tuple[TestClient, TestClient]:
    jonas, partner = factories.household(db)
    a, b = make_client(), make_client()
    factories.signed_in(a, jonas)
    factories.signed_in(b, partner)
    return a, b


def food(client: TestClient, query: str) -> dict[str, Any]:
    found: dict[str, Any] = client.get("/api/items", params={"q": query}).json()[0]
    return found


def add_to_list(client: TestClient, **fields: Any) -> str:
    op_id = str(uuid.uuid4())
    response = client.post(
        "/api/list/ops", json={"ops": [{"kind": "add", "id": op_id, "fields": fields}]}
    )
    assert response.status_code == 200, response.text
    return op_id


def eat(client: TestClient, day: str, *foods: tuple[str, float], **fields: Any) -> dict[str, Any]:
    body = {
        "day": day,
        "slot": "dinner",
        "components": [{"item_id": i, "amount": a} for i, a in foods],
    } | fields
    response = client.post("/api/entries", json=body)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def test_one_shop_and_three_days_of_logging(phones: Any) -> None:
    a, b = phones
    rice, chicken = food(a, "reis"), food(a, "hähnchen brustfilet")
    ids = [
        add_to_list(a, item_id=rice["id"], quantity="1 kg", checked=True),
        add_to_list(b, item_id=chicken["id"], quantity="600 g", checked=True),
        add_to_list(a, text="Spülmittel", checked=True),
    ]
    lidl = next(s["id"] for s in a.get("/api/list").json()["stores"] if s["key"] == "lidl")
    body = {
        "id": str(uuid.uuid4()),
        "store_id": lidl,
        "day": "2026-10-03",
        "lines": [
            {"list_item_id": ids[0], "price_cents": 199},
            {"list_item_id": ids[1], "price_cents": 899},
            {"list_item_id": ids[2], "price_cents": 145},
        ],
    }
    bought = a.post("/api/purchases", json=body)
    assert bought.status_code == 201, bought.text
    assert [ln["amount"] for ln in bought.json()["lines"]] == [1000, 600, None]
    assert bought.json()["spend_cents"] == 199 + 899 + 145
    assert b.post("/api/purchases", json=body).json()["id"] == body["id"]  # sent twice: once
    assert b.get("/api/list").json()["items"] == []

    for day in ("2026-10-04", "2026-10-05", TODAY):
        eat(a, day, (rice["id"], 150), (chicken["id"], 200), joint=True)
    rows = {r["item_id"]: r for r in b.get("/api/stock").json()["rows"]}
    assert (rows[rice["id"]]["level"], rows[chicken["id"]]["level"]) == (550, 0)

    report = a.get("/api/stock/report", params={"start": "2026-10-01"}).json()
    by_item = {r["item_id"]: r for r in report["rows"]}
    assert (by_item[rice["id"]]["purchased"], by_item[rice["id"]]["logged"]) == (1000, 450)
    assert (by_item[chicken["id"]]["logged"], by_item[chicken["id"]]["shortfall"]) == (600, 0)
    assert report["spend_cents"] == 1243

    detail = a.get(f"/api/stock/items/{rice['id']}").json()
    assert [m["reason"] for m in detail["movements"]] == [
        "consumption",
        "consumption",
        "consumption",
        "purchase",
    ]
    assert [p["id"] for p in b.get("/api/purchases").json()] == [body["id"]]
    assert b.get(f"/api/purchases/{body['id']}").json()["store_id"] == lidl


def test_pantry_check_status_items_and_suggestions(phones: Any) -> None:
    a, b = phones
    oats, oil = food(a, "hafer flocken"), food(a, "olivenöl")
    a.post(
        "/api/purchases",
        json={"id": str(uuid.uuid4()), "lines": [{"item_id": oats["id"], "amount": 500}]},
    )
    checked = b.post(
        "/api/stock/checks",
        json={
            "category": "dry_goods",
            "counts": {oats["id"]: 200},
            "statuses": {oil["id"]: "low"},
        },
    )
    assert checked.status_code == 200, checked.text
    stock = a.get("/api/stock").json()
    assert {c["category"] for c in stock["checks"]} == {"dry_goods"}
    rows = {r["item_id"]: r for r in stock["rows"]}
    assert rows[oats["id"]]["level"] == 200
    assert (rows[oil["id"]]["mode"], rows[oil["id"]]["status"]) == ("status", "low")

    a.post(
        "/api/entries",
        json={
            "day": "2026-10-07",
            "slot": "breakfast",
            "plan": True,
            "components": [{"item_id": oats["id"], "amount": 300}],
        },
    )
    suggested = b.get("/api/list/suggestions").json()
    assert suggested["plan_days"] == 3
    assert [(s["item_id"], s["reason"], s["quantity"]) for s in suggested["suggestions"]] == [
        (oats["id"], "planned", "100 g"),
        (oil["id"], "low", None),
    ]

    adjusted = a.post(f"/api/stock/items/{oil['id']}/adjust", json={"status": "ok"})
    assert adjusted.json()["status"] == "ok"
    wasted = a.post(f"/api/stock/items/{oats['id']}/adjust", json={"waste": 50})
    assert wasted.json()["level"] == 150
    mode = a.put(f"/api/stock/items/{oats['id']}/mode", json={"mode": "status"})
    assert (mode.json()["mode"], mode.json()["level"]) == ("status", None)
    profile = a.patch("/api/me/profile", json={"list_plan_days": 7})
    assert profile.json()["profile"]["list_plan_days"] == 7
    assert a.patch("/api/me/profile", json={"list_plan_days": 30}).status_code == 422


def test_invalid_input_answers_with_codes(phones: Any) -> None:
    a, _ = phones
    empty = a.post("/api/purchases", json={"id": str(uuid.uuid4()), "lines": []})
    assert (empty.status_code, empty.json()["code"]) == (422, "purchase_empty")
    rice = food(a, "reis")
    both = a.post(f"/api/stock/items/{rice['id']}/adjust", json={"count": 1, "waste": 1})
    assert both.json()["code"] == "stock_change_invalid"
    period = a.get("/api/stock/report", params={"start": "2026-10-06", "end": "2026-10-01"})
    assert period.json()["code"] == "range_invalid"
    aisle = a.post("/api/stock/checks", json={"category": "attic"})
    assert aisle.json()["code"] == "category_unknown"
