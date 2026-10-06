import json
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from mahlzeit.domain.errors import Conflict, Invalid
from mahlzeit.models import Job, PushSubscription
from mahlzeit.push import Delivery
from mahlzeit.services import profiles, push
from tests import factories

ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc123"


class FakeSender:
    def __init__(self, gone: set[str] | None = None) -> None:
        self.sent: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.gone = gone or set()

    def send(self, subscription: dict[str, Any], message: dict[str, Any]) -> Delivery:
        self.sent.append((subscription, message))
        return Delivery.GONE if subscription["endpoint"] in self.gone else Delivery.SENT


def _sub(db: Session, member: factories.Member, endpoint: str = ENDPOINT) -> PushSubscription:
    return push.subscribe(db, member.actor, endpoint=endpoint, p256dh="BPk-key", auth="auth-secret")


class TestSubscribe:
    def test_stores_endpoint_and_keys_encrypted(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        sub = _sub(db, jonas)
        assert b"fcm.googleapis.com" not in sub.subscription_encrypted
        assert b"auth-secret" not in sub.subscription_encrypted

    def test_rejects_non_https_endpoints(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        with pytest.raises(Invalid):
            _sub(db, jonas, endpoint="http://evil.example/push")

    def test_device_moves_to_whoever_signs_in(self, db: Session) -> None:
        jonas, partner = factories.household(db)
        _sub(db, jonas)
        _sub(db, partner)
        assert push.count(db, jonas.actor) == 0
        assert push.count(db, partner.actor) == 1

    def test_keeps_ten_devices(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        for i in range(12):
            _sub(db, jonas, endpoint=f"{ENDPOINT}/{i}")
        assert push.count(db, jonas.actor) == 10

    def test_unsubscribe_ignores_other_users_devices(self, db: Session) -> None:
        jonas, partner = factories.household(db)
        _sub(db, jonas)
        push.unsubscribe(db, partner.actor, endpoint=ENDPOINT)
        assert push.count(db, jonas.actor) == 1
        push.unsubscribe(db, jonas.actor, endpoint=ENDPOINT)
        assert push.count(db, jonas.actor) == 0

    def test_not_configured(self, db: Session, settings) -> None:
        jonas, _ = factories.household(db)
        settings(vapid_private_key="")
        with pytest.raises(Conflict) as err:
            _sub(db, jonas)
        assert err.value.code == "push_not_configured"


class TestDelivery:
    def test_test_message_needs_a_device(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        with pytest.raises(Conflict) as err:
            push.send_test(db, jonas.actor)
        assert err.value.code == "push_no_subscription"

    def test_test_message_is_queued_then_delivered_in_users_language(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        profiles.update_user(db, jonas.actor, language="nl")
        _sub(db, jonas)
        push.send_test(db, jonas.actor)
        job = db.scalars(select(Job).where(Job.kind == "push.deliver")).one()
        sender = FakeSender()
        assert push.deliver(db, job.payload, sender) == 1
        (subscription, message) = sender.sent[0]
        assert subscription == {
            "endpoint": ENDPOINT,
            "keys": {"p256dh": "BPk-key", "auth": "auth-secret"},
        }
        assert message["body"] == "Meldingen werken op dit apparaat."
        assert message["url"] == "/settings"
        json.dumps(message)

    def test_gone_subscriptions_are_deleted(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        _sub(db, jonas, f"{ENDPOINT}/old")
        _sub(db, jonas, f"{ENDPOINT}/new")
        sent = push.deliver(
            db,
            {"user_id": str(jonas.user.id), "message": "test"},
            FakeSender(gone={f"{ENDPOINT}/old"}),
        )
        assert sent == 1
        assert push.count(db, jonas.actor) == 1
