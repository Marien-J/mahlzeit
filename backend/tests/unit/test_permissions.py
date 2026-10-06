import uuid

import pytest

from mahlzeit.domain.errors import Forbidden, NotFound
from mahlzeit.domain.permissions import (
    Actor,
    Area,
    Client,
    Visibility,
    can_view,
    require_admin,
    require_household,
)

HOME = uuid.uuid4()
OTHER = uuid.uuid4()


def actor(household: uuid.UUID = HOME, *, admin: bool = False) -> Actor:
    return Actor(user_id=uuid.uuid4(), household_id=household, client=Client.UI, is_admin=admin)


class TestHouseholdScope:
    def test_same_household_passes(self) -> None:
        require_household(actor(), HOME)

    def test_other_household_looks_like_not_found(self) -> None:
        # Never reveal that a row exists in another household.
        with pytest.raises(NotFound):
            require_household(actor(), OTHER)

    def test_admin_flag_does_not_cross_households(self) -> None:
        with pytest.raises(NotFound):
            require_household(actor(admin=True), OTHER)


class TestAdmin:
    def test_requires_flag(self) -> None:
        with pytest.raises(Forbidden):
            require_admin(actor())
        require_admin(actor(admin=True))


DEFAULTS = Visibility(show_workouts=True, show_body=False, share_ai_usage=False)


class TestVisibility:
    def test_self_sees_everything(self) -> None:
        me = actor()
        for area in Area:
            assert can_view(me, me.user_id, HOME, Visibility(False, False, False), area)

    @pytest.mark.parametrize("area", [Area.FOOD, Area.TARGETS])
    def test_food_and_targets_always_visible_to_partner(self, area: Area) -> None:
        assert can_view(actor(), uuid.uuid4(), HOME, Visibility(False, False, False), area)

    def test_defaults_show_workouts_hide_body_and_ai_usage(self) -> None:
        partner = uuid.uuid4()
        assert can_view(actor(), partner, HOME, DEFAULTS, Area.WORKOUTS)
        assert not can_view(actor(), partner, HOME, DEFAULTS, Area.BODY)
        assert not can_view(actor(), partner, HOME, DEFAULTS, Area.AI_USAGE)

    def test_toggles_open_and_close(self) -> None:
        partner = uuid.uuid4()
        shared = Visibility(show_workouts=False, show_body=True, share_ai_usage=True)
        assert not can_view(actor(), partner, HOME, shared, Area.WORKOUTS)
        assert can_view(actor(), partner, HOME, shared, Area.BODY)
        assert can_view(actor(), partner, HOME, shared, Area.AI_USAGE)

    @pytest.mark.parametrize("area", list(Area))
    def test_other_household_sees_nothing(self, area: Area) -> None:
        everything = Visibility(True, True, True)
        assert not can_view(actor(), uuid.uuid4(), OTHER, everything, area)
