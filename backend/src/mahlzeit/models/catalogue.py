from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mahlzeit.db import Base
from mahlzeit.models._types import Timestamp, UuidPk

CATEGORIES = (
    "produce",
    "bakery",
    "meat_fish",
    "dairy_eggs",
    "dry_goods",
    "canned",
    "frozen",
    "oils_fats",
    "spices_condiments",
    "sweets_snacks",
    "drinks",
    "household",
    "personal_care",
    "other",
)


class Item(Base):
    """A food or product. Generic seed items have no household and are read-only."""

    __tablename__ = "item"
    __table_args__ = (
        CheckConstraint(f"category IN {CATEGORIES}", name="category"),
        CheckConstraint("base_unit IN ('g', 'ml')", name="base_unit"),
        CheckConstraint("tracking_mode IN ('counted', 'status')", name="tracking_mode"),
        CheckConstraint("source IN ('bls', 'off', 'custom', 'mahlzeit')", name="source"),
        Index(
            "ix_item_search_trgm",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
        Index(
            "uq_item_global_source",
            "source",
            "source_id",
            unique=True,
            postgresql_where=text("household_id IS NULL"),
        ),
    )

    id: Mapped[UuidPk]
    household_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    name_de: Mapped[str | None] = mapped_column(String(120))
    name_en: Mapped[str | None] = mapped_column(String(120))
    name_nl: Mapped[str | None] = mapped_column(String(120))
    brand: Mapped[str | None] = mapped_column(String(80))
    search_text: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(20), default="other")
    base_unit: Mapped[str] = mapped_column(String(2), default="g")
    kcal: Mapped[float | None] = mapped_column(Float)
    protein: Mapped[float | None] = mapped_column(Float)
    carbs: Mapped[float | None] = mapped_column(Float)
    sugar: Mapped[float | None] = mapped_column(Float)
    fat: Mapped[float | None] = mapped_column(Float)
    sat_fat: Mapped[float | None] = mapped_column(Float)
    fibre: Mapped[float | None] = mapped_column(Float)
    salt: Mapped[float | None] = mapped_column(Float)
    alcohol: Mapped[float | None] = mapped_column(Float)
    package_size: Mapped[float | None] = mapped_column(Float)
    tracking_mode: Mapped[str] = mapped_column(String(10), default="counted")
    source: Mapped[str] = mapped_column(String(10), default="custom")
    source_id: Mapped[str | None] = mapped_column(String(40))
    image_url: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL")
    )
    created_at: Mapped[Timestamp]
    updated_at: Mapped[Timestamp]

    barcodes: Mapped[list[ItemBarcode]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="ItemBarcode.code"
    )
    servings: Mapped[list[ServingSize]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="ServingSize.position"
    )


class ItemBarcode(Base):
    """A barcode belongs to one item per household, so each household keeps its own products."""

    __tablename__ = "item_barcode"
    __table_args__ = (UniqueConstraint("household_id", "code"),)

    id: Mapped[UuidPk]
    household_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("household.id", ondelete="CASCADE"))
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("item.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(14))

    item: Mapped[Item] = relationship(back_populates="barcodes")


class ServingSize(Base):
    __tablename__ = "serving_size"

    id: Mapped[UuidPk]
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("item.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(40))
    amount: Mapped[float] = mapped_column(Float)
    position: Mapped[int] = mapped_column(Integer, default=0)

    item: Mapped[Item] = relationship(back_populates="servings")


class Favourite(Base):
    __tablename__ = "favourite"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("item.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[Timestamp]


class Recipe(Base):
    """A recipe or a saved meal (a one-serving recipe for one-tap logging)."""

    __tablename__ = "recipe"
    __table_args__ = (
        CheckConstraint("kind IN ('recipe', 'saved_meal')", name="kind"),
        CheckConstraint("servings > 0", name="servings_positive"),
    )

    id: Mapped[UuidPk]
    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("household.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(12))
    name: Mapped[str] = mapped_column(String(120))
    servings: Mapped[float] = mapped_column(Float, default=1)
    cooked_yield_g: Mapped[float | None] = mapped_column(Float)
    staple: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL")
    )
    created_at: Mapped[Timestamp]
    updated_at: Mapped[Timestamp]

    ingredients: Mapped[list[RecipeIngredient]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", order_by="RecipeIngredient.position"
    )


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredient"

    id: Mapped[UuidPk]
    recipe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recipe.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("item.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    position: Mapped[int] = mapped_column(Integer, default=0)

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")
    item: Mapped[Item] = relationship()
