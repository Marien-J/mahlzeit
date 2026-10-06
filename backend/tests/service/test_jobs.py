from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mahlzeit.jobs import worker
from mahlzeit.jobs.registry import HANDLERS, Deps
from mahlzeit.models import AuthSession, Job, LoginAttempt
from mahlzeit.services import auth, maintenance, queue
from tests import factories
from tests.service.test_push import FakeSender


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    def send(self, *, to: str, subject: str, body: str) -> None:
        self.sent.append({"to": to, "subject": subject, "body": body})


def deps() -> Deps:
    return Deps(mailer=FakeMailer(), push_sender=FakeSender())


class TestQueue:
    def test_claim_complete(self, db: Session, clock) -> None:
        queue.enqueue(db, "maintenance.purge")
        db.commit()
        job = queue.claim(db)
        assert job is not None and job.status == "running" and job.attempts == 1
        assert queue.claim(db) is None
        queue.complete(db, job)
        assert job.status == "done"

    def test_future_jobs_wait(self, db: Session, clock) -> None:
        queue.enqueue(db, "maintenance.purge", run_at=clock.current + timedelta(minutes=5))
        db.commit()
        assert queue.claim(db) is None
        clock.advance(timedelta(minutes=5))
        assert queue.claim(db) is not None

    def test_dedupe_key(self, db: Session) -> None:
        for _ in range(3):
            queue.enqueue(db, "maintenance.purge", dedupe_key="once")
        db.commit()
        assert db.scalar(select(func.count()).select_from(Job)) == 1

    def test_failures_back_off_then_give_up(self, db: Session, clock) -> None:
        queue.enqueue(db, "nope", max_attempts=2)
        db.commit()
        d = deps()
        assert worker.run_one(db, d)
        job = db.scalars(select(Job)).one()
        assert job.status == "queued" and "no handler" in (job.last_error or "")
        assert job.run_at == clock.current + timedelta(seconds=30)
        clock.advance(timedelta(seconds=30))
        assert worker.run_one(db, d)
        assert job.status == "failed"
        assert not worker.run_one(db, d)

    def test_stale_running_jobs_are_reclaimed(self, db: Session, clock) -> None:
        queue.enqueue(db, "maintenance.purge")
        db.commit()
        assert queue.claim(db) is not None
        clock.advance(timedelta(minutes=11))
        again = queue.claim(db)
        assert again is not None and again.attempts == 2

    def test_recurring_schedule_is_idempotent(self, db: Session) -> None:
        worker.schedule_recurring(db)
        worker.schedule_recurring(db)
        assert db.scalar(select(func.count()).where(Job.kind == "maintenance.purge")) == 1

    def test_every_recurring_kind_has_a_handler(self) -> None:
        from mahlzeit.jobs.registry import RECURRING

        assert set(RECURRING) <= set(HANDLERS)


class TestHandlers:
    def test_password_reset_email(self, db: Session, settings) -> None:
        settings(smtp_host="smtp.test", smtp_from="mahlzeit@example.org")
        jonas, _ = factories.household(db)
        auth.request_password_reset(db, email=jonas.email)
        d = deps()
        assert worker.run_one(db, d)
        (mail,) = d.mailer.sent  # type: ignore[attr-defined]
        assert mail["to"] == jonas.email
        assert mail["subject"] == "Mahlzeit: Passwort zurücksetzen"
        assert "http://localhost/reset/" in mail["body"]
        assert "60 Minuten" in mail["body"]

    def test_purge_removes_expired_sign_in_data(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        auth.login(db, email=jonas.email, password=factories.PASSWORD, ip="1.1.1.1")
        clock.advance(timedelta(days=31))
        counts = maintenance.purge(db)
        assert counts["sessions"] == 2  # the login above and the partner's sign-up
        assert counts["login_attempts"] == 1
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 0
        assert db.scalar(select(func.count()).select_from(LoginAttempt)) == 0


class TestHeartbeat:
    def test_fresh_heartbeat_is_healthy(self, tmp_path) -> None:
        path = tmp_path / "beat"
        assert not worker.healthy(path)
        worker.beat(path)
        assert worker.healthy(path)

    def test_stale_heartbeat_is_unhealthy(self, tmp_path) -> None:
        import os

        path = tmp_path / "beat"
        worker.beat(path)
        os.utime(path, (0, 0))
        assert not worker.healthy(path)
