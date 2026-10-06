"""Admin commands: `mahlzeit --help`. Run inside the app container in production:
`docker compose exec app mahlzeit <command>`.
"""

from __future__ import annotations

import os
import secrets
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy import text
from sqlalchemy.orm import Session

from mahlzeit.db import get_engine, new_session
from mahlzeit.domain import accounts
from mahlzeit.domain.errors import DomainError
from mahlzeit.security.crypto import new_key
from mahlzeit.security.vapid import new_vapid_keys
from mahlzeit.services import admin, auth, invites

app = typer.Typer(help="Mahlzeit admin commands.", no_args_is_help=True, add_completion=False)

MIGRATION_LOCK = 4_242_001


def session() -> AbstractContextManager[Session]:
    return new_session()


def _fail(err: DomainError) -> typer.Exit:
    typer.secho(f"error: {err.code} {err.detail or ''}".rstrip(), err=True, fg="red")
    return typer.Exit(code=1)


Password = Annotated[
    str,
    typer.Option(
        prompt=True,
        hide_input=True,
        confirmation_prompt=True,
        envvar="MAHLZEIT_PASSWORD",
        help="Prompted if not given; or set MAHLZEIT_PASSWORD.",
    ),
]


@app.command("create-admin")
def create_admin(
    email: Annotated[str, typer.Option(help="Login email")],
    name: Annotated[str, typer.Option(help="Display name")],
    password: Password,
    household: Annotated[str | None, typer.Option(help="Household name")] = None,
    language: Annotated[str, typer.Option()] = accounts.DEFAULT_LANGUAGE,
    time_zone: Annotated[str, typer.Option()] = accounts.DEFAULT_TIME_ZONE,
) -> None:
    """Create the first user (instance admin) and their household."""
    with session() as db:
        try:
            user = admin.create_admin(
                db,
                email=email,
                password=password,
                display_name=name,
                household_name=household,
                language=language,
                time_zone=time_zone,
            )
        except DomainError as err:
            raise _fail(err) from None
        typer.echo(f"Created admin {user.email} in a new household.")


@app.command("invite-household")
def invite_household(
    language: Annotated[str, typer.Option(help="Language of the join page")] = "de",
    note: Annotated[str | None, typer.Option(help="Who this invite is for")] = None,
) -> None:
    """Invite someone who will start a new household. Prints a link and a code, once."""
    with session() as db:
        try:
            issued = invites.create_household_invite(db, language=language, note=note)
        except DomainError as err:
            raise _fail(err) from None
        typer.echo(f"Link: {issued.link}")
        typer.echo(f"Code: {issued.display_code}")
        typer.echo(f"Valid until: {issued.invite.expires_at:%Y-%m-%d %H:%M} UTC")


@app.command("reset-password")
def reset_password(
    email: Annotated[str, typer.Option()],
    password: Password,
) -> None:
    """Set a user's password and sign them out everywhere."""
    with session() as db:
        try:
            user = auth.admin_set_password(db, email=email, new=password)
        except DomainError as err:
            raise _fail(err) from None
        typer.echo(f"Password set for {user.email}; their sessions have ended.")


@app.command("list-users")
def list_users() -> None:
    """List users grouped by household."""
    with session() as db:
        for user, household in admin.list_users(db):
            flag = " (admin)" if user.is_admin else ""
            typer.echo(
                f"{household.name}\t{user.display_name}\t{user.email}\t{user.language}{flag}"
            )


@app.command("gen-secrets")
def gen_secrets() -> None:
    """Print fresh secrets for .env. Run once per installation."""
    private, public = new_vapid_keys()
    typer.echo(f"POSTGRES_PASSWORD={secrets.token_urlsafe(24)}")
    typer.echo(f"ENCRYPTION_KEY={new_key()}")
    typer.echo(f"VAPID_PRIVATE_KEY={private}")
    typer.echo(f"VAPID_PUBLIC_KEY={public}")


@app.command("send-test-email")
def send_test_email(to: Annotated[str, typer.Option()]) -> None:
    """Check the SMTP settings by sending one email."""
    from mahlzeit.config import get_settings
    from mahlzeit.mail import SmtpMailer

    if not get_settings().email_enabled:
        typer.secho("SMTP is not configured (SMTP_HOST and SMTP_FROM).", err=True, fg="red")
        raise typer.Exit(code=1)
    SmtpMailer().send(to=to, subject="Mahlzeit test", body="SMTP works.")
    typer.echo("Sent.")


def _alembic_ini() -> Path:
    configured = os.environ.get("ALEMBIC_CONFIG")
    return Path(configured) if configured else Path(__file__).resolve().parents[2] / "alembic.ini"


@app.command()
def migrate() -> None:
    """Upgrade the database to the latest migration. Safe to run from several processes."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_alembic_ini()))
    with get_engine().connect() as conn:
        # A session-level lock: it outlives the commit and serialises concurrent starts.
        conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": MIGRATION_LOCK})
        conn.commit()
        try:
            with conn.begin():
                cfg.attributes["connection"] = conn
                command.upgrade(cfg, "head")
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": MIGRATION_LOCK})
            conn.commit()
    typer.echo("Database is up to date.")


if __name__ == "__main__":
    app()
