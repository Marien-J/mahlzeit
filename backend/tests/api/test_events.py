"""Live updates: the broker, the event stream, and the real LISTEN/NOTIFY path."""

import asyncio
import json
import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from mahlzeit.api import events
from mahlzeit.services.events import CHANNEL, payload
from tests.conftest import TEST_DATABASE_URL

HOME = uuid.UUID("0192f1c4-0000-7000-8000-0000000000aa")
AWAY = uuid.UUID("0192f1c4-0000-7000-8000-0000000000bb")


def test_the_stream_needs_a_session(make_client: Callable[[], TestClient]) -> None:
    response = make_client().get("/api/events")
    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


def test_notifications_reach_only_the_households_streams() -> None:
    broker = events.Broker()

    async def run() -> None:
        home, away = broker.subscribe(HOME), broker.subscribe(AWAY)
        broker.dispatch(payload(HOME, "list_item", None))
        broker.dispatch("not json")
        assert json.loads(home.get_nowait()) == {"entity": "list_item", "user": None}
        assert away.empty()
        broker.unsubscribe(HOME, home)
        assert broker.subscribers(HOME) == 0

    asyncio.run(run())


def test_a_slow_stream_is_told_to_refetch_everything() -> None:
    broker = events.Broker()

    async def run() -> None:
        queue = broker.subscribe(HOME)
        for _ in range(events.QUEUE_SIZE + 5):
            broker.dispatch(payload(HOME, "list_item", None))
        items = []
        while not queue.empty():
            items.append(queue.get_nowait())
        assert events.RESYNC in items
        assert len(items) <= events.QUEUE_SIZE

    asyncio.run(run())


def test_the_stream_sends_ready_changes_heartbeats_and_ends_when_signed_out() -> None:
    async def run() -> list[str]:
        queue: asyncio.Queue[str] = asyncio.Queue()
        await queue.put('{"entity": "list_item"}')
        signed_in = iter([True, False])

        async def check() -> bool:
            return next(signed_in)

        chunks = []
        async for chunk in events.stream(queue, check, heartbeat=0.01, recheck=0):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(run())
    assert chunks[0].startswith("retry:")
    assert chunks[1] == "event: ready\ndata: {}\n\n"
    assert chunks[2] == 'event: change\ndata: {"entity": "list_item"}\n\n'
    assert chunks[3] == ": ping\n\n"
    assert chunks[-1] == "event: signed_out\ndata: {}\n\n"


def test_a_committed_notify_reaches_the_listener(engine: Engine) -> None:
    broker = events.Broker()

    async def run() -> str:
        queue = broker.subscribe(HOME)
        listener = asyncio.create_task(broker.listen(TEST_DATABASE_URL))
        try:
            for _ in range(100):
                if broker.listening:
                    break
                await asyncio.sleep(0.05)
            assert broker.listening
            assert await asyncio.wait_for(queue.get(), 1) == events.RESYNC  # after connecting
            with engine.begin() as conn:
                conn.execute(
                    text("SELECT pg_notify(:channel, :payload)"),
                    {"channel": CHANNEL, "payload": payload(HOME, "list_item", None)},
                )
            return await asyncio.wait_for(queue.get(), 5)
        finally:
            listener.cancel()

    assert json.loads(asyncio.run(run())) == {"entity": "list_item", "user": None}
