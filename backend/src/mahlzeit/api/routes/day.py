from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, status

from mahlzeit import views
from mahlzeit.api import convert
from mahlzeit.api.deps import Current, CurrentWrite, Db
from mahlzeit.api.schemas import (
    CopyDayIn,
    CopyEntryIn,
    DayTypeIn,
    EntryIn,
    EntryPatchIn,
    EntryStateIn,
    ExactAmountsIn,
    MoveEntryIn,
    ShareIn,
)
from mahlzeit.domain.day import EntryState, Slot
from mahlzeit.domain.targets import DayType
from mahlzeit.services import day, targets

router = APIRouter(tags=["day"])


@router.get("/days/{day_}", response_model=views.DayOut)
def get_day(day_: date, current: Current, db: Db) -> views.DayOut:
    return views.day(day.get_day(db, current.actor, day_), current.user.language, current.user.id)


@router.post("/entries", response_model=views.EntryOut, status_code=status.HTTP_201_CREATED)
def log_food(body: EntryIn, current: CurrentWrite, db: Db) -> views.EntryOut:
    entry = day.log_food(db, current.actor, convert.entry_input(body))
    return views.entry(entry, current.user.language, current.user.id)


@router.patch("/entries/{entry_id}", response_model=views.EntryOut)
def update_entry(
    entry_id: uuid.UUID, body: EntryPatchIn, current: CurrentWrite, db: Db
) -> views.EntryOut:
    entry = day.update_entry(db, current.actor, entry_id, convert.entry_patch(body))
    return views.entry(entry, current.user.language, current.user.id)


@router.post("/entries/{entry_id}/state", response_model=views.EntryOut)
def set_entry_state(
    entry_id: uuid.UUID, body: EntryStateIn, current: CurrentWrite, db: Db
) -> views.EntryOut:
    entry = day.set_state(db, current.actor, entry_id, EntryState(body.state))
    return views.entry(entry, current.user.language, current.user.id)


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(entry_id: uuid.UUID, current: CurrentWrite, db: Db) -> None:
    day.delete_entry(db, current.actor, entry_id)


@router.put("/entries/{entry_id}/share", response_model=views.EntryOut)
def set_share(entry_id: uuid.UUID, body: ShareIn, current: CurrentWrite, db: Db) -> views.EntryOut:
    entry = day.set_share(db, current.actor, entry_id, body.share)
    return views.entry(entry, current.user.language, current.user.id)


@router.put("/entries/{entry_id}/exact-amounts", response_model=views.EntryOut)
def set_exact_amounts(
    entry_id: uuid.UUID, body: ExactAmountsIn, current: CurrentWrite, db: Db
) -> views.EntryOut:
    entry = day.set_exact_amounts(db, current.actor, entry_id, body.amounts)
    return views.entry(entry, current.user.language, current.user.id)


@router.post("/entries/{entry_id}/move", response_model=list[views.EntryOut])
def move_entry(
    entry_id: uuid.UUID, body: MoveEntryIn, current: CurrentWrite, db: Db
) -> list[views.EntryOut]:
    """Drag an entry before another of my day (or last); the entries whose time changed."""
    moved = day.move_entry(db, current.actor, entry_id, before_id=body.before_id)
    return [views.entry(e, current.user.language, current.user.id) for e in moved]


@router.post(
    "/entries/{entry_id}/copy", response_model=views.EntryOut, status_code=status.HTTP_201_CREATED
)
def copy_entry(
    entry_id: uuid.UUID, body: CopyEntryIn, current: CurrentWrite, db: Db
) -> views.EntryOut:
    entry = day.copy_entry(
        db, current.actor, entry_id, day=body.day, slot=Slot(body.slot) if body.slot else None
    )
    return views.entry(entry, current.user.language, current.user.id)


@router.post(
    "/days/{day_}/copy", response_model=list[views.EntryOut], status_code=status.HTTP_201_CREATED
)
def copy_day(day_: date, body: CopyDayIn, current: CurrentWrite, db: Db) -> list[views.EntryOut]:
    entries = day.copy_day(db, current.actor, source_day=body.source_day, day=day_)
    return [views.entry(e, current.user.language, current.user.id) for e in entries]


@router.put("/days/{day_}/day-type", status_code=status.HTTP_204_NO_CONTENT)
def set_day_type(day_: date, body: DayTypeIn, current: CurrentWrite, db: Db) -> None:
    targets.set_day_type(db, current.actor, day_, DayType(body.day_type) if body.day_type else None)
