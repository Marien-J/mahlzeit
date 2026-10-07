from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, Float, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mahlzeit.db import Base
from mahlzeit.models._types import Timestamp, UuidPk
from mahlzeit.models.catalogue import CATEGORIES, Item
from mahlzeit.models.shopping import Store


class Purchase(Base):
    """One shop: a store, a day and its lines. Confirming it writes stock movements. The id is
    made by the phone, so sending 'Bought' twice records one purchase."""

    __tablename__ = "purchase"
    __table_args__ = (Index("ix_purchase_household_day", "household_id", "day"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    household_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("household.id", ondelete="CASCADE"))
    store_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("store.id", ondelete="SET NULL"))
    day: Mapped[date] = mapped_column(Date)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL")
    )
    created_at: Mapped[Timestamp]

    lines: Mapped[list[PurchaseLine]] = relationship(
        back_populates="purchase", cascade="all, delete-orphan", order_by="PurchaseLine.position"
    )
    store: Mapped[Store | None] = relationship()


class PurchaseLine(Base):
    """A catalogue item or free text; the amount (g or ml) goes into stock, the price is
    optional. `quantity` is what the list said."""

    __tablename__ = "purchase_line"
    __table_args__ = (
        CheckConstraint("amount IS NULL OR amount > 0", name="amount_positive"),
        CheckConstraint("price_cents IS NULL OR price_cents >= 0", name="price_not_negative"),
    )

    id: Mapped[UuidPk]
    purchase_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("purchase.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("item.id", ondelete="SET NULL"), index=True
    )
    text: Mapped[str] = mapped_column(String(120))
    quantity: Mapped[str | None] = mapped_column(String(40))
    amount: Mapped[float | None] = mapped_column(Float)
    price_cents: Mapped[int | None] = mapped_column(Integer)
    list_item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    position: Mapped[int] = mapped_column(Integer, default=0)

    purchase: Mapped[Purchase] = relationship(back_populates="lines")
    item: Mapped[Item | None] = relationship()


class StockMovement(Base):
    """One signed change of an item's stock in its base unit. The level is the sum."""

    __tablename__ = "stock_movement"
    __table_args__ = (
        CheckConstraint(
            "reason IN ('purchase', 'consumption', 'correction', 'waste')", name="reason"
        ),
        CheckConstraint(
            "source IN ('purchase', 'entry', 'shortfall', 'pantry', 'manual')", name="source"
        ),
        CheckConstraint("amount <> 0", name="amount_not_zero"),
        Index("ix_stock_movement_household_item", "household_id", "item_id"),
        Index("ix_stock_movement_household_day", "household_id", "day"),
        Index("ix_stock_movement_source_id", "source_id"),
    )

    id: Mapped[UuidPk]
    household_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("household.id", ondelete="CASCADE"))
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("item.id", ondelete="CASCADE"))
    amount: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(12))
    source: Mapped[str] = mapped_column(String(10))
    # The purchase line or meal entry behind it (no foreign key: the history outlives them).
    source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    day: Mapped[date] = mapped_column(Date)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL")
    )
    created_at: Mapped[Timestamp]

    item: Mapped[Item] = relationship()


class StockStatus(Base):
    """Per household and item: how it is tracked here (a counted amount, or only a status) and,
    for status-only items such as oil and spices, whether it is ok, low or out."""

    __tablename__ = "stock_status"
    __table_args__ = (
        CheckConstraint("mode IS NULL OR mode IN ('counted', 'status')", name="mode"),
        CheckConstraint("status IS NULL OR status IN ('ok', 'low', 'out')", name="status"),
    )

    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("item.id", ondelete="CASCADE"), primary_key=True
    )
    mode: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str | None] = mapped_column(String(4))
    updated_at: Mapped[Timestamp]
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL")
    )


class PantryCheck(Base):
    """When an aisle of the pantry was last checked, and by whom."""

    __tablename__ = "pantry_check"
    __table_args__ = (CheckConstraint(f"category IN {CATEGORIES}", name="category"),)

    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), primary_key=True
    )
    category: Mapped[str] = mapped_column(String(20), primary_key=True)
    checked_at: Mapped[Timestamp]
    checked_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL")
    )
