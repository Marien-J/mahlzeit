from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mahlzeit.db import Base
from mahlzeit.models._types import OptTimestamp, Timestamp, UuidPk
from mahlzeit.models.catalogue import CATEGORIES


class Store(Base):
    """A shop. Built-in chains have a key and no household; custom ones belong to a household."""

    __tablename__ = "store"
    __table_args__ = (
        CheckConstraint(
            "(household_id IS NULL AND key IS NOT NULL) OR "
            "(household_id IS NOT NULL AND name IS NOT NULL)",
            name="kind",
        ),
        Index(
            "uq_store_household_name",
            "household_id",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("household_id IS NOT NULL"),
        ),
    )

    id: Mapped[UuidPk]
    household_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str | None] = mapped_column(String(10), unique=True)
    name: Mapped[str | None] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[Timestamp]


class ShoppingListItem(Base):
    """One row of the household's shared list. The id is made by the client, so an offline
    phone can create it and later send it again without a duplicate. Removing sets deleted_at
    and is final."""

    __tablename__ = "shopping_list_item"
    __table_args__ = (
        CheckConstraint(f"category IN {CATEGORIES}", name="category"),
        Index(
            "ix_shopping_list_item_open",
            "household_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    household_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("household.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(String(120))
    item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("item.id", ondelete="SET NULL"))
    quantity: Mapped[str | None] = mapped_column(String(40))
    store_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("store.id", ondelete="SET NULL"))
    category: Mapped[str] = mapped_column(String(20), default="other")
    checked: Mapped[bool] = mapped_column(Boolean, default=False)
    checked_at: Mapped[OptTimestamp]
    checked_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL")
    )
    origin: Mapped[str] = mapped_column(String(12), default="manual")
    # The time of the last change per field, for last-write-wins merging of offline changes.
    field_times: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL")
    )
    created_at: Mapped[Timestamp]
    updated_at: Mapped[Timestamp]
    deleted_at: Mapped[OptTimestamp]
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL")
    )

    store: Mapped[Store | None] = relationship()


class ListMemory(Base):
    """What the household has put on its list before, keyed by catalogue item or normalized
    text: the history behind suggestions, and the aisle and store an entry was last moved to."""

    __tablename__ = "list_memory"
    __table_args__ = (
        UniqueConstraint("household_id", "key"),
        CheckConstraint(f"category IN {CATEGORIES}", name="category"),
    )

    id: Mapped[UuidPk]
    household_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("household.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(160))
    text: Mapped[str] = mapped_column(String(120))
    item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("item.id", ondelete="SET NULL"))
    category: Mapped[str] = mapped_column(String(20), default="other")
    store_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("store.id", ondelete="SET NULL"))
    uses: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[Timestamp]
