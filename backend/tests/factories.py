"""Builders for test data. They go through the services, like every client does."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import count

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from mahlzeit.domain.permissions import Actor
from mahlzeit.models import Item, User
from mahlzeit.services import admin, auth, invites

PASSWORD = "correct horse battery"
_seq = count(1)


@dataclass
class Member:
    user: User
    actor: Actor
    email: str
    password: str = PASSWORD


def household(db: Session, *names: str) -> list[Member]:
    """A new household: the first name is created by the admin command, the rest join by invite."""
    first, *rest = names or ("Jonas", "Partner")
    n = next(_seq)
    email = f"{first.lower()}{n}@example.org"
    user = admin.create_admin(db, email=email, password=PASSWORD, display_name=first)
    members = [Member(user=user, actor=auth.actor_for(user), email=email)]
    for name in rest:
        issued = invites.create_partner_invite(db, members[0].actor)
        member_email = f"{name.lower()}{n}@example.org"
        started = invites.accept(
            db,
            key=issued.token,
            email=member_email,
            password=PASSWORD,
            display_name=name,
            language="en",
            time_zone="Europe/Amsterdam",
        )
        members.append(
            Member(user=started.user, actor=auth.actor_for(started.user), email=member_email)
        )
    return members


def signed_in(client: TestClient, member: Member) -> str:
    """Log a client in and return its CSRF token."""
    response = client.post(
        "/api/auth/login", json={"email": member.email, "password": member.password}
    )
    assert response.status_code == 200, response.text
    token: str = response.json()["csrf_token"]
    client.headers["X-CSRF-Token"] = token
    return token


def generic(db: Session, actor: Actor, bls_code: str) -> Item:
    """A generic seed food by its BLS code."""
    return db.scalars(select(Item).where(Item.source == "bls", Item.source_id == bls_code)).one()
