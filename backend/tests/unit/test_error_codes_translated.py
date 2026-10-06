"""Every error code the server can send has a message in the UI catalogues."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "backend" / "src" / "mahlzeit"
RAISED = re.compile(r"\b(?:Invalid|NotFound|Forbidden|Unauthorized|Conflict|RateLimited)\(\s*\"([a-z_]+)\"")
EXTRA = {"not_found", "forbidden", "not_authenticated", "origin_not_allowed", "validation_error"}


def _server_codes() -> set[str]:
    codes = set(EXTRA)
    for path in SRC.rglob("*.py"):
        codes |= set(RAISED.findall(path.read_text()))
    return codes


def test_codes_were_found() -> None:
    assert {"invalid_credentials", "household_full", "csrf_failed"} <= _server_codes()


def test_every_code_has_a_translation() -> None:
    for lang in ("de", "en", "nl"):
        catalogue = json.loads((ROOT / "frontend/src/i18n/locales" / f"{lang}.json").read_text())
        missing = _server_codes() - set(catalogue["errors"])
        assert not missing, f"{lang}.json lacks errors.{sorted(missing)}"
