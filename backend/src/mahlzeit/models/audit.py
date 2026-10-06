from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mahlzeit.db import Base
from mahlzeit.models._types import OptTimestamp, Timestamp, UuidPk


class ChangeRecord(Base):
    """Who changed what, through which client. Written for every domain write."""

    __tablename__ = "change_record"
    __table_args__ = (
        CheckConstraint("client IN ('ui', 'connector', 'assistant', 'job', 'cli')", name="client"),
        Index("ix_change_record_household_created", "household_id", "created_at"),
    )

    id: Mapped[UuidPk]
    household_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL")
    )
    client: Mapped[str] = mapped_column(String(10))
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[uuid.UUID | None]
    action: Mapped[str] = mapped_column(String(40))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[Timestamp]
    undone_at: Mapped[OptTimestamp]
