from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from mahlzeit.db import Base
from mahlzeit.models._types import OptTimestamp, Timestamp, UuidPk


class PushSubscription(Base):
    """A browser push subscription. Endpoint and keys are encrypted at rest."""

    __tablename__ = "push_subscription"

    id: Mapped[UuidPk]
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True
    )
    endpoint_hash: Mapped[str] = mapped_column(String(64), unique=True)
    subscription_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    user_agent: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[Timestamp]
    last_success_at: Mapped[OptTimestamp]
