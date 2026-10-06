"""Instance administration, reachable only from the admin CLI."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mahlzeit.domain import accounts
from mahlzeit.domain.errors import Conflict
from mahlzeit.domain.permissions import Client
from mahlzeit.models import Favourite, Household, Item, Profile, User
from mahlzeit.security import passwords
from mahlzeit.services import audit, seed
from mahlzeit.services.auth import actor_for


def create_admin(
    db: Session,
    *,
    email: str,
    password: str,
    display_name: str,
    household_name: str | None = None,
    language: str = accounts.DEFAULT_LANGUAGE,
    time_zone: str = accounts.DEFAULT_TIME_ZONE,
) -> User:
    """Create the first user, as instance admin, in a new household."""
    email = accounts.clean_email(email)
    display_name = accounts.clean_display_name(display_name)
    accounts.check_password(password)
    accounts.check_language(language)
    accounts.check_time_zone(time_zone)
    if db.scalar(select(func.count()).where(User.email == email)):
        raise Conflict("email_taken")
    first_user = not db.scalar(select(func.count()).select_from(User))
    household = Household(name=accounts.clean_household_name(household_name or display_name))
    db.add(household)
    db.flush()
    user = User(
        household_id=household.id,
        email=email,
        password_hash=passwords.hash_password(password),
        display_name=display_name,
        language=language,
        time_zone=time_zone,
        is_admin=True,
    )
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id))
    if first_user:
        _favourite_staples(db, user.id)
    actor = actor_for(user, Client.CLI)
    audit.record(
        db,
        actor=actor,
        entity="household",
        entity_id=household.id,
        action="created",
        after={"name": household.name},
    )
    audit.record(
        db,
        actor=actor,
        entity="user",
        entity_id=user.id,
        action="created",
        after={"display_name": display_name, "is_admin": True},
    )
    db.commit()
    return user


def _favourite_staples(db: Session, user_id: uuid.UUID) -> None:
    """The brief's staple foods become the first person's favourites."""
    wanted = seed.favourite_seed_ids()
    items = db.scalars(select(Item).where(Item.household_id.is_(None)))
    for item in items:
        if (item.source, item.source_id) in wanted:
            db.add(Favourite(user_id=user_id, item_id=item.id))


def list_users(db: Session) -> list[tuple[User, Household]]:
    rows = db.execute(
        select(User, Household)
        .join(Household, Household.id == User.household_id)
        .order_by(Household.created_at, User.created_at)
    )
    return [(user, household) for user, household in rows]
