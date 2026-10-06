from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mahlzeit.db import Base
from mahlzeit.models._types import OptTimestamp, Timestamp, UuidPk


class ConnectorToken(Base):
    """The secret in a person's connector URL. Stored hashed, shown once, never logged."""

    __tablename__ = "connector_token"

    id: Mapped[UuidPk]
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[Timestamp]
    last_used_at: Mapped[OptTimestamp]
    revoked_at: Mapped[OptTimestamp]


class OffCache(Base):
    """Open Food Facts product reads, cached so a barcode is fetched once."""

    __tablename__ = "off_cache"

    code: Mapped[str] = mapped_column(String(14), primary_key=True)
    found: Mapped[bool]
    payload: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RateWindow(Base):
    """Fixed one-minute windows counting calls to an outside service, shared by all processes."""

    __tablename__ = "rate_window"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
