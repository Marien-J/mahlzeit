import pytest

from mahlzeit.config import Settings
from mahlzeit.security.crypto import new_key

GOOD = {
    "env": "production",
    "base_url": "https://mahlzeit.example.org",
    "encryption_key": new_key(),
    "database_url": "postgresql+psycopg://u:p@db/m",
    "vapid_private_key": "",
    "vapid_public_key": "",
    "vapid_subject": "",
    "smtp_host": "",
    "smtp_from": "",
}


def test_production_settings_pass() -> None:
    assert Settings(**GOOD).problems() == []


@pytest.mark.parametrize(
    ("override", "problem"),
    [
        ({"encryption_key": ""}, "ENCRYPTION_KEY"),
        ({"encryption_key": "short"}, "ENCRYPTION_KEY"),
        ({"base_url": "localhost"}, "BASE_URL"),
        ({"vapid_private_key": "x"}, "VAPID"),
        ({"smtp_host": "smtp.example.org"}, "SMTP_FROM"),
    ],
)
def test_production_settings_problems(override: dict[str, str], problem: str) -> None:
    problems = Settings(**{**GOOD, **override}).problems()
    assert any(problem in p for p in problems), problems


def test_allowed_origins() -> None:
    s = Settings(base_url="https://m.example.org/", extra_origins="http://localhost:5173, ")
    assert s.allowed_origins == {"https://m.example.org", "http://localhost:5173"}


def test_http_base_url_is_allowed_for_localhost() -> None:
    assert Settings(**{**GOOD, "base_url": "http://localhost"}).problems() == []


def test_keys_without_subject_still_start_and_enable_push() -> None:
    # scripts/init-env.sh writes the keys; the contact address is optional.
    s = Settings(**{**GOOD, "vapid_private_key": "priv", "vapid_public_key": "pub"})
    assert s.problems() == []
    assert s.push_enabled
    assert s.vapid_contact == "https://mahlzeit.example.org"


def test_explicit_subject_wins() -> None:
    s = Settings(
        **{
            **GOOD,
            "vapid_private_key": "p",
            "vapid_public_key": "q",
            "vapid_subject": "mailto:jonas@example.org",
        }
    )
    assert s.vapid_contact == "mailto:jonas@example.org"


def test_local_subject_falls_back_to_mailto() -> None:
    s = Settings(**{**GOOD, "base_url": "http://localhost"})
    assert s.vapid_contact.startswith("mailto:")


def test_localhost_also_allows_the_loopback_address() -> None:
    assert Settings(base_url="http://localhost", extra_origins="").allowed_origins == {
        "http://localhost",
        "http://127.0.0.1",
    }
    assert Settings(base_url="http://localhost:8088", extra_origins="").allowed_origins == {
        "http://localhost:8088",
        "http://127.0.0.1:8088",
    }
    assert Settings(base_url="https://m.example.org", extra_origins="").allowed_origins == {
        "https://m.example.org"
    }
