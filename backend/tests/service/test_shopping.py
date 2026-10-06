import uuid
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from mahlzeit.domain.errors import Conflict, Invalid, NotFound
from mahlzeit.ids import uuid7
from mahlzeit.models import ChangeRecord, Item, ShoppingListItem
from mahlzeit.services import events, shopping
from mahlzeit.services.shopping import Op
from tests import factories
from tests.conftest import Clock


def add(text: str, **fields: Any) -> Op:
    return Op(kind="add", id=uuid7(), fields={"text": text, **fields})


def texts(db: Session, actor: Any) -> list[str]:
    return [r.text for r in shopping.open_items(db, actor)]


def builtin(db: Session, actor: Any, key: str) -> uuid.UUID:
    return next(s.id for s in shopping.stores(db, actor) if s.key == key)


class TestAdding:
    def test_one_field_entry_splits_quantity_and_files_unknown_text_under_other(
        self, db: Session
    ) -> None:
        jonas, _ = factories.household(db)
        op = add("2 Milch")
        assert shopping.apply(db, jonas.actor, [op])[0].status == "applied"
        row = shopping.get_row(db, jonas.actor, op.id)
        assert (row.text, row.quantity, row.category, row.checked) == ("Milch", "2", "other", False)
        assert row.created_by == jonas.user.id

    def test_catalogue_items_bring_their_aisle_and_name(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        banana = db.scalars(select(Item).where(Item.name_de == "Banane roh")).one()
        op = Op(kind="add", id=uuid7(), fields={"item_id": banana.id})
        shopping.apply(db, jonas.actor, [op], language="en")
        row = shopping.get_row(db, jonas.actor, op.id)
        assert (row.text, row.category, row.item_id) == (banana.name_en, "produce", banana.id)

    def test_the_aisle_and_store_an_entry_was_moved_to_are_remembered(self, db: Session) -> None:
        jonas, partner = factories.household(db)
        first = add("Spülmittel")
        shopping.apply(db, jonas.actor, [first])
        dm = builtin(db, jonas.actor, "dm")
        moved = Op(kind="update", id=first.id, fields={"category": "household", "store_id": dm})
        shopping.apply(db, jonas.actor, [moved])
        shopping.apply(db, jonas.actor, [Op(kind="remove", id=first.id)])
        again = add("spülmittel")
        shopping.apply(db, partner.actor, [again])
        row = shopping.get_row(db, partner.actor, again.id)
        assert (row.category, row.store_id) == ("household", dm)

    def test_history_lists_the_most_used_entries_first(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        shopping.apply(db, jonas.actor, [add("Brot"), add("Milch"), add("Milch"), add("2 Milch")])
        history = shopping.history(db, jonas.actor)
        assert [(m.text, m.uses) for m in history] == [("Milch", 3), ("Brot", 1)]

    def test_empty_text_is_reported_per_operation(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        bad, good = add("  "), add("Brot")
        results = shopping.apply(db, jonas.actor, [bad, good])
        assert [(r.status, r.code) for r in results] == [
            ("invalid", "list_text_empty"),
            ("applied", None),
        ]
        assert texts(db, jonas.actor) == ["Brot"]


class TestOfflineSync:
    def test_sending_the_same_batch_twice_adds_nothing_twice(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        batch = [add("Brot"), add("Eier")]
        shopping.apply(db, jonas.actor, batch)
        again = shopping.apply(db, jonas.actor, batch)
        assert [r.status for r in again] == ["unchanged", "unchanged"]
        assert sorted(texts(db, jonas.actor)) == ["Brot", "Eier"]

    def test_an_older_offline_change_loses_field_by_field(self, db: Session, clock: Clock) -> None:
        jonas, partner = factories.household(db)
        op = add("Äpfel")
        shopping.apply(db, jonas.actor, [op])
        offline_at = clock.current + timedelta(minutes=1)
        clock.advance(timedelta(minutes=5))
        # Online, the partner changes the quantity now.
        shopping.apply(db, partner.actor, [Op(kind="update", id=op.id, fields={"quantity": "6"})])
        clock.advance(timedelta(minutes=30))
        # Jonas's phone comes back with a quantity and a check made before that.
        result = shopping.apply(
            db,
            jonas.actor,
            [Op(kind="update", id=op.id, at=offline_at, fields={"quantity": "1", "checked": True})],
        )
        assert result[0].status == "applied"
        row = shopping.get_row(db, jonas.actor, op.id)
        assert (row.quantity, row.checked, row.checked_by) == ("6", True, jonas.user.id)
        assert row.checked_at == offline_at  # ticked in the shop, not when it synced

    def test_a_removed_item_stays_removed(self, db: Session) -> None:
        jonas, partner = factories.household(db)
        op = add("Käse")
        shopping.apply(db, jonas.actor, [op])
        shopping.apply(db, partner.actor, [Op(kind="remove", id=op.id)])
        late = shopping.apply(
            db,
            jonas.actor,
            [Op(kind="update", id=op.id, fields={"checked": True}), op, Op("remove", op.id)],
        )
        assert [r.status for r in late] == ["removed", "removed", "removed"]
        assert texts(db, jonas.actor) == []

    def test_checking_off_is_recorded_as_check(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        op = add("Brot")
        shopping.apply(db, jonas.actor, [op])
        shopping.apply(db, jonas.actor, [Op(kind="update", id=op.id, fields={"checked": True})])
        actions = db.scalars(
            select(ChangeRecord.action)
            .where(ChangeRecord.entity_id == op.id)
            .order_by(ChangeRecord.created_at, ChangeRecord.id)
        ).all()
        assert actions == ["add", "check"]

    def test_too_many_operations_are_refused(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        with pytest.raises(Invalid, match="too_many_operations"):
            shopping.apply(db, jonas.actor, [add(str(i)) for i in range(201)])

    def test_order_is_aisle_by_aisle_with_checked_items_last(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        bread, milk, apples = add("Brot"), add("Milch"), add("Äpfel")
        shopping.apply(
            db,
            jonas.actor,
            [
                Op(kind="add", id=bread.id, fields={"text": "Brot", "category": "bakery"}),
                Op(kind="add", id=milk.id, fields={"text": "Milch", "category": "dairy_eggs"}),
                Op(kind="add", id=apples.id, fields={"text": "Äpfel", "category": "produce"}),
                Op(kind="update", id=bread.id, fields={"checked": True}),
            ],
        )
        assert texts(db, jonas.actor) == ["Äpfel", "Milch", "Brot"]


class TestHouseholds:
    def test_another_households_items_cannot_be_touched(self, db: Session) -> None:
        mine, _ = factories.household(db)
        theirs, _ = factories.household(db)
        op = add("Geheim")
        shopping.apply(db, theirs.actor, [op])
        results = shopping.apply(
            db,
            mine.actor,
            [
                Op(kind="update", id=op.id, fields={"checked": True}),
                Op(kind="remove", id=op.id),
                Op(kind="add", id=op.id, fields={"text": "Übernommen"}),
            ],
        )
        assert [r.status for r in results] == ["not_found", "not_found", "not_found"]
        row = db.get(ShoppingListItem, op.id)
        assert row is not None and row.deleted_at is None and row.checked is False
        assert texts(db, mine.actor) == []
        with pytest.raises(NotFound):
            shopping.get_row(db, mine.actor, op.id)

    def test_another_households_store_and_item_are_refused(self, db: Session) -> None:
        mine, _ = factories.household(db)
        theirs, _ = factories.household(db)
        store = shopping.create_store(db, theirs.actor, "Hofladen")
        results = shopping.apply(db, mine.actor, [add("Eier", store_id=store.id)])
        assert (results[0].status, results[0].code) == ("invalid", "store_not_found")
        assert all(s.id != store.id for s in shopping.stores(db, mine.actor))
        with pytest.raises(NotFound):
            shopping.delete_store(db, mine.actor, store.id)


class TestStores:
    def test_builtin_stores_come_first_then_custom_ones(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        shopping.create_store(db, jonas.actor, "Wochenmarkt")
        names = [s.key or s.name for s in shopping.stores(db, jonas.actor)]
        assert names == [
            "aldi",
            "lidl",
            "edeka",
            "rewe",
            "netto",
            "penny",
            "dm",
            "other",
            "Wochenmarkt",
        ]

    def test_custom_store_names_are_unique_and_builtin_ones_stay(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        market = shopping.create_store(db, jonas.actor, "Wochenmarkt")
        with pytest.raises(Conflict, match="store_name_taken"):
            shopping.create_store(db, jonas.actor, "wochenmarkt")
        with pytest.raises(Invalid, match="store_builtin"):
            shopping.delete_store(db, jonas.actor, builtin(db, jonas.actor, "aldi"))
        op = add("Eier", store_id=market.id)
        shopping.apply(db, jonas.actor, [op])
        shopping.delete_store(db, jonas.actor, market.id)
        db.expire_all()
        assert shopping.get_row(db, jonas.actor, op.id).store_id is None


class TestEvents:
    def test_every_change_record_notifies_the_household(
        self, db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        jonas, _ = factories.household(db)
        sent: list[tuple[uuid.UUID, str]] = []
        monkeypatch.setattr(
            events,
            "publish",
            lambda _db, household, entity, user=None: sent.append((household, entity)),
        )
        shopping.apply(db, jonas.actor, [add("Brot")])
        assert sent == [(jonas.user.household_id, "list_item")]

    def test_the_notification_is_valid_sql_inside_a_transaction(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        events.publish(db, jonas.user.household_id, "list_item", jonas.user.id)
