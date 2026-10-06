"""Live updates: one server-sent event stream per signed-in app, scoped to its household.

Each app process keeps one Postgres connection that LISTENs on the events channel
(services/events.py) and hands every notification to the streams of that household. The
event only says what kind of thing changed; the app refetches it through the normal API,
so permissions and visibility stay in one place.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable

import psycopg
from sqlalchemy.engine import make_url

from mahlzeit.services.events import CHANNEL

log = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 15.0
RECHECK_SECONDS = 60.0
QUEUE_SIZE = 100
RESYNC = json.dumps({"entity": "*"})


class Broker:
    """Fans notifications out to the open streams of each household in this process."""

    def __init__(self) -> None:
        self._streams: dict[uuid.UUID, set[asyncio.Queue[str]]] = defaultdict(set)
        self.listening = False

    def subscribe(self, household_id: uuid.UUID) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._streams[household_id].add(queue)
        return queue

    def unsubscribe(self, household_id: uuid.UUID, queue: asyncio.Queue[str]) -> None:
        streams = self._streams.get(household_id)
        if streams is not None:
            streams.discard(queue)
            if not streams:
                del self._streams[household_id]

    def subscribers(self, household_id: uuid.UUID) -> int:
        return len(self._streams.get(household_id, ()))

    @staticmethod
    def _put(queue: asyncio.Queue[str], data: str) -> None:
        try:
            queue.put_nowait(data)
        except asyncio.QueueFull:
            # A stream that cannot keep up is told to refetch everything instead.
            with contextlib.suppress(asyncio.QueueEmpty):
                while True:
                    queue.get_nowait()
            queue.put_nowait(RESYNC)

    def dispatch(self, raw: str) -> None:
        try:
            note = json.loads(raw)
            household_id = uuid.UUID(note["household"])
        except (ValueError, KeyError, TypeError):
            log.warning("ignoring a malformed event notification")
            return
        data = json.dumps({"entity": note.get("entity"), "user": note.get("user")})
        for queue in list(self._streams.get(household_id, ())):
            self._put(queue, data)

    def resync_all(self) -> None:
        """After a gap in listening, every open app refetches."""
        for streams in list(self._streams.values()):
            for queue in list(streams):
                self._put(queue, RESYNC)

    async def listen(self, database_url: str) -> None:
        """Run until cancelled; reconnect with a growing pause when the connection drops."""
        conninfo = make_url(database_url).set(drivername="postgresql")
        dsn = conninfo.render_as_string(hide_password=False)
        pause = 1.0
        while True:
            try:
                async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as conn:
                    await conn.execute(f"LISTEN {CHANNEL}")
                    self.listening = True
                    pause = 1.0
                    self.resync_all()
                    async for note in conn.notifies():
                        self.dispatch(note.payload)
            except asyncio.CancelledError:
                raise
            except Exception as err:
                log.warning("event listener disconnected: %s", type(err).__name__)
            self.listening = False
            await asyncio.sleep(pause)
            pause = min(pause * 2, 30.0)


async def stream(
    queue: asyncio.Queue[str],
    still_signed_in: Callable[[], Awaitable[bool]],
    *,
    heartbeat: float = HEARTBEAT_SECONDS,
    recheck: float = RECHECK_SECONDS,
) -> AsyncIterator[str]:
    """The text/event-stream body: a ready event, then changes, with comments as heartbeats so
    proxies keep the connection open. Ends when the session is no longer valid."""
    yield "retry: 3000\n\n"
    yield "event: ready\ndata: {}\n\n"
    checked = time.monotonic()
    while True:
        try:
            data = await asyncio.wait_for(queue.get(), timeout=heartbeat)
            yield f"event: change\ndata: {data}\n\n"
        except TimeoutError:
            yield ": ping\n\n"
        if time.monotonic() - checked >= recheck:
            checked = time.monotonic()
            if not await still_signed_in():
                yield "event: signed_out\ndata: {}\n\n"
                return
