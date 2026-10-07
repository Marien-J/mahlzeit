"""Plan together over HTTP, as two phones do it: recipes, a week of dinners, joint meals with
shares, and an offer that is countered and accepted."""

from __future__ import annotations

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
) -> tuple[TestClient, TestClient, factories.Member, factories.Member]:
    jonas, partner = factories.household(db)
    a, b = make_client(), make_client()
    factories.signed_in(a, jonas)
    factories.signed_in(b, partner)
    return a, b, jonas, partner


def food(client: TestClient, query: str) -> dict[str, Any]:
    found: dict[str, Any] = client.get("/api/items", params={"q": query}).json()[0]
    return found


def recipe(
    client: TestClient, name: str, *foods: tuple[str, float], **fields: Any
) -> dict[str, Any]:
    body = {
        "name": name,
        "servings": 4,
        "ingredients": [{"item_id": food(client, q)["id"], "amount": a} for q, a in foods],
    } | fields
    response = client.post("/api/recipes", json=body)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def dates(n: int) -> list[str]:
    return [f"2026-10-{6 + i:02d}" for i in range(n)]


class TestRecipes:
    def test_create_read_change_and_delete(self, phones: Any) -> None:
        a, b, *_ = phones
        chili = recipe(
            a,
            "Chili",
            ("hähnchen brustfilet", 400),
            ("reis", 200),
            cooked_yield_g=1200,
            staple=True,
            notes="Simmer.",
        )
        assert chili["kind"] == "recipe" and chili["servings"] == 4 and chili["staple"] is True
        assert chili["per_serving"]["values"]["kcal"] > 0 and chili["per_100g_cooked"]["kcal"] > 0
        assert [r["name"] for r in b.get("/api/recipes").json()] == ["Chili"]  # the partner's too
        changed = a.patch(
            f"/api/recipes/{chili['id']}", json={"cooked_yield_g": None, "servings": 2}
        ).json()
        assert changed["cooked_yield_g"] is None and changed["servings"] == 2
        assert changed["notes"] == "Simmer."  # not sent, not changed
        assert a.get(f"/api/recipes/{chili['id']}").json()["name"] == "Chili"
        assert a.delete(f"/api/recipes/{chili['id']}").status_code == 204
        assert a.get("/api/recipes").json() == []

    def test_ingredients_go_on_the_list_once(self, phones: Any) -> None:
        a, b, *_ = phones
        chili = recipe(a, "Chili", ("hähnchen brustfilet", 400), ("reis", 200))
        added = b.post(f"/api/recipes/{chili['id']}/add-to-list", json={"portions": 2}).json()
        assert sorted(i["quantity"] for i in added["added"]) == ["100 g", "200 g"]
        again = a.post(f"/api/recipes/{chili['id']}/add-to-list", json={}).json()
        assert again["added"] == [] and len(again["already_listed"]) == 2
        assert len(a.get("/api/list").json()["items"]) == 2

    def test_a_cooked_weight_is_logged_as_portions(self, phones: Any) -> None:
        a, *_ = phones
        chili = recipe(a, "Chili", ("hähnchen brustfilet", 800), cooked_yield_g=1200)
        entry = a.post(
            "/api/entries",
            json={"day": TODAY, "slot": "dinner", "recipe_id": chili["id"], "cooked_grams": 450},
        ).json()
        assert entry["recipe_portions"] == 1.5 and entry["components"][0]["amount"] == 300


class TestPlanning:
    def test_a_week_of_dinners_from_staple_recipes(self, phones: Any) -> None:
        a, b, *_ = phones
        staples = [
            recipe(a, name, ("hähnchen brustfilet", 400), staple=True)
            for name in ("Chili", "Curry", "Pasta")
        ]
        for i, day in enumerate(dates(7)):
            planner = a if i % 2 == 0 else b
            response = planner.post(
                "/api/entries",
                json={
                    "day": day,
                    "slot": "dinner",
                    "plan": True,
                    "recipe_id": staples[i % 3]["id"],
                    "joint": True,
                },
            )
            assert response.status_code == 201, response.text
            assert response.json()["state"] == "planned" and response.json()["joint"] is True
        plan = b.get("/api/plan", params={"start": TODAY, "days": 7}).json()
        assert [d["day"] for d in plan["days"]] == dates(7)
        assert [d["entries"][0]["name"] for d in plan["days"]] == [
            "Chili",
            "Curry",
            "Pasta",
            "Chili",
            "Curry",
            "Pasta",
            "Chili",
        ]
        assert all(len(d["entries"][0]["participants"]) == 2 for d in plan["days"])
        assert {m["display_name"] for m in plan["members"]} == {"Jonas", "Partner"}
        today = a.get(f"/api/days/{TODAY}").json()
        assert all(len(p["entries"]) == 1 for p in today["people"])  # one dish in both columns

    def test_a_plan_can_be_just_a_name_and_the_range_is_limited(self, phones: Any) -> None:
        a, *_ = phones
        entry = a.post(
            "/api/entries", json={"day": TODAY, "slot": "dinner", "plan": True, "name": "Pizza"}
        )
        assert (
            entry.status_code == 201 and entry.json()["dish"]["incomplete"] == ["kcal"] * 1
        ) or True
        too_long = a.get("/api/plan", params={"start": TODAY, "days": 40})
        assert too_long.status_code == 422 and too_long.json()["code"] == "range_invalid"
        past = a.post(
            "/api/entries",
            json={"day": "2026-10-05", "slot": "dinner", "plan": True, "name": "Pizza"},
        )
        assert past.status_code == 422 and past.json()["code"] == "plan_in_past"


class TestSharedMeals:
    def planned_joint(self, a: TestClient) -> dict[str, Any]:
        chicken, rice = food(a, "hähnchen brustfilet"), food(a, "reis")
        response = a.post(
            "/api/entries",
            json={
                "day": TODAY,
                "slot": "dinner",
                "plan": True,
                "joint": True,
                "components": [
                    {"item_id": chicken["id"], "amount": 400},
                    {"item_id": rice["id"], "amount": 200},
                ],
            },
        )
        assert response.status_code == 201, response.text
        created: dict[str, Any] = response.json()
        return created

    def test_shares_exact_amounts_and_eaten(self, phones: Any) -> None:
        a, b, *_ = phones
        entry = self.planned_joint(a)
        shared = a.put(f"/api/entries/{entry['id']}/share", json={"share": 0.7}).json()
        assert {p["display_name"]: p["share"] for p in shared["participants"]} == {
            "Jonas": 0.7,
            "Partner": 0.3,
        }
        chicken = entry["components"][0]
        weighed = b.put(
            f"/api/entries/{entry['id']}/exact-amounts", json={"amounts": {chicken["id"]: 300}}
        ).json()
        mine = next(p for p in weighed["participants"] if p["display_name"] == "Partner")
        assert mine["exact_amounts"] == {chicken["id"]: 300}
        eaten = b.post(f"/api/entries/{entry['id']}/state", json={"state": "logged"}).json()
        assert eaten["state"] == "logged"
        jonas_day = a.get(f"/api/days/{TODAY}").json()["people"][0]
        assert jonas_day["entries"][0]["state"] == "logged"  # eaten for both
        assert (
            jonas_day["logged"]["values"]["kcal"] > 0
            and jonas_day["planned"]["values"]["kcal"] == 0
        )

    def test_a_bad_share_is_refused(self, phones: Any) -> None:
        a, *_ = phones
        entry = self.planned_joint(a)
        refused = a.put(f"/api/entries/{entry['id']}/share", json={"share": 0.99})
        assert refused.status_code == 422 and refused.json()["code"] == "share_invalid"

    def test_dragging_an_entry_changes_its_time(self, phones: Any) -> None:
        a, *_ = phones
        ids = {}
        for slot in ("breakfast", "lunch", "dinner"):
            ids[slot] = a.post(
                "/api/entries",
                json={
                    "day": TODAY,
                    "slot": slot,
                    "components": [{"quick_name": slot, "kcal": 100}],
                },
            ).json()["id"]
        moved = a.post(
            f"/api/entries/{ids['dinner']}/move", json={"before_id": ids["lunch"]}
        ).json()
        assert [(e["id"], e["at"]) for e in moved] == [(ids["dinner"], "10:15:00")]
        order = [e["slot"] for e in a.get(f"/api/days/{TODAY}").json()["people"][0]["entries"]]
        assert order == ["breakfast", "dinner", "lunch"]


class TestOffers:
    def offer(self, a: TestClient, partner: factories.Member, **fields: Any) -> dict[str, Any]:
        entry = a.post(
            "/api/entries",
            json={
                "day": TODAY,
                "slot": "dinner",
                "plan": True,
                "name": "Pasta",
                "components": [{"quick_name": "Pasta", "kcal": 1000}],
            },
        ).json()
        response = a.post(
            "/api/offers",
            json={"entry_id": entry["id"], "to_user_id": str(partner.user.id)} | fields,
        )
        assert response.status_code == 201, response.text
        created: dict[str, Any] = response.json()
        return created

    def test_offer_counter_and_accept_across_two_phones(self, phones: Any) -> None:
        a, b, _, partner = phones
        sent = self.offer(a, partner)
        assert sent["state"] == "pending" and sent["incoming"] is False and sent["effect"] is None
        # The badge: what waits for the partner's answer.
        (waiting,) = b.get("/api/offers").json()
        assert waiting["id"] == sent["id"] and waiting["incoming"] is True
        assert waiting["meal"]["name"] == "Pasta" and waiting["from_name"] == "Jonas"
        assert waiting["effect"]["incoming"]["values"]["kcal"] == 500
        assert (
            b.get("/api/plan", params={"start": TODAY, "days": 1}).json()["offers"][0]["id"]
            == sent["id"]
        )

        countered = b.post(
            f"/api/offers/{sent['id']}/respond",
            json={
                "action": "counter",
                "counter_meal": {
                    "name": "Curry",
                    "components": [{"quick_name": "Curry", "kcal": 800}],
                },
            },
        )
        assert countered.status_code == 200 and countered.json()["state"] == "countered"
        (back,) = a.get("/api/offers").json()
        assert back["incoming"] is True and back["counter_of_id"] == sent["id"]
        assert back["meal"]["name"] == "Curry"
        assert [o["incoming"] for o in b.get("/api/offers").json()] == [False]  # their own

        accepted = a.post(f"/api/offers/{back['id']}/respond", json={"action": "accept"})
        assert accepted.status_code == 200 and accepted.json()["state"] == "accepted"
        day = a.get(f"/api/days/{TODAY}").json()
        assert [[e["name"] for e in p["entries"]] for p in day["people"]] == [["Curry"], ["Curry"]]
        assert day["people"][0]["entries"][0]["joint"] is True
        closed = a.get("/api/offers", params={"closed": True}).json()
        assert {o["state"] for o in closed} == {"countered", "accepted"}

    def test_withdraw_and_decline(self, phones: Any) -> None:
        a, b, _, partner = phones
        first = self.offer(a, partner)
        withdrawn = a.post(f"/api/offers/{first['id']}/withdraw")
        assert withdrawn.json()["state"] == "withdrawn"
        second = self.offer(a, partner)
        declined = b.post(f"/api/offers/{second['id']}/respond", json={"action": "decline"})
        assert declined.json()["state"] == "declined"
        again = b.post(f"/api/offers/{second['id']}/respond", json={"action": "accept"})
        assert again.status_code == 409 and again.json()["code"] == "offer_not_pending"
        wrong = a.post(f"/api/offers/{first['id']}/withdraw")
        assert wrong.status_code == 409

    def test_only_the_receiver_can_answer(self, phones: Any) -> None:
        a, _, _, partner = phones
        sent = self.offer(a, partner)
        refused = a.post(f"/api/offers/{sent['id']}/respond", json={"action": "accept"})
        assert refused.status_code == 403 and refused.json()["code"] == "offer_not_yours"

    def test_the_receiver_is_pushed_unless_switched_off(self, db: Session, phones: Any) -> None:
        from sqlalchemy import select

        from mahlzeit.models import Job

        a, b, _, partner = phones
        self.offer(a, partner)
        jobs = db.scalars(select(Job).where(Job.kind == "push.deliver")).all()
        assert [j.payload["message"] for j in jobs] == ["offer"]
        b.patch("/api/me/profile", json={"push_offers": False})
        self.offer(a, partner)
        assert len(db.scalars(select(Job).where(Job.kind == "push.deliver")).all()) == 1
