"""The worker process: schedules recurring jobs and runs queued ones."""

from __future__ import annotations

import logging
import signal
import time
from types import FrameType

from sqlalchemy.orm import Session

from mahlzeit import clock
from mahlzeit.config import get_settings
from mahlzeit.db import new_session
from mahlzeit.jobs.registry import HANDLERS, RECURRING, Deps
from mahlzeit.services import queue

log = logging.getLogger("mahlzeit.worker")


def schedule_recurring(db: Session) -> None:
    """Enqueue each recurring job once per interval. The dedupe key makes this safe to repeat."""
    now = clock.now().timestamp()
    for kind, interval in RECURRING.items():
        seconds = int(interval.total_seconds())
        bucket = int(now // seconds)
        queue.enqueue(db, kind, dedupe_key=f"{kind}:{bucket}")
    db.commit()


def run_one(db: Session, deps: Deps) -> bool:
    """Claim and run one due job. Returns False when the queue is empty."""
    job = queue.claim(db)
    if job is None:
        return False
    handler = HANDLERS.get(job.kind)
    try:
        if handler is None:
            raise LookupError(f"no handler for job kind {job.kind!r}")
        handler(db, job.payload, deps)
    except Exception as err:
        db.rollback()
        log.warning("job %s (%s) failed: %s", job.id, job.kind, type(err).__name__)
        queue.fail(db, job, f"{type(err).__name__}: {err}")
    else:
        queue.complete(db, job)
    return True


def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    stopping = False

    def stop(signum: int, frame: FrameType | None) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    deps = Deps()
    log.info("worker started")
    last_schedule = 0.0
    while not stopping:
        with new_session() as db:
            if time.monotonic() - last_schedule > 30:
                schedule_recurring(db)
                last_schedule = time.monotonic()
            while not stopping and run_one(db, deps):
                pass
        time.sleep(settings.worker_poll_seconds)
    log.info("worker stopped")


if __name__ == "__main__":
    main()
