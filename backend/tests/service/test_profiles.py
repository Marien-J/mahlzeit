import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from mahlzeit.domain.errors import Invalid
from mahlzeit.models import ChangeRecord
from mahlzeit.services import households, profiles
from tests import factories


def _changes(db: Session, entity: str) -> list[ChangeRecord]:
    return list(
        db.scalars(
            select(ChangeRecord).where(
                ChangeRecord.entity == entity,
                ChangeRecord.action != "created",
                ChangeRecord.action != "joined",
            )
        )
    )


class TestUserSettings:
    def test_switch_language_and_time_zone(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        me = profiles.update_user(db, jonas.actor, language="nl", time_zone="Europe/Amsterdam")
        assert (me.user.language, me.user.time_zone) == ("nl", "Europe/Amsterdam")
        (change,) = _changes(db, "user")
        assert change.before == {"language": "de", "time_zone": "Europe/Berlin"}
        assert change.after == {"language": "nl", "time_zone": "Europe/Amsterdam"}
        assert change.client == "ui"

    def test_unchanged_values_write_no_record(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        profiles.update_user(db, jonas.actor, language="de", display_name="Jonas")
        assert _changes(db, "user") == []

    @pytest.mark.parametrize(
        "kw", [{"language": "fr"}, {"time_zone": "Nowhere"}, {"display_name": ""}]
    )
    def test_rejects_invalid(self, db: Session, kw: dict[str, str]) -> None:
        jonas, _ = factories.household(db)
        with pytest.raises(Invalid):
            profiles.update_user(db, jonas.actor, **kw)


class TestSharingSwitches:
    def test_defaults(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        p = profiles.get_me(db, jonas.actor).profile
        assert (p.show_workouts, p.show_body, p.share_ai_usage, p.start_screen, p.push_offers) == (
            True,
            False,
            False,
            "today",
            True,
        )

    def test_update_only_touches_own_profile(self, db: Session) -> None:
        jonas, partner = factories.household(db)
        profiles.update_profile(db, partner.actor, show_body=True, start_screen="list")
        assert profiles.get_me(db, partner.actor).profile.show_body
        assert not profiles.get_me(db, jonas.actor).profile.show_body

    def test_start_screen_values(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        with pytest.raises(Invalid):
            profiles.update_profile(db, jonas.actor, start_screen="plan")


class TestHousehold:
    def test_members_in_join_order(self, db: Session) -> None:
        _, partner = factories.household(db)
        h = households.get(db, partner.actor)
        assert [m.display_name for m in h.members] == ["Jonas", "Partner"]

    def test_never_shows_another_household(self, db: Session) -> None:
        mine, _ = factories.household(db, "Mine", "MyPartner")
        factories.household(db, "Theirs", "TheirPartner")
        assert {m.display_name for m in households.get(db, mine.actor).members} == {
            "Mine",
            "MyPartner",
        }

    def test_rename_records_change(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        households.rename(db, jonas.actor, "  Zuhause ")
        assert households.get(db, jonas.actor).name == "Zuhause"
        (change,) = _changes(db, "household")
        assert change.after == {"name": "Zuhause"}
