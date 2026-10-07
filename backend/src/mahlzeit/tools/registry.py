from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from mahlzeit.domain.errors import DomainError
from mahlzeit.domain.permissions import Actor
from mahlzeit.models import User
from mahlzeit.services.targets import today_for


@dataclass(frozen=True)
class ToolContext:
    db: Session
    actor: Actor
    user: User

    @property
    def language(self) -> str:
        return self.user.language

    @property
    def today(self) -> date:
        return today_for(self.user)


Result = BaseModel | Sequence[BaseModel] | dict[str, Any]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input: type[BaseModel]
    run: Callable[[ToolContext, Any], Result]
    writes: bool

    def input_schema(self) -> dict[str, Any]:
        return self.input.model_json_schema()


class ToolError(Exception):
    """A failure the model should read: an error code plus details, never a stack trace."""

    def __init__(self, code: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail or {}

    def as_dict(self) -> dict[str, Any]:
        return {"error": self.code, "detail": self.detail}


REGISTRY: dict[str, Tool] = {}


def tool(
    name: str, description: str, input: type[BaseModel], *, writes: bool
) -> Callable[[Callable[[ToolContext, Any], Result]], Callable[[ToolContext, Any], Result]]:
    def register(fn: Callable[[ToolContext, Any], Result]) -> Callable[[ToolContext, Any], Result]:
        if name in REGISTRY:
            raise ValueError(f"tool {name} registered twice")
        REGISTRY[name] = Tool(
            name=name, description=description, input=input, run=fn, writes=writes
        )
        return fn

    return register


def _json(result: Result) -> dict[str, Any]:
    if isinstance(result, BaseModel):
        return result.model_dump(mode="json")
    if isinstance(result, dict):
        return result
    return {"items": [r.model_dump(mode="json") for r in result]}


def call(ctx: ToolContext, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Run a tool by name. Raises ToolError for anything the caller got wrong."""
    load_all()
    spec = REGISTRY.get(name)
    if spec is None:
        raise ToolError("unknown_tool", {"name": name})
    try:
        args = spec.input.model_validate(arguments or {})
    except ValidationError as err:
        fields = [{"loc": [str(p) for p in e["loc"]], "msg": e["msg"]} for e in err.errors()]
        raise ToolError("validation_error", {"fields": fields}) from None
    try:
        return _json(spec.run(ctx, args))
    except DomainError as err:
        ctx.db.rollback()
        raise ToolError(err.code, dict(err.detail)) from None


def load_all() -> dict[str, Tool]:
    """Import the modules that register tools (idempotent)."""
    from mahlzeit.tools import catalogue, day, plan, shopping  # noqa: F401

    return REGISTRY
