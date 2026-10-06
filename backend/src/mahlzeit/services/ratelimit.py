"""Fixed-window rate limits for calls to outside services, shared by every process."""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from mahlzeit import clock
from mahlzeit.domain.errors import RateLimited
from mahlzeit.models import RateWindow


def take(db: Session, key: str, *, per_minute: int) -> None:
    """Count one call; raise RateLimited when this minute's budget is spent. Commits."""
    now = clock.now()
    window = now.replace(second=0, microsecond=0)
    stmt = (
        insert(RateWindow)
        .values(key=key, window_start=window, count=1)
        .on_conflict_do_update(
            index_elements=["key", "window_start"], set_={"count": RateWindow.count + 1}
        )
        .returning(RateWindow.count)
    )
    count = db.execute(stmt).scalar_one()
    db.commit()
    if count > per_minute:
        raise RateLimited("external_rate_limited", seconds=60 - now.second)
