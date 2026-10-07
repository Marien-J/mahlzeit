"""Rules for the shared shopping list: one-field entry, per-field last write wins, aisle order.

Offline phones send their changes later, with the time each change was made. Every field keeps
the time of its last change, so an old offline change never overwrites a newer one, field by
field. Removing an item is final (a tombstone); a removed item never comes back by a late edit.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from mahlzeit.domain.catalogue import Category
from mahlzeit.domain.errors import Invalid

BUILTIN_STORES = ("aldi", "lidl", "edeka", "rewe", "netto", "penny", "dm", "other")
FIELDS = frozenset({"text", "item_id", "quantity", "store_id", "category", "checked"})
AISLES = [c.value for c in Category]

_UNIT = r"(?:g|kg|ml|l|stk|stück|st|pck|pkg|packung|dose|dosen|flasche|flaschen|bund|becher)"
_NUM = r"\d+(?:[.,]\d+)?"
_TIMES = "[x\u00d7]"  # x or the multiplication sign
_LEADING = re.compile(
    rf"^(?P<n>{_NUM})\s*(?:(?P<x>{_TIMES})|(?P<u>{_UNIT})\b\.?)?\s+(?P<name>.+)$", re.IGNORECASE
)
_TRAILING = re.compile(
    rf"^(?P<name>.+?)\s+(?:{_TIMES}\s*(?P<n1>{_NUM})|(?P<n2>{_NUM})\s*(?:{_TIMES}|(?P<u>{_UNIT})\b\.?)?)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Entry:
    quantity: str | None
    name: str


def check_text(text: str) -> str:
    cleaned = " ".join(text.split())[:120]
    if not cleaned:
        raise Invalid("list_text_empty")
    return cleaned


def check_quantity(quantity: str | None) -> str | None:
    cleaned = " ".join((quantity or "").split())[:40]
    return cleaned or None


def check_store_name(name: str) -> str:
    cleaned = " ".join(name.split())[:40]
    if not cleaned:
        raise Invalid("store_name_empty")
    return cleaned


def _quantity(number: str, unit: str | None) -> str:
    return f"{number} {unit}" if unit else number


def parse_entry(raw: str) -> Entry:
    """'2 Milch', '500 g Hack', 'Milch x2' → quantity and name. Anything else is all name."""
    text = check_text(raw)
    if m := _LEADING.match(text):
        name = m.group("name").strip()
        if name and not name[0].isdigit():
            return Entry(_quantity(m.group("n"), m.group("u")), name)
    if m := _TRAILING.match(text):
        name = m.group("name").strip()
        number = m.group("n1") or m.group("n2")
        if name and not name.endswith(","):
            return Entry(_quantity(number, m.group("u")), name)
    return Entry(None, text)


@dataclass(frozen=True)
class FieldState:
    values: Mapping[str, Any]
    times: Mapping[str, datetime]


@dataclass(frozen=True)
class MergeResult:
    state: FieldState
    changed: set[str] = field(default_factory=set)


def merge(
    state: FieldState, patch: Mapping[str, Any], *, at: datetime, now: datetime
) -> MergeResult:
    """Apply a change made at `at` field by field: it wins where it is not older than the field's
    last change. A clock ahead of the server counts as now, so a wrong phone clock cannot pin a
    field forever."""
    unknown = set(patch) - FIELDS
    if unknown:
        raise ValueError(f"unknown list fields: {sorted(unknown)}")
    when = min(at, now)
    values, times = dict(state.values), dict(state.times)
    changed: set[str] = set()
    for name, value in patch.items():
        last = times.get(name)
        if last is not None and when < last:
            continue
        if values.get(name) != value:
            changed.add(name)
        values[name] = value
        times[name] = max(when, last) if last else when
    return MergeResult(FieldState(values, times), changed)


@dataclass(frozen=True)
class Row:
    key: Any
    category: str
    checked: bool
    added: datetime


def ordered(rows: Iterable[Row]) -> list[Row]:
    """Aisle by aisle in the fixed category order, oldest first; checked items at the bottom."""

    def rank(r: Row) -> tuple[bool, int, datetime, str]:
        aisle = AISLES.index(r.category) if r.category in AISLES else len(AISLES)
        # Ids are UUIDv7, so they break ties in creation order (items added in one batch).
        return (r.checked, aisle, r.added, str(r.key))

    return sorted(rows, key=rank)
