"""Every endpoint, walked from the OpenAPI schema: authentication, CSRF and household isolation.

Adding an endpoint makes these tests fail until it is classified here, so no route ships unchecked.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from mahlzeit.domain.day import Slot
from mahlzeit.main import app
from mahlzeit.services import day, invites, items, saved_meals, shopping
from mahlzeit.services.day import ComponentInput, EntryInput
from mahlzeit.services.items import ItemInput
from mahlzeit.services.saved_meals import Ingredient
from tests import factories

UNSAFE = {"post", "put", "patch", "delete"}

# Reachable without signing in. Everything else must answer 401 without a session.
PUBLIC = {
    ("get", "/api/health"),
    ("get", "/api/config"),
    ("post", "/api/auth/login"),
    ("post", "/api/auth/password-reset/request"),
    ("post", "/api/auth/password-reset/confirm"),
    ("get", "/api/invites/{key}"),
    ("post", "/api/invites/accept"),
}


def _operations() -> list[tuple[str, str]]:
    schema = app.openapi()
    return sorted(
        (method, path)
        for path, item in schema["paths"].items()
        for method in item
        if method in {"get", *UNSAFE}
    )


OPERATIONS = _operations()
PRIVATE = [op for op in OPERATIONS if op not in PUBLIC]


def _fill(path: str) -> str:
    return re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)


def test_schema_lists_operations() -> None:
    assert len(OPERATIONS) >= 20
    assert set(OPERATIONS) >= PUBLIC, "a public route was renamed or removed"


@pytest.mark.parametrize(("method", "path"), PRIVATE)
def test_requires_a_session(make_client: Callable[[], TestClient], method: str, path: str) -> None:
    response = make_client().request(method, _fill(path), json={})
    assert response.status_code == 401, response.text
    assert response.json()["code"] == "not_authenticated"


@pytest.mark.parametrize(("method", "path"), [op for op in PRIVATE if op[0] in UNSAFE])
def test_unsafe_requests_require_the_csrf_token(
    db: Session, make_client: Callable[[], TestClient], method: str, path: str
) -> None:
    jonas, _ = factories.household(db)
    client = make_client()
    factories.signed_in(client, jonas)
    del client.headers["X-CSRF-Token"]
    response = client.request(method, _fill(path), json={})
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "csrf_failed"
    client.headers["X-CSRF-Token"] = "forged"
    assert client.request(method, _fill(path), json={}).status_code == 403


@pytest.mark.parametrize(("method", "path"), [op for op in OPERATIONS if op[0] in UNSAFE])
def test_foreign_origins_are_rejected(
    make_client: Callable[[], TestClient], method: str, path: str
) -> None:
    response = make_client().request(
        method, _fill(path), json={}, headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403
    assert response.json()["code"] == "origin_not_allowed"


# --- Household isolation --------------------------------------------------------------------
# Every route with a path parameter that names a household-owned row needs a case here.

CrossCase = Callable[[Session, factories.Member], tuple[dict[str, Any], dict[str, Any]]]
"""Builds a row in another household; returns (path params, valid request body)."""


def _invite(db: Session, other: factories.Member) -> tuple[dict[str, Any], dict[str, Any]]:
    return {"invite_id": invites.create_partner_invite(db, other.actor).invite.id}, {}


def _item(db: Session, other: factories.Member) -> tuple[dict[str, Any], dict[str, Any]]:
    item = items.create(db, other.actor, ItemInput(names={"de": "Geheim"}))
    return {"item_id": item.id}, {"names": {"de": "Gestohlen"}, "on": True}


def _entry(db: Session, other: factories.Member) -> tuple[dict[str, Any], dict[str, Any]]:
    entry = day.log_food(
        db,
        other.actor,
        EntryInput(
            day=date(2026, 10, 1),
            slot=Slot.LUNCH,
            components=[ComponentInput(quick_name="Soup", kcal=300)],
        ),
    )
    return {"entry_id": entry.id}, {"state": "skipped", "day": "2026-10-02", "name": "x"}


def _saved_meal(db: Session, other: factories.Member) -> tuple[dict[str, Any], dict[str, Any]]:
    oats = factories.generic(db, other.actor, "C133000")
    meal = saved_meals.create(db, other.actor, name="Theirs", ingredients=[Ingredient(oats.id, 50)])
    return {"meal_id": meal.id}, {"name": "Mine now"}


def _store(db: Session, other: factories.Member) -> tuple[dict[str, Any], dict[str, Any]]:
    return {"store_id": shopping.create_store(db, other.actor, "Hofladen").id}, {}


CROSS_HOUSEHOLD: dict[tuple[str, str], CrossCase] = {
    ("delete", "/api/household/invites/{invite_id}"): _invite,
    ("get", "/api/items/{item_id}"): _item,
    ("put", "/api/items/{item_id}"): _item,
    ("put", "/api/items/{item_id}/favourite"): _item,
    ("patch", "/api/entries/{entry_id}"): _entry,
    ("delete", "/api/entries/{entry_id}"): _entry,
    ("post", "/api/entries/{entry_id}/state"): _entry,
    ("post", "/api/entries/{entry_id}/copy"): _entry,
    ("post", "/api/entries/{entry_id}/save-as-meal"): _entry,
    ("patch", "/api/saved-meals/{meal_id}"): _saved_meal,
    ("delete", "/api/saved-meals/{meal_id}"): _saved_meal,
    ("delete", "/api/stores/{store_id}"): _store,
}

# Path parameters that are not household-owned ids: lookups by secret key or by value,
# answered for the caller's own household only (tested in test_flows_m1.py).
NOT_SCOPED = {
    ("get", "/api/invites/{key}"),
    ("get", "/api/barcodes/{code}"),
    ("get", "/api/days/{day_}"),
    ("post", "/api/days/{day_}/copy"),
    ("put", "/api/days/{day_}/day-type"),
}


def test_every_parametrised_route_has_a_cross_household_case() -> None:
    parametrised = {op for op in OPERATIONS if "{" in op[1]}
    assert parametrised - NOT_SCOPED == set(CROSS_HOUSEHOLD)


@pytest.mark.parametrize(("method", "path"), sorted(CROSS_HOUSEHOLD))
def test_cannot_reach_another_households_rows(
    db: Session, make_client: Callable[[], TestClient], method: str, path: str
) -> None:
    mine, _ = factories.household(db)
    theirs, _ = factories.household(db)
    params, body = CROSS_HOUSEHOLD[(method, path)](db, theirs)
    client = make_client()
    factories.signed_in(client, mine)
    response = client.request(method, path.format(**params), json=body if method != "get" else None)
    assert response.status_code == 404, response.text


def test_household_and_me_only_show_own_data(
    db: Session, make_client: Callable[[], TestClient]
) -> None:
    mine, _ = factories.household(db, "Mine", "MyPartner")
    theirs, _ = factories.household(db, "Theirs", "TheirPartner")
    invites.create_partner_invite(db, theirs.actor)
    client = make_client()
    factories.signed_in(client, mine)
    household = client.get("/api/household").json()
    assert {m["display_name"] for m in household["members"]} == {"Mine", "MyPartner"}
    assert client.get("/api/household/invites").json() == []
    assert client.get("/api/auth/me").json()["user"]["id"] == str(mine.user.id)
