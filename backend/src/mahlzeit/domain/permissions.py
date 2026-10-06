"""Who may see and change what. Pure functions; the service layer calls them on every operation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

from mahlzeit.domain.errors import Forbidden, NotFound


class Client(StrEnum):
    """Which client made a change. Recorded on every write."""

    UI = "ui"
    CONNECTOR = "connector"
    ASSISTANT = "assistant"
    JOB = "job"
    CLI = "cli"


@dataclass(frozen=True, slots=True)
class Actor:
    user_id: uuid.UUID
    household_id: uuid.UUID
    client: Client
    is_admin: bool = False


class Area(StrEnum):
    FOOD = "food"
    TARGETS = "targets"
    WORKOUTS = "workouts"
    BODY = "body"
    AI_USAGE = "ai_usage"


@dataclass(frozen=True, slots=True)
class Visibility:
    """A profile's sharing switches, as the owner set them."""

    show_workouts: bool
    show_body: bool
    share_ai_usage: bool


def require_household(actor: Actor, household_id: uuid.UUID) -> None:
    """Rows of another household behave as if they did not exist."""
    if actor.household_id != household_id:
        raise NotFound()


def require_admin(actor: Actor) -> None:
    if not actor.is_admin:
        raise Forbidden("admin_only")


def can_view(
    actor: Actor,
    owner_id: uuid.UUID,
    owner_household_id: uuid.UUID,
    owner_visibility: Visibility,
    area: Area,
) -> bool:
    if owner_household_id != actor.household_id:
        return False
    if owner_id == actor.user_id:
        return True
    match area:
        case Area.FOOD | Area.TARGETS:
            return True  # joint planning depends on them
        case Area.WORKOUTS:
            return owner_visibility.show_workouts
        case Area.BODY:
            return owner_visibility.show_body
        case Area.AI_USAGE:
            return owner_visibility.share_ai_usage
