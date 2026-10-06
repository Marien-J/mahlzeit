"""catalogue day targets connector

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-06 19:25:47.001378
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "off_cache",
        sa.Column("code", sa.String(length=14), nullable=False),
        sa.Column("found", sa.Boolean(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_off_cache")),
    )
    op.create_table(
        "rate_window",
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("key", "window_start", name=op.f("pk_rate_window")),
    )
    op.create_table(
        "connector_token",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_account.id"],
            name=op.f("fk_connector_token_user_id_user_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_connector_token")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_connector_token_token_hash")),
    )
    op.create_index(
        op.f("ix_connector_token_user_id"), "connector_token", ["user_id"], unique=False
    )
    op.create_table(
        "day_type_override",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("day_type", sa.String(length=10), nullable=False),
        sa.CheckConstraint(
            "day_type IN ('training', 'rest')", name=op.f("ck_day_type_override_day_type")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_account.id"],
            name=op.f("fk_day_type_override_user_id_user_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "day", name=op.f("pk_day_type_override")),
    )
    op.create_table(
        "item",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=True),
        sa.Column("name_de", sa.String(length=120), nullable=True),
        sa.Column("name_en", sa.String(length=120), nullable=True),
        sa.Column("name_nl", sa.String(length=120), nullable=True),
        sa.Column("brand", sa.String(length=80), nullable=True),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("base_unit", sa.String(length=2), nullable=False),
        sa.Column("kcal", sa.Float(), nullable=True),
        sa.Column("protein", sa.Float(), nullable=True),
        sa.Column("carbs", sa.Float(), nullable=True),
        sa.Column("sugar", sa.Float(), nullable=True),
        sa.Column("fat", sa.Float(), nullable=True),
        sa.Column("sat_fat", sa.Float(), nullable=True),
        sa.Column("fibre", sa.Float(), nullable=True),
        sa.Column("salt", sa.Float(), nullable=True),
        sa.Column("alcohol", sa.Float(), nullable=True),
        sa.Column("package_size", sa.Float(), nullable=True),
        sa.Column("tracking_mode", sa.String(length=10), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("source_id", sa.String(length=40), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("base_unit IN ('g', 'ml')", name=op.f("ck_item_base_unit")),
        sa.CheckConstraint(
            "category IN ('produce', 'bakery', 'meat_fish', 'dairy_eggs', 'dry_goods', 'canned', 'frozen', 'oils_fats', 'spices_condiments', 'sweets_snacks', 'drinks', 'household', 'personal_care', 'other')",
            name=op.f("ck_item_category"),
        ),
        sa.CheckConstraint(
            "source IN ('bls', 'off', 'custom', 'mahlzeit')", name=op.f("ck_item_source")
        ),
        sa.CheckConstraint(
            "tracking_mode IN ('counted', 'status')", name=op.f("ck_item_tracking_mode")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["user_account.id"],
            name=op.f("fk_item_created_by_user_account"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_item_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_item")),
    )
    op.create_index(op.f("ix_item_household_id"), "item", ["household_id"], unique=False)
    op.create_index(
        "ix_item_search_trgm",
        "item",
        ["search_text"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.create_index(
        "uq_item_global_source",
        "item",
        ["source", "source_id"],
        unique=True,
        postgresql_where=sa.text("household_id IS NULL"),
    )
    op.create_table(
        "recipe",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("servings", sa.Float(), nullable=False),
        sa.Column("cooked_yield_g", sa.Float(), nullable=True),
        sa.Column("staple", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('recipe', 'saved_meal')", name=op.f("ck_recipe_kind")),
        sa.CheckConstraint("servings > 0", name=op.f("ck_recipe_servings_positive")),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["user_account.id"],
            name=op.f("fk_recipe_created_by_user_account"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_recipe_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recipe")),
    )
    op.create_index(op.f("ix_recipe_household_id"), "recipe", ["household_id"], unique=False)
    op.create_table(
        "target_set",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("day_type", sa.String(length=10), nullable=False),
        sa.Column("kcal", sa.Float(), nullable=True),
        sa.Column("protein", sa.Float(), nullable=True),
        sa.Column("carbs", sa.Float(), nullable=True),
        sa.Column("fat", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("day_type IN ('training', 'rest')", name=op.f("ck_target_set_day_type")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_account.id"],
            name=op.f("fk_target_set_user_id_user_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_target_set")),
        sa.UniqueConstraint(
            "user_id", "valid_from", "day_type", name=op.f("uq_target_set_user_id")
        ),
    )
    op.create_index(op.f("ix_target_set_user_id"), "target_set", ["user_id"], unique=False)
    op.create_table(
        "favourite",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"], ["item.id"], name=op.f("fk_favourite_item_id_item"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_account.id"],
            name=op.f("fk_favourite_user_id_user_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "item_id", name=op.f("pk_favourite")),
    )
    op.create_table(
        "item_barcode",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=14), nullable=False),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_item_barcode_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_id"], ["item.id"], name=op.f("fk_item_barcode_item_id_item"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_item_barcode")),
        sa.UniqueConstraint("household_id", "code", name=op.f("uq_item_barcode_household_id")),
    )
    op.create_index(op.f("ix_item_barcode_item_id"), "item_barcode", ["item_id"], unique=False)
    op.create_table(
        "meal_entry",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("slot", sa.String(length=10), nullable=False),
        sa.Column("at", sa.Time(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("eaten_out", sa.Boolean(), nullable=False),
        sa.Column("recipe_id", sa.Uuid(), nullable=True),
        sa.Column("recipe_portions", sa.Float(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "slot IN ('breakfast', 'lunch', 'dinner', 'snack')", name=op.f("ck_meal_entry_slot")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["user_account.id"],
            name=op.f("fk_meal_entry_created_by_user_account"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_meal_entry_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipe.id"],
            name=op.f("fk_meal_entry_recipe_id_recipe"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meal_entry")),
    )
    op.create_index(
        "ix_meal_entry_household_day", "meal_entry", ["household_id", "day"], unique=False
    )
    op.create_table(
        "recipe_ingredient",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recipe_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"], ["item.id"], name=op.f("fk_recipe_ingredient_item_id_item")
        ),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipe.id"],
            name=op.f("fk_recipe_ingredient_recipe_id_recipe"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recipe_ingredient")),
    )
    op.create_index(
        op.f("ix_recipe_ingredient_item_id"), "recipe_ingredient", ["item_id"], unique=False
    )
    op.create_index(
        op.f("ix_recipe_ingredient_recipe_id"), "recipe_ingredient", ["recipe_id"], unique=False
    )
    op.create_table(
        "serving_size",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=40), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"], ["item.id"], name=op.f("fk_serving_size_item_id_item"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_serving_size")),
    )
    op.create_index(op.f("ix_serving_size_item_id"), "serving_size", ["item_id"], unique=False)
    op.create_table(
        "meal_component",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("serving_label", sa.String(length=40), nullable=True),
        sa.Column("serving_count", sa.Float(), nullable=True),
        sa.Column("quick_name", sa.String(length=120), nullable=True),
        sa.Column("quick_kcal", sa.Float(), nullable=True),
        sa.Column("quick_protein", sa.Float(), nullable=True),
        sa.Column("quick_carbs", sa.Float(), nullable=True),
        sa.Column("quick_fat", sa.Float(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "(item_id IS NOT NULL AND amount IS NOT NULL) OR (item_id IS NULL AND quick_name IS NOT NULL)",
            name=op.f("ck_meal_component_item_or_quick"),
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["meal_entry.id"],
            name=op.f("fk_meal_component_entry_id_meal_entry"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_id"], ["item.id"], name=op.f("fk_meal_component_item_id_item")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meal_component")),
    )
    op.create_index(
        op.f("ix_meal_component_entry_id"), "meal_component", ["entry_id"], unique=False
    )
    op.create_index(op.f("ix_meal_component_item_id"), "meal_component", ["item_id"], unique=False)
    op.create_table(
        "meal_participant",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=10), nullable=False),
        sa.Column("share", sa.Float(), nullable=False),
        sa.Column("logged_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('planned', 'logged', 'skipped')", name=op.f("ck_meal_participant_state")
        ),
        sa.CheckConstraint("share > 0 AND share <= 1", name=op.f("ck_meal_participant_share")),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["meal_entry.id"],
            name=op.f("fk_meal_participant_entry_id_meal_entry"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_account.id"],
            name=op.f("fk_meal_participant_user_id_user_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meal_participant")),
        sa.UniqueConstraint("entry_id", "user_id", name=op.f("uq_meal_participant_entry_id")),
    )
    op.create_index(
        op.f("ix_meal_participant_user_id"), "meal_participant", ["user_id"], unique=False
    )
    op.add_column(
        "profile",
        sa.Column("week_pattern", sa.String(length=7), server_default="RRRRRRR", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("profile", "week_pattern")
    op.drop_index(op.f("ix_meal_participant_user_id"), table_name="meal_participant")
    op.drop_table("meal_participant")
    op.drop_index(op.f("ix_meal_component_item_id"), table_name="meal_component")
    op.drop_index(op.f("ix_meal_component_entry_id"), table_name="meal_component")
    op.drop_table("meal_component")
    op.drop_index(op.f("ix_serving_size_item_id"), table_name="serving_size")
    op.drop_table("serving_size")
    op.drop_index(op.f("ix_recipe_ingredient_recipe_id"), table_name="recipe_ingredient")
    op.drop_index(op.f("ix_recipe_ingredient_item_id"), table_name="recipe_ingredient")
    op.drop_table("recipe_ingredient")
    op.drop_index("ix_meal_entry_household_day", table_name="meal_entry")
    op.drop_table("meal_entry")
    op.drop_index(op.f("ix_item_barcode_item_id"), table_name="item_barcode")
    op.drop_table("item_barcode")
    op.drop_table("favourite")
    op.drop_index(op.f("ix_target_set_user_id"), table_name="target_set")
    op.drop_table("target_set")
    op.drop_index(op.f("ix_recipe_household_id"), table_name="recipe")
    op.drop_table("recipe")
    op.drop_index(
        "uq_item_global_source", table_name="item", postgresql_where=sa.text("household_id IS NULL")
    )
    op.drop_index(
        "ix_item_search_trgm",
        table_name="item",
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.drop_index(op.f("ix_item_household_id"), table_name="item")
    op.drop_table("item")
    op.drop_table("day_type_override")
    op.drop_index(op.f("ix_connector_token_user_id"), table_name="connector_token")
    op.drop_table("connector_token")
    op.drop_table("rate_window")
    op.drop_table("off_cache")
