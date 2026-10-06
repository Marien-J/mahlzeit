"""Web push delivery with VAPID."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any, Protocol

from mahlzeit.config import get_settings


class Delivery(StrEnum):
    SENT = "sent"
    GONE = "gone"  # the subscription expired or was revoked; delete it


class PushSender(Protocol):
    def send(self, subscription: dict[str, Any], message: dict[str, Any]) -> Delivery: ...


class WebPushSender:
    def send(self, subscription: dict[str, Any], message: dict[str, Any]) -> Delivery:
        from pywebpush import WebPushException, webpush

        s = get_settings()
        try:
            webpush(
                subscription_info=subscription,
                data=json.dumps(message),
                vapid_private_key=s.vapid_private_key,
                vapid_claims={"sub": s.vapid_contact},
                ttl=24 * 3600,
                timeout=15,
            )
        except WebPushException as err:
            status = err.response.status_code if err.response is not None else None
            if status in (404, 410):
                return Delivery.GONE
            raise RuntimeError(f"push failed with status {status}") from None
        return Delivery.SENT
