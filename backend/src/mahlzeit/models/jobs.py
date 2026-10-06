from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mahlzeit.db import Base
from mahlzeit.models._types import OptTimestamp, Timestamp, UuidPk


class Job(Base):
    """A queued unit of background work. Workers claim rows with FOR UPDATE SKIP LOCKED."""

    __tablename__ = "job"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="status"),
        Index("ix_job_status_run_at", "status", "run_at"),
    )

    id: Mapped[UuidPk]
    kind: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(10), default="queued")
    run_at: Mapped[Timestamp]
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    dedupe_key: Mapped[str | None] = mapped_column(String(120), unique=True)
    locked_at: Mapped[OptTimestamp]
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[Timestamp]
    finished_at: Mapped[OptTimestamp]
