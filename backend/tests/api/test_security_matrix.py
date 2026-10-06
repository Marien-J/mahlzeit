"""Every endpoint, walked from the OpenAPI schema: authentication, CSRF and household isolation.

Adding an endpoint makes these tests fail until it is classified here, so no route ships unchecked.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from mahlzeit.main import app
from mahlzeit.services import invites
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

CrossCase = Callable[[Session, factories.Member], dict[str, Any]]


def _other_households_invite(db: Session, other: factories.Member) -> dict[str, Any]:
    return {"invite_id": invites.create_partner_invite(db, other.actor).invite.id}


CROSS_HOUSEHOLD: dict[tuple[str, str], CrossCase] = {
    ("delete", "/api/household/invites/{invite_id}"): _other_households_invite,
}

# Path parameters that are not household-scoped ids (public lookups by secret key).
NOT_SCOPED = {("get", "/api/invites/{key}")}


def test_every_parametrised_route_has_a_cross_household_case() -> None:
    parametrised = {op for op in OPERATIONS if "{" in op[1]}
    assert parametrised - NOT_SCOPED == set(CROSS_HOUSEHOLD)


@pytest.mark.parametrize(("method", "path"), sorted(CROSS_HOUSEHOLD))
def test_cannot_reach_another_households_rows(
    db: Session, make_client: Callable[[], TestClient], method: str, path: str
) -> None:
    mine, _ = factories.household(db)
    theirs, _ = factories.household(db)
    params = CROSS_HOUSEHOLD[(method, path)](db, theirs)
    client = make_client()
    factories.signed_in(client, mine)
    response = client.request(method, path.format(**params), json={})
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
