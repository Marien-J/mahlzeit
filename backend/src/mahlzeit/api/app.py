"""The FastAPI application."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from mahlzeit import __version__
from mahlzeit.api import errors
from mahlzeit.api.routes import auth, household, invites, me, push, system
from mahlzeit.config import get_settings, require_valid_settings

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def create_app() -> FastAPI:
    require_valid_settings()
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    app = FastAPI(
        title="Mahlzeit",
        version=__version__,
        openapi_url="/api/openapi.json",
        docs_url="/api/docs" if settings.env != "production" else None,
        redoc_url=None,
    )
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
    ):
        app.include_router(router, prefix="/api")
    return app
