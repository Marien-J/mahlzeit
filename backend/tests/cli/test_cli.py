from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from mahlzeit import cli
from mahlzeit.models import ChangeRecord, User
from mahlzeit.services import auth, invites

runner = CliRunner()


@pytest.fixture(autouse=True)
def use_test_session(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def shared() -> Iterator[Session]:
        yield db

    monkeypatch.setattr(cli, "session", shared)


def test_create_admin_with_password_from_env(db: Session) -> None:
    result = runner.invoke(
        cli.app,
        [
            "create-admin",
            "--email",
            "Jonas@Example.org",
            "--name",
            "Jonas",
            "--household",
            "Zuhause",
        ],
        env={"MAHLZEIT_PASSWORD": "a long password"},
    )
    assert result.exit_code == 0, result.output
    user = db.scalars(select(User)).one()
    assert (user.email, user.is_admin, user.household.name) == (
        "jonas@example.org",
        True,
        "Zuhause",
    )
    assert {c.client for c in db.scalars(select(ChangeRecord))} == {"cli"}


def test_create_admin_with_prompted_password(db: Session) -> None:
    result = runner.invoke(
        cli.app,
        ["create-admin", "--email", "a@example.org", "--name", "A"],
        input="a long password\na long password\n",
    )
    assert result.exit_code == 0, result.output
    assert "a long password" not in result.output


def test_create_admin_rejects_weak_password() -> None:
    result = runner.invoke(
        cli.app,
        ["create-admin", "--email", "a@example.org", "--name", "A"],
        env={"MAHLZEIT_PASSWORD": "short"},
    )
    assert result.exit_code == 1
    assert "password_too_short" in result.output


def test_invite_household_prints_a_working_link_and_code(db: Session) -> None:
    result = runner.invoke(cli.app, ["invite-household", "--language", "nl"])
    assert result.exit_code == 0, result.output
    lines = dict(line.split(": ", 1) for line in result.output.strip().splitlines())
    assert lines["Link"].startswith("http://localhost/join/")
    preview = invites.preview(db, lines["Code"])
    assert preview.kind == "household" and preview.language == "nl"


def test_reset_password_and_list_users(db: Session) -> None:
    runner.invoke(
        cli.app,
        ["create-admin", "--email", "a@example.org", "--name", "A"],
        env={"MAHLZEIT_PASSWORD": "a long password"},
    )
    result = runner.invoke(
        cli.app,
        ["reset-password", "--email", "a@example.org"],
        env={"MAHLZEIT_PASSWORD": "another password"},
    )
    assert result.exit_code == 0, result.output
    auth.login(db, email="a@example.org", password="another password", ip="1.1.1.1")
    listing = runner.invoke(cli.app, ["list-users"])
    assert "a@example.org" in listing.output and "(admin)" in listing.output


def test_reset_password_unknown_user() -> None:
    result = runner.invoke(
        cli.app,
        ["reset-password", "--email", "x@example.org"],
        env={"MAHLZEIT_PASSWORD": "another password"},
    )
    assert result.exit_code == 1


def test_gen_secrets_prints_usable_values() -> None:
    from mahlzeit.security import crypto

    result = runner.invoke(cli.app, ["gen-secrets"])
    values = dict(line.split("=", 1) for line in result.output.strip().splitlines())
    assert set(values) == {
        "POSTGRES_PASSWORD",
        "ENCRYPTION_KEY",
        "VAPID_PRIVATE_KEY",
        "VAPID_PUBLIC_KEY",
    }
    assert (
        crypto.decrypt(
            crypto.encrypt(b"x", key=values["ENCRYPTION_KEY"]), key=values["ENCRYPTION_KEY"]
        )
        == b"x"
    )
