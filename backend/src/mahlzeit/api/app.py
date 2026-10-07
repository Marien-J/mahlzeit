"""The FastAPI application."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from mahlzeit import __version__, logfilter
from mahlzeit.api import errors, events
from mahlzeit.api.routes import (
    auth,
    catalogue,
    connector,
    day,
    household,
    invites,
    me,
    push,
    saved_meals,
    shopping,
    system,
    targets,
)
from mahlzeit.api.routes import (
    events as event_routes,
)
from mahlzeit.config import get_settings, require_valid_settings
from mahlzeit.connector.server import ConnectorApp, build_session_manager

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def create_app() -> FastAPI:
    require_valid_settings()
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    logfilter.install()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # A fresh session manager per start: run() may only be entered once per instance.
        app.state.mcp_manager = build_session_manager()
        listener = asyncio.create_task(app.state.events.listen(settings.database_url))
        try:
            async with app.state.mcp_manager.run():
                yield
        finally:
            listener.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await listener
            app.state.mcp_manager = None

    app = FastAPI(
        lifespan=lifespan,
        title="Mahlzeit",
        version=__version__,
        openapi_url="/api/openapi.json",
        docs_url="/api/docs" if settings.env != "production" else None,
        redoc_url=None,
    )
    app.state.events = events.Broker()
    errors.install(app)

    @app.middleware("http")
    async def check_origin(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Browsers send Origin on cross-site unsafe requests; reject foreign ones before
        # any handler runs. Requests without Origin (curl, the CLI, tests) pass through.
        origin = request.headers.get("origin")
        if (
            request.method in UNSAFE
            # The connector authenticates by its URL, not by cookies, so CSRF does not apply.
            and not request.url.path.startswith("/mcp/")
            and origin is not None
            and origin.rstrip("/") not in get_settings().allowed_origins
        ):
            return JSONResponse(errors.error_body("origin_not_allowed"), status_code=403)
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    for router in (
        system.router,
        auth.router,
        me.router,
        household.router,
        invites.router,
        push.router,
        catalogue.router,
        day.router,
        targets.router,
        saved_meals.router,
        connector.router,
        shopping.router,
        event_routes.router,
    ):
        app.include_router(router, prefix="/api")
    app.mount("/mcp", ConnectorApp())
    return app
