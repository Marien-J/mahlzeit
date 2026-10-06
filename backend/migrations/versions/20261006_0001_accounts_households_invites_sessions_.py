"""accounts households invites sessions push jobs audit

Revision ID: 0001
Revises:
Create Date: 2026-10-06 16:57:17.090283
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Trigram search for the catalogue (M1) and list suggestions (M2).
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "household",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_household")),
    )
    op.create_table(
        "job",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=60), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=120), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')", name=op.f("ck_job_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job")),
        sa.UniqueConstraint("dedupe_key", name=op.f("uq_job_dedupe_key")),
    )
    op.create_index("ix_job_status_run_at", "job", ["status", "run_at"], unique=False)
    op.create_table(
        "login_attempt",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_attempt")),
    )
    op.create_index("ix_login_attempt_email_at", "login_attempt", ["email", "at"], unique=False)
    op.create_index("ix_login_attempt_ip_at", "login_attempt", ["ip", "at"], unique=False)
    op.create_table(
        "user_account",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(length=60), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("time_zone", sa.String(length=64), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("language IN ('de', 'en', 'nl')", name=op.f("ck_user_account_language")),
        sa.ForeignKeyConstraint(
            ["household_id"], ["household.id"], name=op.f("fk_user_account_household_id_household")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_account")),
        sa.UniqueConstraint("email", name=op.f("uq_user_account_email")),
    )
    op.create_index(
        op.f("ix_user_account_household_id"), "user_account", ["household_id"], unique=False
    )
    op.create_table(
        "auth_session",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("csrf_token", sa.String(length=64), nullable=False),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_account.id"],
            name=op.f("fk_auth_session_user_id_user_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_session")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_auth_session_token_hash")),
    )
    op.create_index(op.f("ix_auth_session_user_id"), "auth_session", ["user_id"], unique=False)
    op.create_table(
        "change_record",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("client", sa.String(length=10), nullable=False),
        sa.Column("entity", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "client IN ('ui', 'connector', 'assistant', 'job', 'cli')",
            name=op.f("ck_change_record_client"),
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_change_record_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_account.id"],
            name=op.f("fk_change_record_user_id_user_account"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_record")),
    )
    op.create_index(
        "ix_change_record_household_created",
        "change_record",
        ["household_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "invite",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("note", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(kind = 'partner') = (household_id IS NOT NULL)",
            name=op.f("ck_invite_partner_has_household"),
        ),
        sa.CheckConstraint("kind IN ('household', 'partner')", name=op.f("ck_invite_kind")),
        sa.ForeignKeyConstraint(
            ["accepted_by"],
            ["user_account.id"],
            name=op.f("fk_invite_accepted_by_user_account"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["user_account.id"],
            name=op.f("fk_invite_created_by_user_account"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_invite_household_id_household"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invite")),
        sa.UniqueConstraint("code_hash", name=op.f("uq_invite_code_hash")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_invite_token_hash")),
    )
    op.create_index(op.f("ix_invite_household_id"), "invite", ["household_id"], unique=False)
    op.create_table(
        "password_reset",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_account.id"],
            name=op.f("fk_password_reset_user_id_user_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_reset")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_password_reset_token_hash")),
    )
    op.create_index(op.f("ix_password_reset_user_id"), "password_reset", ["user_id"], unique=False)
    op.create_table(
        "profile",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("show_workouts", sa.Boolean(), nullable=False),
        sa.Column("show_body", sa.Boolean(), nullable=False),
        sa.Column("share_ai_usage", sa.Boolean(), nullable=False),
        sa.Column("start_screen", sa.String(length=10), nullable=False),
        sa.Column("push_offers", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "start_screen IN ('today', 'list')", name=op.f("ck_profile_start_screen")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_account.id"],
            name=op.f("fk_profile_user_id_user_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_profile")),
    )
    op.create_table(
        "push_subscription",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint_hash", sa.String(length=64), nullable=False),
        sa.Column("subscription_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_account.id"],
            name=op.f("fk_push_subscription_user_id_user_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_subscription")),
        sa.UniqueConstraint("endpoint_hash", name=op.f("uq_push_subscription_endpoint_hash")),
    )
    op.create_index(
        op.f("ix_push_subscription_user_id"), "push_subscription", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_push_subscription_user_id"), table_name="push_subscription")
    op.drop_table("push_subscription")
    op.drop_table("profile")
    op.drop_index(op.f("ix_password_reset_user_id"), table_name="password_reset")
    op.drop_table("password_reset")
    op.drop_index(op.f("ix_invite_household_id"), table_name="invite")
    op.drop_table("invite")
    op.drop_index("ix_change_record_household_created", table_name="change_record")
    op.drop_table("change_record")
    op.drop_index(op.f("ix_auth_session_user_id"), table_name="auth_session")
    op.drop_table("auth_session")
    op.drop_index(op.f("ix_user_account_household_id"), table_name="user_account")
    op.drop_table("user_account")
    op.drop_index("ix_login_attempt_ip_at", table_name="login_attempt")
    op.drop_index("ix_login_attempt_email_at", table_name="login_attempt")
    op.drop_table("login_attempt")
    op.drop_index("ix_job_status_run_at", table_name="job")
    op.drop_table("job")
    op.drop_table("household")
