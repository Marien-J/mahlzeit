"""The caller's own account settings and sharing switches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from mahlzeit import clock
from mahlzeit.domain import accounts
from mahlzeit.domain import stock as stock_rules
from mahlzeit.domain.errors import Invalid
from mahlzeit.domain.permissions import Actor
from mahlzeit.models import Profile, User
from mahlzeit.services import audit

START_SCREENS = ("today", "list")


@dataclass(frozen=True, slots=True)
class Me:
    user: User
    profile: Profile


def get_me(db: Session, actor: Actor) -> Me:
    return Me(user=db.get_one(User, actor.user_id), profile=db.get_one(Profile, actor.user_id))


def update_user(
    db: Session,
    actor: Actor,
    *,
    display_name: str | None = None,
    language: str | None = None,
    time_zone: str | None = None,
) -> Me:
    user = db.get_one(User, actor.user_id)
    changes: dict[str, Any] = {}
    if display_name is not None:
        changes["display_name"] = accounts.clean_display_name(display_name)
    if language is not None:
        accounts.check_language(language)
        changes["language"] = language
    if time_zone is not None:
        accounts.check_time_zone(time_zone)
        changes["time_zone"] = time_zone
    _apply(db, actor, user, "user", changes)
    return get_me(db, actor)


def update_profile(
    db: Session,
    actor: Actor,
    *,
    show_workouts: bool | None = None,
    show_body: bool | None = None,
    share_ai_usage: bool | None = None,
    start_screen: str | None = None,
    push_offers: bool | None = None,
    list_plan_days: int | None = None,
) -> Me:
    profile = db.get_one(Profile, actor.user_id)
    if start_screen is not None and start_screen not in START_SCREENS:
        raise Invalid("start_screen_invalid", allowed=list(START_SCREENS))
    if list_plan_days is not None:
        stock_rules.check_plan_days(list_plan_days)
    requested = {
        "show_workouts": show_workouts,
        "show_body": show_body,
        "share_ai_usage": share_ai_usage,
        "start_screen": start_screen,
        "push_offers": push_offers,
        "list_plan_days": list_plan_days,
    }
    changes = {k: v for k, v in requested.items() if v is not None}
    if changes:
        profile.updated_at = clock.now()
    _apply(db, actor, profile, "profile", changes)
    return get_me(db, actor)


def _apply(
    db: Session, actor: Actor, row: User | Profile, entity: str, changes: dict[str, Any]
) -> None:
    before = {k: getattr(row, k) for k in changes if getattr(row, k) != changes[k]}
    if not before:
        return
    after = {k: changes[k] for k in before}
    for key, value in after.items():
        setattr(row, key, value)
    audit.record(
        db,
        actor=actor,
        entity=entity,
        entity_id=actor.user_id,
        action="updated",
        before=before,
        after=after,
    )
    db.commit()
