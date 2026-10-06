from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from mahlzeit.domain.errors import DomainError

STATUS = {
    "invalid": 422,
    "not_found": 404,
    "forbidden": 403,
    "unauthorized": 401,
    "conflict": 409,
    "rate_limited": 429,
}


def error_body(code: str, detail: Any = None) -> dict[str, Any]:
    return {"code": code, "detail": detail or {}}


def install(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(error_body(exc.code, exc.detail), status_code=STATUS[exc.kind])

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"loc": [str(p) for p in e.get("loc", ())], "type": e.get("type")} for e in exc.errors()
        ]
        return JSONResponse(error_body("validation_error", {"fields": fields}), status_code=422)
