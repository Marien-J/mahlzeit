from __future__ import annotations

import json
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

import anyio
import mcp_types as types
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from sqlalchemy.orm import Session
from starlette.types import Receive, Scope, Send

from mahlzeit import __version__
from mahlzeit.db import new_session
from mahlzeit.domain.errors import DomainError
from mahlzeit.domain.permissions import Actor
from mahlzeit.models import User
from mahlzeit.services import connector
from mahlzeit.tools import registry

log = logging.getLogger("mahlzeit.connector")

INSTRUCTIONS = (
    "Mahlzeit is a couple's meal planner and food log. Amounts are grams (or ml) and nutrition is "
    "per 100 g unless a tool says otherwise. Use search_items before log_food. Days are ISO dates "
    "in the person's time zone; get_day without a date is today. Every change you make is "
    "recorded with the connector as its source."
)

SessionFactory = Callable[[], AbstractContextManager[Session]]
_session_factory: SessionFactory = new_session


def set_session_factory(factory: SessionFactory | None) -> None:
    """Tests run tool calls inside their own transaction."""
    global _session_factory
    _session_factory = factory or new_session


def _tool_list() -> list[types.Tool]:
    return [
        types.Tool(
            name=t.name,
            description=t.description,
            input_schema=t.input_schema(),
            annotations=types.ToolAnnotations(
                read_only_hint=not t.writes,
                destructive_hint=t.name.startswith("delete_"),
                open_world_hint=t.name in ("lookup_barcode", "search_online"),
            ),
        )
        for t in registry.load_all().values()
    ]


async def list_tools(
    ctx: ServerRequestContext[Any, Any], params: types.PaginatedRequestParams | None
) -> types.ListToolsResult:
    return types.ListToolsResult(tools=_tool_list())


def _run(actor: Actor, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    with _session_factory() as db:
        user = db.get_one(User, actor.user_id)
        return registry.call(registry.ToolContext(db=db, actor=actor, user=user), name, arguments)


async def call_tool(
    ctx: ServerRequestContext[Any, Any], params: types.CallToolRequestParams
) -> types.CallToolResult:
    actor: Actor | None = (
        getattr(ctx.request.state, "mahlzeit_actor", None) if ctx.request else None
    )
    if actor is None:  # cannot happen behind ConnectorApp; refuse rather than guess
        return _error({"error": "not_authenticated", "detail": {}})
    try:
        result = await anyio.to_thread.run_sync(_run, actor, params.name, params.arguments)
    except registry.ToolError as err:
        return _error(err.as_dict())
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))],
        structured_content=result,
    )


def _error(payload: dict[str, Any]) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(payload))], is_error=True
    )


def build_server() -> Server[Any]:
    return Server(
        "mahlzeit",
        version=__version__,
        instructions=INSTRUCTIONS,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


def build_session_manager() -> StreamableHTTPSessionManager:
    # Stateless JSON: every request stands alone, which suits a personal URL behind Caddy.
    return StreamableHTTPSessionManager(app=build_server(), json_response=True, stateless=True)


class ConnectorApp:
    """ASGI app mounted at /mcp. The path's first segment is the personal token.

    The token resolves to a person; the request then reaches the MCP session manager with that
    person attached. Unknown or revoked tokens get a bare 401. The token never reaches a log.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        # Starlette keeps the full path in mounted apps; take the segment after /mcp/.
        path = scope.get("path", "")
        rest = path.split("/mcp/", 1)[1] if "/mcp/" in path else path.lstrip("/")
        token = rest.split("/", 1)[0]
        actor = await anyio.to_thread.run_sync(_resolve, token)
        if actor is None:
            await _respond(send, 401, {"error": "not_authenticated"})
            return
        manager: StreamableHTTPSessionManager | None = getattr(
            scope["app"].state, "mcp_manager", None
        )
        if manager is None:
            await _respond(send, 503, {"error": "connector_not_started"})
            return
        state = dict(scope.get("state") or {})
        state["mahlzeit_actor"] = actor
        await manager.handle_request({**scope, "state": state}, receive, send)


def _resolve(token: str) -> Actor | None:
    with _session_factory() as db:
        try:
            return connector.resolve(db, token)
        except DomainError:
            return None


async def _respond(send: Send, status: int, body: dict[str, Any]) -> None:
    payload = json.dumps(body).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})
