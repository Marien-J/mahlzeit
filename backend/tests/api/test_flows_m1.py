from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from mahlzeit.off_client import set_off_client
from tests import factories
from tests.fakes import FakeOff

Clients = Callable[[], TestClient]
TODAY = "2026-10-06"


@pytest.fixture
def off() -> Iterator[FakeOff]:
    fake = FakeOff()
    set_off_client(fake)
    yield fake
    set_off_client(None)


@pytest.fixture
def jonas(db: Session, make_client: Clients, clock) -> TestClient:
    member, _ = factories.household(db)
    client = make_client()
    factories.signed_in(client, member)
    return client


class TestCatalogue:
    def test_search_in_the_users_language(self, jonas: TestClient) -> None:
        hits = jonas.get("/api/items", params={"q": "chicken breast"}).json()
        top = hits[0]
        assert top["names"]["de"] == "Hähnchen Brustfilet, roh"
        assert top["name"] == "Hähnchen Brustfilet, roh"  # German user
        assert top["generic"] is True and top["favourite"] is True
        jonas.patch("/api/me", json={"language": "nl"})
        assert jonas.get("/api/items", params={"q": "kipfilet"}).json()[0]["name"] == "Kipfilet"

    def test_create_and_update_own_item(self, jonas: TestClient) -> None:
        body = {
            "names": {"de": "Skyr Natur"},
            "brand": "Arla",
            "category": "dairy_eggs",
            "nutrients": {"kcal": 63, "protein": 11},
            "servings": [{"label": "cup", "amount": 150}],
            "barcodes": ["4008400401621"],
        }
        created = jonas.post("/api/items", json=body)
        assert created.status_code == 201, created.text
        item_id = created.json()["id"]
        updated = jonas.put(f"/api/items/{item_id}", json=body | {"brand": "Siggi's"})
        assert updated.json()["brand"] == "Siggi's"
        assert jonas.put(f"/api/items/{item_id}/favourite", json={"on": True}).status_code == 204
        assert jonas.get(f"/api/items/{item_id}").json()["favourite"] is True

    def test_generic_items_cannot_be_edited(self, jonas: TestClient) -> None:
        generic = jonas.get("/api/items", params={"q": "broccoli"}).json()[0]
        r = jonas.put(f"/api/items/{generic['id']}", json={"names": {"de": "x"}})
        assert r.status_code == 409 and r.json()["code"] == "item_read_only"

    def test_barcode_scan_to_draft_to_item(self, jonas: TestClient, off: FakeOff) -> None:
        first = jonas.get("/api/barcodes/4008400401621").json()
        assert first["status"] == "draft" and first["draft"]["names"]["de"] == "Nutella"
        assert first["draft"]["missing"] == ["fibre"]
        d = first["draft"]
        body = {
            "names": d["names"],
            "brand": d["brand"],
            "category": d["category"],
            "base_unit": d["base_unit"],
            "nutrients": d["nutrients"] | {"fibre": 3.5},
            "servings": d["servings"],
            "barcodes": [d["barcode"]],
            "source": "off",
        }
        item = jonas.post("/api/items", json=body).json()
        assert item["source"] == "off"
        again = jonas.get("/api/barcodes/4008400401621").json()
        assert again["status"] == "item" and again["item"]["id"] == item["id"]
        assert off.product_calls == ["4008400401621"]

    def test_unknown_and_invalid_barcodes(self, jonas: TestClient, off: FakeOff) -> None:
        assert jonas.get("/api/barcodes/96385074").json()["status"] == "not_found"
        r = jonas.get("/api/barcodes/12345")
        assert r.status_code == 422 and r.json()["code"] == "barcode_invalid"

    def test_search_online(self, jonas: TestClient, off: FakeOff) -> None:
        drafts = jonas.get("/api/online-search", params={"q": "nutella"}).json()
        assert drafts[0]["names"]["de"] == "Nutella"


class TestDay:
    def test_log_view_edit_and_delete(self, jonas: TestClient) -> None:
        oats = jonas.get("/api/items", params={"q": "haferflocken"}).json()[0]
        created = jonas.post(
            "/api/entries",
            json={
                "day": TODAY,
                "slot": "breakfast",
                "components": [
                    {"item_id": oats["id"], "amount": 80},
                    {"quick_name": "Kaffee", "kcal": 5},
                ],
            },
        )
        assert created.status_code == 201, created.text
        entry = created.json()
        assert entry["state"] == "logged" and entry["at"] == "08:00:00"
        expected = round(oats["nutrients"]["kcal"] * 0.8 + 5)
        view = jonas.get(f"/api/days/{TODAY}").json()
        me = view["people"][0]
        assert me["is_me"] and me["logged"]["values"]["kcal"] == expected
        assert [p["display_name"] for p in view["people"]] == ["Jonas", "Partner"]

        patched = jonas.patch(
            f"/api/entries/{entry['id']}", json={"at": "07:30", "eaten_out": True}
        ).json()
        assert patched["at"] == "07:30:00" and patched["eaten_out"] is True
        assert jonas.delete(f"/api/entries/{entry['id']}").status_code == 204
        assert jonas.get(f"/api/days/{TODAY}").json()["people"][0]["entries"] == []

    def test_targets_remaining_and_day_type(self, jonas: TestClient) -> None:
        plan = jonas.put(
            "/api/targets", json={"kcal": 2500, "protein": 180, "day_types": ["training"]}
        ).json()
        jonas.put("/api/targets", json={"kcal": 2200, "protein": 170, "day_types": ["rest"]})
        assert plan["history"][0]["targets"]["kcal"] == 2500
        jonas.post(
            "/api/entries",
            json={
                "day": TODAY,
                "slot": "lunch",
                "components": [{"quick_name": "Bowl", "kcal": 700, "protein": 50}],
            },
        )
        me = jonas.get(f"/api/days/{TODAY}").json()["people"][0]
        assert me["day_type"] == "rest" and me["remaining"]["kcal"] == 1500
        assert (
            jonas.put(f"/api/days/{TODAY}/day-type", json={"day_type": "training"}).status_code
            == 204
        )
        me = jonas.get(f"/api/days/{TODAY}").json()["people"][0]
        assert me["day_type"] == "training" and me["remaining"]["kcal"] == 1800
        pattern = jonas.put("/api/targets/week-pattern", json={"pattern": "TRTRTRR"}).json()
        assert pattern["week_pattern"] == "TRTRTRR"

    def test_copy_and_saved_meals(self, jonas: TestClient) -> None:
        oats = jonas.get("/api/items", params={"q": "haferflocken"}).json()[0]
        entry = jonas.post(
            "/api/entries",
            json={
                "day": "2026-10-05",
                "slot": "breakfast",
                "name": "Porridge",
                "components": [{"item_id": oats["id"], "amount": 70}],
            },
        ).json()
        copied = jonas.post(f"/api/entries/{entry['id']}/copy", json={"day": TODAY})
        assert copied.status_code == 201 and copied.json()["day"] == TODAY
        meal = jonas.post(f"/api/entries/{entry['id']}/save-as-meal", json={}).json()
        assert meal["name"] == "Porridge" and meal["ingredients"][0]["amount"] == 70
        logged = jonas.post(
            "/api/entries", json={"day": TODAY, "slot": "snack", "saved_meal_id": meal["id"]}
        )
        assert logged.json()["saved_meal_id"] == meal["id"]
        assert [m["name"] for m in jonas.get("/api/saved-meals").json()] == ["Porridge"]
        renamed = jonas.patch(f"/api/saved-meals/{meal['id']}", json={"name": "Hafer"}).json()
        assert renamed["name"] == "Hafer"
        assert jonas.delete(f"/api/saved-meals/{meal['id']}").status_code == 204
        day_copy = jonas.post("/api/days/2026-10-07/copy", json={"source_day": "2026-10-05"})
        assert day_copy.status_code == 201 and day_copy.json()[0]["state"] == "planned"

    def test_another_household_sees_only_its_own_day(
        self, db: Session, jonas: TestClient, make_client: Clients
    ) -> None:
        jonas.post(
            "/api/entries",
            json={
                "day": TODAY,
                "slot": "lunch",
                "components": [{"quick_name": "Secret", "kcal": 1}],
            },
        )
        stranger, _ = factories.household(db, "Stranger", "Friend")
        other = make_client()
        factories.signed_in(other, stranger)
        view = other.get(f"/api/days/{TODAY}").json()
        assert [p["display_name"] for p in view["people"]] == ["Stranger", "Friend"]
        assert all(p["entries"] == [] for p in view["people"])


class TestConnectorSettings:
    def test_create_rotate_revoke(self, jonas: TestClient) -> None:
        assert jonas.get("/api/connector").json()["active"] is False
        first = jonas.post("/api/connector").json()["url"]
        assert first.startswith("http://localhost/mcp/") and len(first.rsplit("/", 1)[1]) >= 80
        status = jonas.get("/api/connector").json()
        assert status["active"] is True and status["last_used_at"] is None
        second = jonas.post("/api/connector").json()["url"]
        assert second != first
        assert jonas.delete("/api/connector").status_code == 204
        assert jonas.get("/api/connector").json()["active"] is False
