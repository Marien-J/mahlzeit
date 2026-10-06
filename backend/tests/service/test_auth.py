from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mahlzeit.domain.errors import Invalid, RateLimited, Unauthorized
from mahlzeit.models import AuthSession, ChangeRecord, Job, PasswordReset
from mahlzeit.security import tokens
from mahlzeit.services import auth
from tests import factories
from tests.factories import PASSWORD


def _login(
    db: Session, member: factories.Member, password: str = PASSWORD, ip: str = "10.0.0.1"
) -> auth.StartedSession:
    return auth.login(db, email=member.email, password=password, ip=ip)


class TestLogin:
    def test_login_creates_a_hashed_session(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        started = _login(db, jonas)
        stored = db.scalars(select(AuthSession).where(AuthSession.user_id == jonas.user.id)).one()
        assert stored.token_hash == tokens.hash_token(started.token)
        assert started.token not in stored.token_hash

    def test_email_is_case_insensitive(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        auth.login(db, email=jonas.email.upper(), password=PASSWORD, ip="1.1.1.1")

    def test_wrong_password_and_unknown_email_look_the_same(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        with pytest.raises(Unauthorized) as wrong:
            _login(db, jonas, password="wrong password!")
        with pytest.raises(Unauthorized) as unknown:
            auth.login(db, email="nobody@example.org", password=PASSWORD, ip="1.1.1.1")
        assert wrong.value.code == unknown.value.code == "invalid_credentials"

    def test_five_failures_lock_the_email_even_with_the_right_password(
        self, db: Session, clock
    ) -> None:
        jonas, _ = factories.household(db)
        for i in range(5):
            with pytest.raises(Unauthorized):
                _login(db, jonas, password="nope nope nope", ip=f"10.0.0.{i}")
        with pytest.raises(RateLimited):
            _login(db, jonas)
        clock.advance(timedelta(minutes=16))
        _login(db, jonas)

    def test_twenty_failures_lock_the_ip(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        for i in range(20):
            with pytest.raises(Unauthorized):
                auth.login(db, email=f"x{i}@example.org", password="whatever123", ip="6.6.6.6")
        with pytest.raises(RateLimited):
            _login(db, jonas, ip="6.6.6.6")
        _login(db, jonas, ip="7.7.7.7")


class TestSessions:
    def test_resolve_returns_actor(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        started = _login(db, jonas)
        current = auth.resolve(db, started.token)
        assert current.actor.user_id == jonas.user.id
        assert current.actor.household_id == jonas.user.household_id
        assert current.actor.is_admin

    @pytest.mark.parametrize("token", [None, "", "not-a-real-token"])
    def test_resolve_rejects_bad_tokens(self, db: Session, token: str | None) -> None:
        with pytest.raises(Unauthorized):
            auth.resolve(db, token)

    def test_session_expires_after_inactivity(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        started = _login(db, jonas)
        clock.advance(timedelta(days=31))
        with pytest.raises(Unauthorized) as err:
            auth.resolve(db, started.token)
        assert err.value.code == "session_expired"

    def test_use_extends_the_session(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        started = _login(db, jonas)
        for _ in range(3):
            clock.advance(timedelta(days=20))
            auth.resolve(db, started.token)

    def test_logout_ends_only_that_session(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        phone, laptop = _login(db, jonas), _login(db, jonas)
        auth.logout(db, auth.resolve(db, phone.token))
        with pytest.raises(Unauthorized):
            auth.resolve(db, phone.token)
        auth.resolve(db, laptop.token)


class TestChangePassword:
    def test_requires_current_password(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        current = auth.resolve(db, _login(db, jonas).token)
        with pytest.raises(Invalid) as err:
            auth.change_password(db, current, old="wrong one!!", new="new password 1")
        assert err.value.code == "current_password_wrong"

    def test_applies_policy(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        current = auth.resolve(db, _login(db, jonas).token)
        with pytest.raises(Invalid):
            auth.change_password(db, current, old=PASSWORD, new="short")

    def test_keeps_this_session_and_ends_the_others(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        here, elsewhere = _login(db, jonas), _login(db, jonas)
        auth.change_password(db, auth.resolve(db, here.token), old=PASSWORD, new="new password 1")
        auth.resolve(db, here.token)
        with pytest.raises(Unauthorized):
            auth.resolve(db, elsewhere.token)
        auth.login(db, email=jonas.email, password="new password 1", ip="1.1.1.1")
        change = db.scalars(
            select(ChangeRecord).where(ChangeRecord.action == "password_changed")
        ).one()
        assert change.client == "ui"
        assert change.before is None and change.after is None  # never secrets


class TestPasswordReset:
    def test_without_smtp_nothing_happens(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        auth.request_password_reset(db, email=jonas.email)
        assert db.scalar(select(func.count()).select_from(PasswordReset)) == 0

    def test_with_smtp_a_token_and_an_email_job_are_created(self, db: Session, settings) -> None:
        settings(smtp_host="smtp.test", smtp_from="mahlzeit@example.org")
        jonas, _ = factories.household(db)
        auth.request_password_reset(db, email=jonas.email.upper())
        job = db.scalars(select(Job).where(Job.kind == "email.password_reset")).one()
        assert job.payload["user_id"] == str(jonas.user.id)
        assert job.payload["link"].startswith("http://localhost/reset/")

    def test_unknown_email_is_silent(self, db: Session, settings) -> None:
        settings(smtp_host="smtp.test", smtp_from="mahlzeit@example.org")
        auth.request_password_reset(db, email="nobody@example.org")
        assert db.scalar(select(func.count()).select_from(Job)) == 0

    def test_at_most_three_requests_per_hour(self, db: Session, settings) -> None:
        settings(smtp_host="smtp.test", smtp_from="mahlzeit@example.org")
        jonas, _ = factories.household(db)
        for _ in range(5):
            auth.request_password_reset(db, email=jonas.email)
        assert db.scalar(select(func.count()).select_from(PasswordReset)) == 3

    def _token(self, db: Session, member: factories.Member) -> str:
        auth.request_password_reset(db, email=member.email)
        job = db.scalars(select(Job).where(Job.kind == "email.password_reset")).all()[-1]
        return str(job.payload["link"]).rsplit("/", 1)[1]

    def test_confirm_sets_password_once_and_ends_sessions(self, db: Session, settings) -> None:
        settings(smtp_host="smtp.test", smtp_from="mahlzeit@example.org")
        jonas, _ = factories.household(db)
        old_session = _login(db, jonas)
        token = self._token(db, jonas)
        auth.confirm_password_reset(db, token=token, new="brand new secret")
        with pytest.raises(Unauthorized):
            auth.resolve(db, old_session.token)
        auth.login(db, email=jonas.email, password="brand new secret", ip="1.1.1.1")
        with pytest.raises(Invalid) as err:
            auth.confirm_password_reset(db, token=token, new="another secret 1")
        assert err.value.code == "reset_token_invalid"

    def test_token_expires_after_an_hour(self, db: Session, settings, clock) -> None:
        settings(smtp_host="smtp.test", smtp_from="mahlzeit@example.org")
        jonas, _ = factories.household(db)
        token = self._token(db, jonas)
        clock.advance(timedelta(minutes=61))
        with pytest.raises(Invalid):
            auth.confirm_password_reset(db, token=token, new="brand new secret")

    def test_admin_command_sets_password(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        auth.admin_set_password(db, email=jonas.email, new="set by admin 1")
        auth.login(db, email=jonas.email, password="set by admin 1", ip="1.1.1.1")
        change = db.scalars(
            select(ChangeRecord).where(ChangeRecord.action == "password_changed")
        ).one()
        assert change.client == "cli"
