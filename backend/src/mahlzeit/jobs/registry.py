"""Job kinds, their service handlers and the recurring schedule."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from mahlzeit.mail import Mailer, SmtpMailer
from mahlzeit.push import PushSender, WebPushSender
from mahlzeit.services import email, maintenance, push


@dataclass
class Deps:
    """Outside-world adapters, swapped for fakes in tests."""

    mailer: Mailer = field(default_factory=SmtpMailer)
    push_sender: PushSender = field(default_factory=WebPushSender)


Handler = Callable[[Session, dict[str, Any], Deps], object]

HANDLERS: dict[str, Handler] = {
    "email.password_reset": lambda db, p, d: email.send_password_reset(db, p, d.mailer),
    "push.deliver": lambda db, p, d: push.deliver(db, p, d.push_sender),
    "maintenance.purge": lambda db, p, d: maintenance.purge(db),
}

RECURRING: dict[str, timedelta] = {
    "maintenance.purge": timedelta(hours=1),
}
