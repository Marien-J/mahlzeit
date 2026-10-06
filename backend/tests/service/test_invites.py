from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from mahlzeit.domain.accounts import InviteKind, InviteStatus
from mahlzeit.domain.errors import Conflict, Invalid, NotFound
from mahlzeit.models import ChangeRecord, Household, Invite, User
from mahlzeit.services import invites
from tests import factories
from tests.factories import PASSWORD


def _accept(
    db: Session, key: str, email: str = "new@example.org", **kw: str
) -> invites.StartedSession:
    args = {
        "key": key,
        "email": email,
        "password": PASSWORD,
        "display_name": "Neu",
        "language": "nl",
        "time_zone": "Europe/Amsterdam",
    }
    args.update(kw)
    return invites.accept(db, **args)


class TestHouseholdInvite:
    def test_creates_a_new_household(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        issued = invites.create_household_invite(db, language="nl")
        started = _accept(db, issued.token, household_name="Familie Neu")
        user = started.user
        assert user.household_id != jonas.user.household_id
        assert db.get_one(Household, user.household_id).name == "Familie Neu"
        assert not user.is_admin
        actions = db.scalars(
            select(ChangeRecord.entity + ":" + ChangeRecord.action).where(
                ChangeRecord.household_id == user.household_id
            )
        ).all()
        assert set(actions) == {"household:created", "user:joined"}

    def test_records_cli_as_issuer(self, db: Session) -> None:
        issued = invites.create_household_invite(db)
        change = db.scalars(
            select(ChangeRecord).where(ChangeRecord.entity_id == issued.invite.id)
        ).one()
        assert change.client == "cli"

    def test_invite_kind_and_hashes(self, db: Session) -> None:
        issued = invites.create_household_invite(db)
        stored = db.get_one(Invite, issued.invite.id)
        assert stored.kind == InviteKind.HOUSEHOLD
        assert issued.token not in stored.token_hash
        assert issued.code not in stored.code_hash


class TestPartnerInvite:
    def test_partner_joins_the_inviters_household(self, db: Session) -> None:
        (jonas,) = factories.household(db, "Jonas")
        issued = invites.create_partner_invite(db, jonas.actor)
        started = _accept(db, issued.token)
        assert started.user.household_id == jonas.user.household_id

    @pytest.mark.parametrize(
        "transform", [str.lower, lambda c: f"{c[:4]}-{c[4:]}", lambda c: f" {c} "]
    )
    def test_accept_by_typed_code(self, db: Session, transform) -> None:
        (jonas,) = factories.household(db, "Jonas")
        issued = invites.create_partner_invite(db, jonas.actor)
        started = _accept(db, transform(issued.code))
        assert started.user.household_id == jonas.user.household_id

    def test_preview_names_inviter_and_household(self, db: Session) -> None:
        (jonas,) = factories.household(db, "Jonas")
        issued = invites.create_partner_invite(db, jonas.actor)
        p = invites.preview(db, issued.display_code)
        assert (p.kind, p.status, p.inviter_name, p.household_name) == (
            InviteKind.PARTNER,
            InviteStatus.PENDING,
            "Jonas",
            "Jonas",
        )

    def test_unknown_key(self, db: Session) -> None:
        with pytest.raises(NotFound) as err:
            invites.preview(db, "ABCDEFGH")
        assert err.value.code == "invite_not_found"

    def test_single_use(self, db: Session) -> None:
        (jonas,) = factories.household(db, "Jonas")
        issued = invites.create_partner_invite(db, jonas.actor)
        _accept(db, issued.token)
        with pytest.raises(Conflict) as err:
            _accept(db, issued.token, email="second@example.org")
        assert err.value.code == "invite_used"

    def test_expires_after_seven_days(self, db: Session, clock) -> None:
        (jonas,) = factories.household(db, "Jonas")
        issued = invites.create_partner_invite(db, jonas.actor)
        clock.advance(timedelta(days=7))
        with pytest.raises(Conflict) as err:
            _accept(db, issued.token)
        assert err.value.code == "invite_expired"

    def test_revoked(self, db: Session) -> None:
        (jonas,) = factories.household(db, "Jonas")
        issued = invites.create_partner_invite(db, jonas.actor)
        invites.revoke_invite(db, jonas.actor, issued.invite.id)
        with pytest.raises(Conflict) as err:
            _accept(db, issued.token)
        assert err.value.code == "invite_revoked"
        assert invites.list_partner_invites(db, jonas.actor) == []

    def test_email_must_be_free(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        issued = invites.create_partner_invite(db, jonas.actor)
        with pytest.raises(Conflict) as err:
            _accept(db, issued.token, email=jonas.email.upper())
        assert err.value.code == "email_taken"
        assert invites.preview(db, issued.token).status is InviteStatus.PENDING

    def test_validates_input_before_using_the_invite(self, db: Session) -> None:
        (jonas,) = factories.household(db, "Jonas")
        issued = invites.create_partner_invite(db, jonas.actor)
        for bad in (
            {"password": "short"},
            {"email": "nope"},
            {"time_zone": "Mars/Base"},
            {"language": "fr"},
            {"display_name": " "},
        ):
            with pytest.raises(Invalid):
                _accept(db, issued.token, **bad)
        assert invites.preview(db, issued.token).status is InviteStatus.PENDING


class TestMemberLimit:
    def test_four_members_fill_the_household(self, db: Session) -> None:
        a, *_ = factories.household(db, "A", "B", "C", "D")
        with pytest.raises(Conflict) as err:
            invites.create_partner_invite(db, a.actor)
        assert err.value.code == "household_full"

    def test_open_invites_reserve_seats(self, db: Session) -> None:
        a, _ = factories.household(db, "A", "B")
        invites.create_partner_invite(db, a.actor)
        invites.create_partner_invite(db, a.actor)
        with pytest.raises(Conflict):
            invites.create_partner_invite(db, a.actor)

    def test_acceptance_rechecks_the_limit(self, db: Session) -> None:
        a, _, _ = factories.household(db, "A", "B", "C")
        fourth = invites.create_partner_invite(db, a.actor)
        # An invite that bypassed the seat reservation, e.g. issued under an older rule.
        extra = invites._issue(
            db,
            kind=InviteKind.PARTNER,
            household_id=a.user.household_id,
            created_by=a.user.id,
            language="de",
            note=None,
        )
        db.commit()
        _accept(db, fourth.token, email="d@example.org")
        with pytest.raises(Conflict) as err:
            _accept(db, extra.token, email="e@example.org")
        assert err.value.code == "household_full"
        members = db.scalars(select(User).where(User.household_id == a.user.household_id)).all()
        assert len(members) == 4


class TestCrossHousehold:
    def test_cannot_revoke_another_households_invite(self, db: Session) -> None:
        mine, _ = factories.household(db)
        theirs, _ = factories.household(db)
        issued = invites.create_partner_invite(db, theirs.actor)
        with pytest.raises(NotFound):
            invites.revoke_invite(db, mine.actor, issued.invite.id)
        assert invites.preview(db, issued.token).status is InviteStatus.PENDING

    def test_cannot_revoke_a_household_invite(self, db: Session) -> None:
        mine, _ = factories.household(db)
        issued = invites.create_household_invite(db)
        with pytest.raises(NotFound):
            invites.revoke_invite(db, mine.actor, issued.invite.id)

    def test_lists_only_own_invites(self, db: Session) -> None:
        mine, _ = factories.household(db)
        theirs, _ = factories.household(db)
        invites.create_partner_invite(db, theirs.actor)
        assert invites.list_partner_invites(db, mine.actor) == []
