"""The shopping list over HTTP: the same calls the app makes, online and after being offline."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from mahlzeit.ids import uuid7
from tests import factories


def test_two_phones_share_one_list(db: Session, make_client: Callable[[], TestClient]) -> None:
    jonas, partner = factories.household(db)
    a, b = make_client(), make_client()
    factories.signed_in(a, jonas)
    factories.signed_in(b, partner)
    milk, bread = str(uuid7()), str(uuid7())
    response = a.post(
        "/api/list/ops",
        json={
            "ops": [
                {
                    "kind": "add",
                    "id": milk,
                    "fields": {"text": "2 Milch", "category": "dairy_eggs"},
                },
                {"kind": "add", "id": bread, "fields": {"text": "Brot", "category": "bakery"}},
            ]
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [r["status"] for r in body["results"]] == ["applied", "applied"]
    assert [(i["text"], i["quantity"]) for i in body["list"]["items"]] == [
        ("Brot", None),
        ("Milch", "2"),
    ]

    seen = b.get("/api/list").json()
    assert {i["id"] for i in seen["items"]} == {milk, bread}
    assert [s["key"] for s in seen["stores"]][:3] == ["aldi", "lidl", "edeka"]

    # The partner shops offline, then sends the queued changes, twice (a lost answer).
    at = seen["server_time"]
    queued = {
        "ops": [
            {
                "kind": "update",
                "id": milk,
                "at": at,
                "fields": {"checked": True},
            },
            {"kind": "remove", "id": bread, "at": at},
        ]
    }
    first = b.post("/api/list/ops", json=queued).json()
    second = b.post("/api/list/ops", json=queued).json()
    assert [r["status"] for r in first["results"]] == ["applied", "applied"]
    assert [r["status"] for r in second["results"]] == ["unchanged", "removed"]
    items = a.get("/api/list").json()["items"]
    assert [(i["text"], i["checked"]) for i in items] == [("Milch", True)]

    history = a.get("/api/list/history").json()
    assert {h["text"] for h in history} == {"Milch", "Brot"}


def test_custom_stores(db: Session, make_client: Callable[[], TestClient]) -> None:
    jonas, _ = factories.household(db)
    client = make_client()
    factories.signed_in(client, jonas)
    created = client.post("/api/stores", json={"name": "Wochenmarkt"})
    assert created.status_code == 201
    store = created.json()
    assert (store["name"], store["custom"]) == ("Wochenmarkt", True)
    again = client.post("/api/stores", json={"name": "wochenmarkt"})
    assert (again.status_code, again.json()["code"]) == (409, "store_name_taken")
    assert client.delete(f"/api/stores/{store['id']}").status_code == 204


def test_another_households_list_stays_hidden(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    mine, _ = factories.household(db)
    theirs, _ = factories.household(db)
    other = make_client()
    factories.signed_in(other, theirs)
    secret = str(uuid7())
    other.post(
        "/api/list/ops", json={"ops": [{"kind": "add", "id": secret, "fields": {"text": "x"}}]}
    )
    client = make_client()
    factories.signed_in(client, mine)
    assert client.get("/api/list").json()["items"] == []
    assert client.get("/api/list/history").json() == []
    tried = client.post(
        "/api/list/ops",
        json={"ops": [{"kind": "update", "id": secret, "fields": {"checked": True}}]},
    ).json()
    assert tried["results"][0]["status"] == "not_found"
