"""The connector end to end over HTTP: personal URL, MCP handshake, tool list and calls."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from mahlzeit.connector.server import set_session_factory
from mahlzeit.logfilter import RedactConnectorTokens, redact
from mahlzeit.main import app
from mahlzeit.services import connector
from mahlzeit.tools.registry import load_all
from tests import factories

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture
def mcp(db: Session, clock) -> Iterator[tuple[TestClient, str, factories.Member]]:
    @contextmanager
    def shared() -> Iterator[Session]:
        yield db

    set_session_factory(shared)
    jonas, _ = factories.household(db)
    token = connector.create(db, jonas.actor).token
    with TestClient(app, base_url="http://localhost") as client:
        yield client, token, jonas
    set_session_factory(None)


def rpc(
    client: TestClient, token: str, method: str, params: dict[str, Any] | None = None, id_: int = 1
) -> dict[str, Any]:
    body: dict[str, Any] = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        body["params"] = params
    r = client.post(f"/mcp/{token}", json=body, headers=HEADERS)
    assert r.status_code == 200, r.text
    data: dict[str, Any] = r.json()
    assert "error" not in data, data
    return data["result"]


def initialize(client: TestClient, token: str) -> dict[str, Any]:
    return rpc(
        client,
        token,
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
    )


def test_handshake_and_tool_list(mcp) -> None:
    client, token, _ = mcp
    init = initialize(client, token)
    assert init["serverInfo"]["name"] == "mahlzeit"
    tools = rpc(client, token, "tools/list", {}, 2)["tools"]
    assert {t["name"] for t in tools} == set(load_all())
    log_food = next(t for t in tools if t["name"] == "log_food")
    assert log_food["annotations"]["readOnlyHint"] is False
    assert "slot" in log_food["inputSchema"]["properties"]
    get_day = next(t for t in tools if t["name"] == "get_day")
    assert get_day["annotations"]["readOnlyHint"] is True


def test_log_a_meal_and_read_the_day(mcp) -> None:
    client, token, jonas = mcp
    initialize(client, token)
    found = rpc(
        client,
        token,
        "tools/call",
        {"name": "search_items", "arguments": {"query": "haferflocken"}},
        2,
    )
    oats = found["structuredContent"]["items"][0]
    logged = rpc(
        client,
        token,
        "tools/call",
        {
            "name": "log_food",
            "arguments": {"slot": "breakfast", "foods": [{"item_id": oats["id"], "amount": 80}]},
        },
        3,
    )
    assert logged.get("isError") is not True
    day = rpc(client, token, "tools/call", {"name": "get_day", "arguments": {}}, 4)[
        "structuredContent"
    ]
    me = day["people"][0]
    assert me["user_id"] == str(jonas.user.id)
    assert me["logged"]["values"]["kcal"] == round(oats["nutrients"]["kcal"] * 0.8)


def test_tool_errors_are_readable(mcp) -> None:
    client, token, _ = mcp
    initialize(client, token)
    result = rpc(
        client, token, "tools/call", {"name": "log_food", "arguments": {"slot": "lunch"}}, 2
    )
    assert result["isError"] is True
    assert "entry_empty" in result["content"][0]["text"]


@pytest.mark.parametrize("token", ["", "wrong", "x" * 300])
def test_unknown_tokens_are_refused(mcp, token: str) -> None:
    client, _, _ = mcp
    r = client.post(
        f"/mcp/{token}", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=HEADERS
    )
    assert r.status_code in (401, 404, 405)
    assert "tools" not in r.text


def test_revoked_and_rotated_urls_stop_working(mcp, db: Session) -> None:
    client, token, jonas = mcp
    initialize(client, token)
    new_token = connector.create(db, jonas.actor).token
    r = client.post(
        f"/mcp/{token}", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=HEADERS
    )
    assert r.status_code == 401
    initialize(client, new_token)
    connector.revoke(db, jonas.actor)
    r = client.post(
        f"/mcp/{new_token}",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers=HEADERS,
    )
    assert r.status_code == 401


def test_foreign_origin_does_not_block_the_connector(mcp) -> None:
    client, token, _ = mcp
    r = client.post(
        f"/mcp/{token}",
        headers=HEADERS | {"Origin": "https://claude.ai"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "c", "version": "1"},
            },
        },
    )
    assert r.status_code == 200


def test_tokens_never_reach_the_logs() -> None:
    assert (
        redact('127.0.0.1:5 - "POST /mcp/abcDEF_123-x HTTP/1.1" 200')
        == '127.0.0.1:5 - "POST /mcp/[redacted] HTTP/1.1" 200'
    )
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4:5", "POST", "/mcp/secret-token", "1.1", 200),
        None,
    )
    RedactConnectorTokens().filter(record)
    assert "secret-token" not in record.getMessage()
