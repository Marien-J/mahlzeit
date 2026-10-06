from datetime import UTC, datetime, timedelta

import pytest

from mahlzeit.domain import accounts
from mahlzeit.domain.accounts import InviteKind, InviteStatus
from mahlzeit.domain.errors import Conflict, Invalid, RateLimited

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


class TestPasswordPolicy:
    def test_accepts_ten_characters(self) -> None:
        accounts.check_password("abcdefghij")

    @pytest.mark.parametrize("password", ["", "short", "123456789"])
    def test_rejects_short(self, password: str) -> None:
        with pytest.raises(Invalid) as err:
            accounts.check_password(password)
        assert err.value.code == "password_too_short"

    def test_rejects_absurdly_long(self) -> None:
        with pytest.raises(Invalid) as err:
            accounts.check_password("x" * 257)
        assert err.value.code == "password_too_long"


class TestEmail:
    def test_normalises_case_and_space(self) -> None:
        assert accounts.normalize_email("  Jonas@Example.ORG ") == "jonas@example.org"


class TestInviteCode:
    def test_generated_code_uses_unambiguous_alphabet(self) -> None:
        for _ in range(200):
            code = accounts.new_invite_code()
            assert len(code) == 8
            assert set(code) <= set(accounts.CODE_ALPHABET)
            assert not set(code) & set("01ILOU")

    @pytest.mark.parametrize("typed", ["abcd-efgh", " ABCD EFGH ", "abcdefgh", "ABCD-EFGH"])
    def test_normalises_typed_code(self, typed: str) -> None:
        assert accounts.normalize_invite_code(typed) == "ABCDEFGH"

    def test_formats_for_display(self) -> None:
        assert accounts.format_invite_code("ABCDEFGH") == "ABCD-EFGH"


class TestInviteStatus:
    def _status(self, **kw: object) -> InviteStatus:
        args: dict[str, object] = {
            "expires_at": NOW + timedelta(days=1),
            "accepted_at": None,
            "revoked_at": None,
            "now": NOW,
        }
        args.update(kw)
        return accounts.invite_status(**args)  # type: ignore[arg-type]

    def test_pending(self) -> None:
        assert self._status() is InviteStatus.PENDING

    def test_expired_at_exact_boundary(self) -> None:
        assert self._status(expires_at=NOW) is InviteStatus.EXPIRED

    def test_accepted_wins_over_expiry(self) -> None:
        assert (
            self._status(expires_at=NOW - timedelta(days=1), accepted_at=NOW)
            is InviteStatus.ACCEPTED
        )

    def test_revoked(self) -> None:
        assert self._status(revoked_at=NOW) is InviteStatus.REVOKED


class TestAcceptInvite:
    def test_pending_partner_invite_with_room(self) -> None:
        accounts.check_invite_acceptable(InviteStatus.PENDING, InviteKind.PARTNER, member_count=1)

    def test_household_invite_ignores_member_count(self) -> None:
        accounts.check_invite_acceptable(InviteStatus.PENDING, InviteKind.HOUSEHOLD, member_count=0)

    @pytest.mark.parametrize(
        ("status", "code"),
        [
            (InviteStatus.EXPIRED, "invite_expired"),
            (InviteStatus.ACCEPTED, "invite_used"),
            (InviteStatus.REVOKED, "invite_revoked"),
        ],
    )
    def test_rejects_unusable(self, status: InviteStatus, code: str) -> None:
        with pytest.raises(Conflict) as err:
            accounts.check_invite_acceptable(status, InviteKind.PARTNER, member_count=1)
        assert err.value.code == code

    def test_household_is_full_at_four(self) -> None:
        with pytest.raises(Conflict) as err:
            accounts.check_invite_acceptable(
                InviteStatus.PENDING, InviteKind.PARTNER, member_count=accounts.MAX_MEMBERS
            )
        assert err.value.code == "household_full"

    def test_cannot_issue_partner_invite_when_full(self) -> None:
        with pytest.raises(Conflict) as err:
            accounts.check_can_invite_partner(member_count=4, pending_invites=0)
        assert err.value.code == "household_full"

    def test_pending_invites_count_towards_the_limit(self) -> None:
        accounts.check_can_invite_partner(member_count=2, pending_invites=1)
        with pytest.raises(Conflict):
            accounts.check_can_invite_partner(member_count=2, pending_invites=2)


class TestLoginRateLimit:
    def test_allows_below_limits(self) -> None:
        accounts.check_login_allowed(email_failures=4, ip_failures=19)

    def test_blocks_on_email_failures(self) -> None:
        with pytest.raises(RateLimited) as err:
            accounts.check_login_allowed(email_failures=5, ip_failures=0)
        assert err.value.code == "too_many_attempts"

    def test_blocks_on_ip_failures(self) -> None:
        with pytest.raises(RateLimited):
            accounts.check_login_allowed(email_failures=0, ip_failures=20)


class TestProfileFields:
    def test_display_name_is_trimmed(self) -> None:
        assert accounts.clean_display_name("  Jonas ") == "Jonas"

    @pytest.mark.parametrize("name", ["", "   ", "x" * 61])
    def test_display_name_bounds(self, name: str) -> None:
        with pytest.raises(Invalid) as err:
            accounts.clean_display_name(name)
        assert err.value.code == "display_name_invalid"

    def test_household_name_bounds(self) -> None:
        assert accounts.clean_household_name(" Küche ") == "Küche"
        with pytest.raises(Invalid):
            accounts.clean_household_name("x" * 81)

    @pytest.mark.parametrize("tz", ["Europe/Berlin", "Europe/Amsterdam", "UTC"])
    def test_known_time_zones(self, tz: str) -> None:
        accounts.check_time_zone(tz)

    @pytest.mark.parametrize("tz", ["", "Mars/Olympus", "../../etc/passwd"])
    def test_unknown_time_zones(self, tz: str) -> None:
        with pytest.raises(Invalid) as err:
            accounts.check_time_zone(tz)
        assert err.value.code == "time_zone_invalid"

    def test_languages(self) -> None:
        for lang in ("de", "en", "nl"):
            accounts.check_language(lang)
        with pytest.raises(Invalid) as err:
            accounts.check_language("fr")
        assert err.value.code == "language_invalid"


class TestCleanEmail:
    def test_accepts_and_normalises(self) -> None:
        assert accounts.clean_email(" A@B.de ") == "a@b.de"

    @pytest.mark.parametrize("email", ["", "no-at", "a@", "@b.de", "a@b", "a b@c.de", "a@b@c.de"])
    def test_rejects(self, email: str) -> None:
        with pytest.raises(Invalid) as err:
            accounts.clean_email(email)
        assert err.value.code == "email_invalid"
