"""A small job queue in Postgres. Workers claim rows with FOR UPDATE SKIP LOCKED."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from mahlzeit import clock
from mahlzeit.ids import uuid7
from mahlzeit.models import Job

STALE_AFTER = timedelta(minutes=10)


def enqueue(
    db: Session,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    run_at: datetime | None = None,
    dedupe_key: str | None = None,
    max_attempts: int = 5,
) -> None:
    """Add a job to the current transaction. A job with an existing dedupe key is skipped."""
    now = clock.now()
    stmt = (
        insert(Job)
        .values(
            id=uuid7(),
            kind=kind,
            payload=payload or {},
            status="queued",
            run_at=run_at or now,
            attempts=0,
            max_attempts=max_attempts,
            dedupe_key=dedupe_key,
            created_at=now,
        )
        .on_conflict_do_nothing(index_elements=["dedupe_key"])
    )
    db.execute(stmt)


def claim(db: Session) -> Job | None:
    """Claim the next due job and commit, so other workers skip it."""
    now = clock.now()
    db.execute(
        update(Job)
        .where(Job.status == "running", Job.locked_at < now - STALE_AFTER)
        .values(status="queued", locked_at=None)
    )
    job = db.scalars(
        select(Job)
        .where(Job.status == "queued", Job.run_at <= now)
        .order_by(Job.run_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if job is None:
        db.commit()
        return None
    job.status = "running"
    job.locked_at = now
    job.attempts += 1
    db.commit()
    return job


def complete(db: Session, job: Job) -> None:
    job.status = "done"
    job.finished_at = clock.now()
    job.locked_at = None
    db.commit()


def fail(db: Session, job: Job, error: str) -> None:
    """Retry with exponential backoff, or give up after max_attempts."""
    job.last_error = error[:2000]
    job.locked_at = None
    if job.attempts >= job.max_attempts:
        job.status = "failed"
        job.finished_at = clock.now()
    else:
        job.status = "queued"
        job.run_at = clock.now() + timedelta(seconds=30 * 2 ** (job.attempts - 1))
    db.commit()
