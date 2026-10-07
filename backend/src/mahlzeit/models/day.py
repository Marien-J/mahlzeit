from __future__ import annotations

import uuid
from datetime import date, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mahlzeit.db import Base
from mahlzeit.models._types import OptTimestamp, Timestamp, UuidPk
from mahlzeit.models.accounts import User
from mahlzeit.models.catalogue import Item, Recipe


class MealEntry(Base):
    """One meal, planned or logged, for one or more people."""

    __tablename__ = "meal_entry"
    __table_args__ = (
        CheckConstraint("slot IN ('breakfast', 'lunch', 'dinner', 'snack')", name="slot"),
        Index("ix_meal_entry_household_day", "household_id", "day"),
    )

    id: Mapped[UuidPk]
    household_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("household.id", ondelete="CASCADE"))
    day: Mapped[date] = mapped_column(Date)
    slot: Mapped[str] = mapped_column(String(10))
    at: Mapped[time] = mapped_column(Time)
    name: Mapped[str | None] = mapped_column(String(120))
    eaten_out: Mapped[bool] = mapped_column(Boolean, default=False)
    recipe_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recipe.id", ondelete="SET NULL")
    )
    recipe_portions: Mapped[float | None] = mapped_column(Float)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL")
    )
    created_at: Mapped[Timestamp]
    updated_at: Mapped[Timestamp]

    components: Mapped[list[MealComponent]] = relationship(
        back_populates="entry", cascade="all, delete-orphan", order_by="MealComponent.position"
    )
    participants: Mapped[list[MealParticipant]] = relationship(
        back_populates="entry", cascade="all, delete-orphan", order_by="MealParticipant.id"
    )
    recipe: Mapped[Recipe | None] = relationship()


class MealComponent(Base):
    """An item and amount, or a quick-add with macros typed in (item_id is null)."""

    __tablename__ = "meal_component"
    __table_args__ = (
        CheckConstraint(
            "(item_id IS NOT NULL AND amount IS NOT NULL)"
            " OR (item_id IS NULL AND quick_name IS NOT NULL)",
            name="item_or_quick",
        ),
    )

    id: Mapped[UuidPk]
    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meal_entry.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("item.id"), index=True)
    amount: Mapped[float | None] = mapped_column(Float)
    serving_label: Mapped[str | None] = mapped_column(String(40))
    serving_count: Mapped[float | None] = mapped_column(Float)
    quick_name: Mapped[str | None] = mapped_column(String(120))
    quick_kcal: Mapped[float | None] = mapped_column(Float)
    quick_protein: Mapped[float | None] = mapped_column(Float)
    quick_carbs: Mapped[float | None] = mapped_column(Float)
    quick_fat: Mapped[float | None] = mapped_column(Float)
    position: Mapped[int] = mapped_column(Integer, default=0)

    entry: Mapped[MealEntry] = relationship(back_populates="components")
    item: Mapped[Item | None] = relationship()


class MealParticipant(Base):
    __tablename__ = "meal_participant"
    __table_args__ = (
        UniqueConstraint("entry_id", "user_id"),
        CheckConstraint("state IN ('planned', 'logged', 'skipped')", name="state"),
        CheckConstraint("share > 0 AND share <= 1", name="share"),
    )

    id: Mapped[UuidPk]
    entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meal_entry.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True
    )
    state: Mapped[str] = mapped_column(String(10))
    share: Mapped[float] = mapped_column(Float, default=1.0)
    logged_at: Mapped[OptTimestamp]

    entry: Mapped[MealEntry] = relationship(back_populates="participants")
    user: Mapped[User] = relationship()
    exact_amounts: Mapped[list[ExactAmount]] = relationship(
        back_populates="participant", cascade="all, delete-orphan"
    )


class ExactAmount(Base):
    """What a person weighed out for themselves of one component of a shared dish. It replaces
    their share for that component. It goes when the component or the participant goes."""

    __tablename__ = "meal_exact_amount"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)

    participant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meal_participant.id", ondelete="CASCADE"), primary_key=True
    )
    component_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meal_component.id", ondelete="CASCADE"), primary_key=True
    )
    amount: Mapped[float] = mapped_column(Float)

    participant: Mapped[MealParticipant] = relationship(back_populates="exact_amounts")


class Offer(Base):
    """A planned meal proposed by one member to another for a date and slot.

    `day` and `slot` are copied from the offered entry so the offer still reads right after the
    entry is gone. A counter-offer points at the offer it answers."""

    __tablename__ = "offer"
    __table_args__ = (
        CheckConstraint("slot IN ('breakfast', 'lunch', 'dinner', 'snack')", name="slot"),
        CheckConstraint(
            "state IN ('pending', 'accepted', 'declined', 'countered', 'withdrawn', 'expired')",
            name="state",
        ),
        CheckConstraint("from_user_id <> to_user_id", name="not_to_self"),
        CheckConstraint("share > 0 AND share < 1", name="share"),
        Index("ix_offer_to_user_state", "to_user_id", "state"),
        Index("ix_offer_household_day", "household_id", "day"),
    )

    id: Mapped[UuidPk]
    household_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("household.id", ondelete="CASCADE"))
    from_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE")
    )
    to_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_account.id", ondelete="CASCADE"))
    entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("meal_entry.id", ondelete="SET NULL"), index=True
    )
    counter_of_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("offer.id", ondelete="SET NULL")
    )
    day: Mapped[date] = mapped_column(Date)
    slot: Mapped[str] = mapped_column(String(10))
    share: Mapped[float] = mapped_column(Float, default=0.5)  # the receiver's share if accepted
    state: Mapped[str] = mapped_column(String(10), default="pending")
    created_at: Mapped[Timestamp]
    responded_at: Mapped[OptTimestamp]

    entry: Mapped[MealEntry | None] = relationship()


class TargetSet(Base):
    """Targets valid from a date for one day type. A later set replaces it from its own date."""

    __tablename__ = "target_set"
    __table_args__ = (
        UniqueConstraint("user_id", "valid_from", "day_type"),
        CheckConstraint("day_type IN ('training', 'rest')", name="day_type"),
    )

    id: Mapped[UuidPk]
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True
    )
    valid_from: Mapped[date] = mapped_column(Date)
    day_type: Mapped[str] = mapped_column(String(10))
    kcal: Mapped[float | None] = mapped_column(Float)
    protein: Mapped[float | None] = mapped_column(Float)
    carbs: Mapped[float | None] = mapped_column(Float)
    fat: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[Timestamp]


class DayTypeOverride(Base):
    __tablename__ = "day_type_override"
    __table_args__ = (CheckConstraint("day_type IN ('training', 'rest')", name="day_type"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    day_type: Mapped[str] = mapped_column(String(10))
