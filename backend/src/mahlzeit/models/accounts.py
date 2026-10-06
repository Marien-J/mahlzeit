from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mahlzeit.db import Base
from mahlzeit.models._types import OptTimestamp, Timestamp, UuidPk

LANGUAGES = ("de", "en", "nl")
START_SCREENS = ("today", "list")


class Household(Base):
    __tablename__ = "household"

    id: Mapped[UuidPk]
    name: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[Timestamp]

    members: Mapped[list[User]] = relationship(
        back_populates="household", order_by="User.created_at"
    )


class User(Base):
    __tablename__ = "user_account"
    __table_args__ = (CheckConstraint(f"language IN {LANGUAGES}", name="language"),)

    id: Mapped[UuidPk]
    household_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("household.id"), index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)  # stored normalised
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(String(60))
    language: Mapped[str] = mapped_column(String(2), default="de")
    time_zone: Mapped[str] = mapped_column(String(64), default="Europe/Berlin")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[Timestamp]
    password_changed_at: Mapped[Timestamp]

    household: Mapped[Household] = relationship(back_populates="members")
    profile: Mapped[Profile] = relationship(back_populates="user", uselist=False)


class Profile(Base):
    __tablename__ = "profile"
    __table_args__ = (CheckConstraint(f"start_screen IN {START_SCREENS}", name="start_screen"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), primary_key=True
    )
    show_workouts: Mapped[bool] = mapped_column(Boolean, default=True)
    show_body: Mapped[bool] = mapped_column(Boolean, default=False)
    share_ai_usage: Mapped[bool] = mapped_column(Boolean, default=False)
    start_screen: Mapped[str] = mapped_column(String(10), default="today")
    push_offers: Mapped[bool] = mapped_column(Boolean, default=True)
    week_pattern: Mapped[str] = mapped_column(
        String(7), default="RRRRRRR", server_default="RRRRRRR"
    )
    updated_at: Mapped[Timestamp]

    user: Mapped[User] = relationship(back_populates="profile")


class Invite(Base):
    __tablename__ = "invite"
    __table_args__ = (
        CheckConstraint("kind IN ('household', 'partner')", name="kind"),
        CheckConstraint(
            "(kind = 'partner') = (household_id IS NOT NULL)", name="partner_has_household"
        ),
    )

    id: Mapped[UuidPk]
    kind: Mapped[str] = mapped_column(String(10))
    household_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL")
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    language: Mapped[str] = mapped_column(String(2), default="de")
    note: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[Timestamp]
    expires_at: Mapped[Timestamp]
    accepted_at: Mapped[OptTimestamp]
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL")
    )
    revoked_at: Mapped[OptTimestamp]


class AuthSession(Base):
    __tablename__ = "auth_session"

    id: Mapped[UuidPk]
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True
    )
    csrf_token: Mapped[str] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[Timestamp]
    last_seen_at: Mapped[Timestamp]
    expires_at: Mapped[Timestamp]


class PasswordReset(Base):
    __tablename__ = "password_reset"

    id: Mapped[UuidPk]
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[Timestamp]
    expires_at: Mapped[Timestamp]
    used_at: Mapped[OptTimestamp]


class LoginAttempt(Base):
    __tablename__ = "login_attempt"
    __table_args__ = (
        Index("ix_login_attempt_email_at", "email", "at"),
        Index("ix_login_attempt_ip_at", "ip", "at"),
    )

    id: Mapped[UuidPk]
    email: Mapped[str] = mapped_column(String(254))
    ip: Mapped[str] = mapped_column(String(64))
    success: Mapped[bool] = mapped_column(Boolean)
    at: Mapped[Timestamp]
