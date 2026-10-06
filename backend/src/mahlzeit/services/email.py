"""Outgoing emails. Sent by the worker, in the recipient's language."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from mahlzeit.config import get_settings
from mahlzeit.i18n import t
from mahlzeit.mail import Mailer
from mahlzeit.models import User


def send_password_reset(db: Session, payload: dict[str, Any], mailer: Mailer) -> None:
    user = db.get(User, uuid.UUID(payload["user_id"]))
    if user is None:
        return
    lang = user.language
    mailer.send(
        to=user.email,
        subject=t(lang, "email.password_reset.subject"),
        body=t(
            lang,
            "email.password_reset.body",
            name=user.display_name,
            link=payload["link"],
            minutes=get_settings().reset_token_minutes,
        ),
    )
