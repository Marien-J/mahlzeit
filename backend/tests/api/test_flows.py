from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from mahlzeit.models import ChangeRecord, Job
from mahlzeit.services import invites
from tests import factories
from tests.factories import PASSWORD

Clients = Callable[[], TestClient]


class TestSystem:
    def test_health(self, make_client: Clients) -> None:
        body = make_client().get("/api/health").json()
        assert body["status"] == body["database"] == "ok"

    def test_config_exposes_only_public_values(self, make_client: Clients) -> None:
        body = make_client().get("/api/config").json()
        assert body["languages"] == ["de", "en", "nl"]
        assert body["email_reset"] is False
        assert body["push_public_key"]
        assert set(body) == {"version", "languages", "email_reset", "push_public_key"}


class TestLogin:
    def test_cookie_is_http_only_and_lax(self, db: Session, make_client: Clients) -> None:
        jonas, _ = factories.household(db)
        response = make_client().post(
            "/api/auth/login", json={"email": jonas.email, "password": PASSWORD}
        )
        cookie = response.headers["set-cookie"].lower()
        assert "mahlzeit_session=" in cookie
        assert "httponly" in cookie and "samesite=lax" in cookie
        assert "secure" not in cookie  # BASE_URL is http in tests

    def test_cookie_is_secure_behind_https(
        self, db: Session, make_client: Clients, settings
    ) -> None:
        settings(base_url="https://mahlzeit.example.org")
        jonas, _ = factories.household(db)
        response = make_client().post(
            "/api/auth/login", json={"email": jonas.email, "password": PASSWORD}
        )
        assert "secure" in response.headers["set-cookie"].lower()

    def test_bad_credentials(self, db: Session, make_client: Clients) -> None:
        jonas, _ = factories.household(db)
        response = make_client().post(
            "/api/auth/login", json={"email": jonas.email, "password": "nope"}
        )
        assert response.status_code == 401
        assert response.json() == {"code": "invalid_credentials", "detail": {}}

    def test_rate_limit_status(self, db: Session, make_client: Clients) -> None:
        jonas, _ = factories.household(db)
        client = make_client()
        for _ in range(5):
            client.post("/api/auth/login", json={"email": jonas.email, "password": "nope"})
        response = client.post("/api/auth/login", json={"email": jonas.email, "password": PASSWORD})
        assert response.status_code == 429
        assert response.json()["code"] == "too_many_attempts"

    def test_me_and_logout(self, db: Session, make_client: Clients) -> None:
        jonas, _ = factories.household(db)
        client = make_client()
        csrf = factories.signed_in(client, jonas)
        me = client.get("/api/auth/me").json()
        assert me["user"]["display_name"] == "Jonas"
        assert me["csrf_token"] == csrf
        assert "password_hash" not in me["user"]
        assert client.post("/api/auth/logout").status_code == 204
        assert client.get("/api/auth/me").status_code == 401

    def test_validation_errors_are_codes(self, make_client: Clients) -> None:
        response = make_client().post("/api/auth/login", json={"email": 5})
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"

    def test_allowed_origin_passes(self, db: Session, make_client: Clients) -> None:
        jonas, _ = factories.household(db)
        response = make_client().post(
            "/api/auth/login",
            json={"email": jonas.email, "password": PASSWORD},
            headers={"Origin": "http://localhost"},
        )
        assert response.status_code == 200


class TestJoin:
    def test_partner_joins_by_link_and_both_see_each_other(
        self, db: Session, make_client: Clients
    ) -> None:
        (jonas,) = factories.household(db, "Jonas")
        owner = make_client()
        factories.signed_in(owner, jonas)
        issued = owner.post("/api/household/invites", json={"note": "for Sam"})
        assert issued.status_code == 201
        body = issued.json()
        token = body["link"].rsplit("/", 1)[1]
        assert body["link"].startswith("http://localhost/join/")
        assert len(body["code"]) == 9 and body["code"][4] == "-"

        partner = make_client()
        preview = partner.get(f"/api/invites/{token}").json()
        assert preview["inviter_name"] == "Jonas" and preview["status"] == "pending"
        joined = partner.post(
            "/api/invites/accept",
            json={
                "key": body["code"].lower(),
                "email": "sam@example.org",
                "password": PASSWORD,
                "display_name": "Sam",
                "language": "nl",
                "time_zone": "Europe/Amsterdam",
            },
        )
        assert joined.status_code == 201, joined.text
        assert joined.json()["user"]["language"] == "nl"
        assert "mahlzeit_session=" in joined.headers["set-cookie"]
        partner.headers["X-CSRF-Token"] = joined.json()["csrf_token"]

        names = {m["display_name"] for m in partner.get("/api/household").json()["members"]}
        assert names == {"Jonas", "Sam"}
        assert owner.get("/api/household/invites").json() == []

    def test_used_invite_answers_409(self, db: Session, make_client: Clients) -> None:
        (jonas,) = factories.household(db, "Jonas")
        issued = invites.create_partner_invite(db, jonas.actor)
        payload = {
            "key": issued.token,
            "email": "a@example.org",
            "password": PASSWORD,
            "display_name": "A",
            "language": "de",
            "time_zone": "Europe/Berlin",
        }
        assert make_client().post("/api/invites/accept", json=payload).status_code == 201
        again = make_client().post(
            "/api/invites/accept", json={**payload, "email": "b@example.org"}
        )
        assert again.status_code == 409
        assert again.json()["code"] == "invite_used"

    def test_revoke(self, db: Session, make_client: Clients) -> None:
        jonas, _ = factories.household(db)
        client = make_client()
        factories.signed_in(client, jonas)
        invite_id = client.post("/api/household/invites", json={}).json()["invite"]["id"]
        assert client.delete(f"/api/household/invites/{invite_id}").status_code == 204
        assert client.get("/api/household/invites").json() == []


class TestSettings:
    def test_switch_language(self, db: Session, make_client: Clients) -> None:
        jonas, _ = factories.household(db)
        client = make_client()
        factories.signed_in(client, jonas)
        response = client.patch("/api/me", json={"language": "en"})
        assert response.json()["user"]["language"] == "en"
        assert client.get("/api/auth/me").json()["user"]["language"] == "en"
        change = db.scalars(
            select(ChangeRecord).where(
                ChangeRecord.entity == "user", ChangeRecord.action == "updated"
            )
        ).one()
        assert change.client == "ui"

    def test_unknown_language_is_rejected_by_schema(
        self, db: Session, make_client: Clients
    ) -> None:
        jonas, _ = factories.household(db)
        client = make_client()
        factories.signed_in(client, jonas)
        assert client.patch("/api/me", json={"language": "fr"}).status_code == 422

    def test_sharing_switches(self, db: Session, make_client: Clients) -> None:
        jonas, _ = factories.household(db)
        client = make_client()
        factories.signed_in(client, jonas)
        profile = client.patch(
            "/api/me/profile", json={"show_body": True, "start_screen": "list"}
        ).json()["profile"]
        assert profile["show_body"] is True and profile["start_screen"] == "list"

    def test_rename_household(self, db: Session, make_client: Clients) -> None:
        _, partner = factories.household(db)
        client = make_client()
        factories.signed_in(client, partner)
        assert client.patch("/api/household", json={"name": "Zuhause"}).json()["name"] == "Zuhause"

    def test_change_password(self, db: Session, make_client: Clients) -> None:
        jonas, _ = factories.household(db)
        client = make_client()
        factories.signed_in(client, jonas)
        bad = client.post(
            "/api/auth/password", json={"current_password": "x", "new_password": "new password 1"}
        )
        assert bad.status_code == 422 and bad.json()["code"] == "current_password_wrong"
        ok = client.post(
            "/api/auth/password",
            json={"current_password": PASSWORD, "new_password": "new password 1"},
        )
        assert ok.status_code == 204
        assert client.get("/api/auth/me").status_code == 200


class TestPasswordReset:
    def test_request_is_accepted_either_way(self, make_client: Clients) -> None:
        response = make_client().post(
            "/api/auth/password-reset/request", json={"email": "x@example.org"}
        )
        assert response.status_code == 202

    def test_full_reset(self, db: Session, make_client: Clients, settings) -> None:
        settings(smtp_host="smtp.test", smtp_from="mahlzeit@example.org")
        jonas, _ = factories.household(db)
        client = make_client()
        client.post("/api/auth/password-reset/request", json={"email": jonas.email})
        job = db.scalars(select(Job).where(Job.kind == "email.password_reset")).one()
        token = job.payload["link"].rsplit("/", 1)[1]
        assert (
            client.post(
                "/api/auth/password-reset/confirm",
                json={"token": token, "password": "brand new one"},
            ).status_code
            == 204
        )
        login = client.post(
            "/api/auth/login", json={"email": jonas.email, "password": "brand new one"}
        )
        assert login.status_code == 200
        reused = client.post(
            "/api/auth/password-reset/confirm", json={"token": token, "password": "brand new two"}
        )
        assert reused.json()["code"] == "reset_token_invalid"


class TestPush:
    SUB: ClassVar[dict[str, object]] = {
        "endpoint": "https://push.example/abc",
        "keys": {"p256dh": "BPk", "auth": "a"},
    }

    def test_subscribe_status_test_unsubscribe(self, db: Session, make_client: Clients) -> None:
        jonas, _ = factories.household(db)
        client = make_client()
        factories.signed_in(client, jonas)
        assert client.post("/api/push/test").json()["code"] == "push_no_subscription"
        assert client.post("/api/push/subscriptions", json=self.SUB).status_code == 204
        status = client.get("/api/push").json()
        assert status["configured"] and status["devices"] == 1 and status["public_key"]
        assert client.post("/api/push/test").status_code == 202
        assert db.scalars(select(Job).where(Job.kind == "push.deliver")).one().payload[
            "user_id"
        ] == str(jonas.user.id)
        assert (
            client.post(
                "/api/push/subscriptions/remove", json={"endpoint": self.SUB["endpoint"]}
            ).status_code
            == 204
        )
        assert client.get("/api/push").json()["devices"] == 0

    def test_not_configured(self, db: Session, make_client: Clients, settings) -> None:
        settings(vapid_public_key="")
        jonas, _ = factories.household(db)
        client = make_client()
        factories.signed_in(client, jonas)
        assert client.get("/api/push").json() == {
            "configured": False,
            "public_key": None,
            "devices": 0,
        }
        assert client.post("/api/push/subscriptions", json=self.SUB).status_code == 409
