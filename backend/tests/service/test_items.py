from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mahlzeit.domain.catalogue import Category
from mahlzeit.domain.errors import Conflict, Invalid, NotFound, RateLimited
from mahlzeit.domain.nutrition import Nutrients
from mahlzeit.models import ChangeRecord, Favourite, Item
from mahlzeit.services import items, seed
from mahlzeit.services.items import ItemInput
from tests import factories
from tests.fakes import FakeOff

SKYR = ItemInput(
    names={"de": "Skyr Natur", "en": None, "nl": None},
    brand="Arla",
    category=Category.DAIRY_EGGS,
    nutrients=Nutrients(
        kcal=63, protein=11, carbs=4, sugar=4, fat=0.2, sat_fat=0.1, fibre=0, salt=0.1
    ),
    servings=[("cup", 150)],
    barcodes=["4008400401621"],
)


def names(hits: list[items.Hit]) -> list[str]:
    return [h.item.name_de or "" for h in hits]


class TestSeed:
    def test_generic_foods_are_loaded_once(self, db: Session) -> None:
        count = db.scalar(select(func.count()).select_from(Item).where(Item.household_id.is_(None)))
        assert count == len(seed.generic_foods()) >= 240
        seed.load_generic_foods(db)
        again = db.scalar(select(func.count()).select_from(Item).where(Item.household_id.is_(None)))
        assert again == count

    def test_first_admin_gets_the_staples_as_favourites(self, db: Session) -> None:
        # The test database already has users from other tests' rolled-back transactions only,
        # so this household's admin is the first user.
        jonas, partner = factories.household(db)
        assert len(items.favourite_ids(db, jonas.actor)) == len(seed.favourite_seed_ids())
        assert items.favourite_ids(db, partner.actor) == set()


class TestSearch:
    def test_finds_generic_foods_in_three_languages(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        assert "Hähnchen Brustfilet, roh" in names(items.search(db, jonas.actor, "hähnchen brust"))
        assert "Hähnchen Brustfilet, roh" in names(items.search(db, jonas.actor, "chicken breast"))
        assert "Hähnchen Brustfilet, roh" in names(items.search(db, jonas.actor, "kipfilet"))

    def test_tolerates_typos_and_umlauts(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        assert "Hähnchen Brustfilet, roh" in names(
            items.search(db, jonas.actor, "hahnchen brustfilt")
        )
        assert any(
            "Haferflocken" in n or "Hafer Flocken" in n
            for n in names(items.search(db, jonas.actor, "haferflocen"))
        )

    def test_household_items_rank_first(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        items.create(db, jonas.actor, SKYR)
        hits = items.search(db, jonas.actor, "skyr")
        assert hits[0].item.name_de == "Skyr Natur"
        assert hits[0].item.household_id == jonas.user.household_id

    def test_own_lists_only_the_households_items(self, db: Session) -> None:
        mine, _ = factories.household(db)
        theirs, _ = factories.household(db)
        items.create(db, mine.actor, SKYR)
        items.create(db, theirs.actor, SKYR)
        own = items.search(db, mine.actor, "", own=True)
        assert [h.item.household_id for h in own] == [mine.user.household_id]
        assert items.search(db, mine.actor, "hähnchen", own=True) == []
        assert names(items.search(db, mine.actor, "skir", own=True)) == ["Skyr Natur"]

    def test_never_shows_another_households_items(self, db: Session) -> None:
        mine, _ = factories.household(db)
        theirs, _ = factories.household(db)
        items.create(db, theirs.actor, SKYR)
        assert all(
            h.item.household_id in (None, mine.user.household_id)
            for h in items.search(db, mine.actor, "skyr")
        )

    def test_empty_query_returns_favourites(self, db: Session) -> None:
        jonas, partner = factories.household(db)
        assert {
            h.item.id for h in items.search(db, jonas.actor, "", limit=100)
        } == items.favourite_ids(db, jonas.actor)
        assert items.search(db, partner.actor, "") == []


class TestCreateUpdate:
    def test_create_household_item_with_barcode_and_serving(self, db: Session) -> None:
        jonas, partner = factories.household(db)
        item = items.create(db, jonas.actor, SKYR)
        assert item.household_id == jonas.user.household_id
        assert [b.code for b in item.barcodes] == ["4008400401621"]
        assert [(s.label, s.amount) for s in item.servings] == [("cup", 150)]
        assert items.get(db, partner.actor, item.id).id == item.id
        change = db.scalars(select(ChangeRecord).where(ChangeRecord.entity_id == item.id)).one()
        assert change.action == "created" and change.after["brand"] == "Arla"

    def test_generic_items_are_read_only(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        generic = items.search(db, jonas.actor, "Broccoli")[0].item
        with pytest.raises(Conflict) as err:
            items.update(db, jonas.actor, generic.id, SKYR)
        assert err.value.code == "item_read_only"

    def test_update_changes_values_and_records_before(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        item = items.create(db, jonas.actor, SKYR)
        changed = ItemInput(**{**SKYR.__dict__, "brand": "Siggi's", "barcodes": []})
        updated = items.update(db, jonas.actor, item.id, changed)
        assert updated.brand == "Siggi's" and updated.barcodes == []
        change = db.scalars(
            select(ChangeRecord).where(
                ChangeRecord.entity_id == item.id, ChangeRecord.action == "updated"
            )
        ).one()
        assert change.before["brand"] == "Arla"

    def test_barcode_is_unique_per_household_only(self, db: Session) -> None:
        mine, _ = factories.household(db)
        theirs, _ = factories.household(db)
        items.create(db, mine.actor, SKYR)
        items.create(db, theirs.actor, SKYR)
        with pytest.raises(Conflict) as err:
            items.create(db, mine.actor, SKYR)
        assert err.value.code == "barcode_taken"

    def test_validation(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        for bad in (
            ItemInput(names={}),
            ItemInput(names={"de": "x"}, nutrients=Nutrients(kcal=3720)),
            ItemInput(names={"de": "x"}, barcodes=["123"]),
            ItemInput(names={"de": "x"}, servings=[("", 10)]),
        ):
            with pytest.raises(Invalid):
                items.create(db, jonas.actor, bad)

    def test_cross_household_get_and_update(self, db: Session) -> None:
        mine, _ = factories.household(db)
        theirs, _ = factories.household(db)
        item = items.create(db, theirs.actor, SKYR)
        with pytest.raises(NotFound):
            items.get(db, mine.actor, item.id)
        with pytest.raises(NotFound):
            items.update(db, mine.actor, item.id, SKYR)
        with pytest.raises(NotFound):
            items.set_favourite(db, mine.actor, item.id, True)


class TestFavourites:
    def test_toggle(self, db: Session) -> None:
        _, partner = factories.household(db)
        broccoli = items.search(db, partner.actor, "Broccoli")[0].item
        items.set_favourite(db, partner.actor, broccoli.id, True)
        items.set_favourite(db, partner.actor, broccoli.id, True)
        assert (
            db.scalar(
                select(func.count())
                .select_from(Favourite)
                .where(Favourite.user_id == partner.user.id)
            )
            == 1
        )
        items.set_favourite(db, partner.actor, broccoli.id, False)
        assert items.favourite_ids(db, partner.actor) == set()


class TestBarcode:
    def test_own_item_first(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        mine = items.create(db, jonas.actor, SKYR)
        off = FakeOff()
        result = items.lookup_barcode(db, jonas.actor, "4008400401621", off)
        assert result.status == "item" and result.item.id == mine.id
        assert off.product_calls == []

    def test_open_food_facts_draft_is_cached(self, db: Session) -> None:
        jonas, partner = factories.household(db)
        off = FakeOff()
        first = items.lookup_barcode(db, jonas.actor, "4008400401621", off)
        assert first.status == "draft" and first.draft.names["de"] == "Nutella"
        items.lookup_barcode(db, partner.actor, "4008400401621", off)
        assert off.product_calls == ["4008400401621"]

    def test_unknown_code(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        off = FakeOff(products={})
        assert items.lookup_barcode(db, jonas.actor, "96385074", off).status == "not_found"
        items.lookup_barcode(db, jonas.actor, "96385074", off)
        assert len(off.product_calls) == 1
        clock.advance(timedelta(days=2))
        items.lookup_barcode(db, jonas.actor, "96385074", off)
        assert len(off.product_calls) == 2

    def test_invalid_code_is_never_sent(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        off = FakeOff()
        with pytest.raises(Invalid):
            items.lookup_barcode(db, jonas.actor, "12345", off)
        assert off.product_calls == []

    def test_rate_limit_is_15_reads_per_minute(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        off = FakeOff(products={})
        codes = [str(1000000 + i) for i in range(16)]
        valid = []
        for base in codes:
            body = base.zfill(7)
            weighted = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
            valid.append(body + str((10 - weighted % 10) % 10))
        for code in valid[:15]:
            items.lookup_barcode(db, jonas.actor, code, off)
        with pytest.raises(RateLimited) as err:
            items.lookup_barcode(db, jonas.actor, valid[15], off)
        assert err.value.code == "external_rate_limited"
        clock.advance(timedelta(minutes=1))
        items.lookup_barcode(db, jonas.actor, valid[15], off)

    def test_outage_is_a_clear_error(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        with pytest.raises(Conflict) as err:
            items.lookup_barcode(db, jonas.actor, "4008400401621", FakeOff(down=True))
        assert err.value.code == "off_unavailable"

    def test_import_from_draft(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        draft = items.lookup_barcode(db, jonas.actor, "4008400401621", FakeOff()).draft
        assert draft is not None
        data = ItemInput(
            names=draft.names,
            brand=draft.brand,
            category=draft.category,
            nutrients=draft.nutrients,
            barcodes=[draft.barcode],
            servings=draft.servings,
        )
        item = items.create(db, jonas.actor, data, source="off", source_id=draft.barcode)
        assert item.source == "off"
        assert items.lookup_barcode(db, jonas.actor, "4008400401621", FakeOff()).item.id == item.id


class TestSearchOnline:
    def test_returns_drafts_and_respects_limit(self, db: Session, clock) -> None:
        jonas, _ = factories.household(db)
        off = FakeOff()
        drafts = items.search_online(db, jonas.actor, "nutella", "de", off)
        assert [d.names["de"] for d in drafts] == ["Nutella"]
        for _ in range(9):
            items.search_online(db, jonas.actor, "nutella", "de", off)
        with pytest.raises(RateLimited):
            items.search_online(db, jonas.actor, "nutella", "de", off)

    def test_short_queries_do_nothing(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        off = FakeOff()
        assert items.search_online(db, jonas.actor, " a ", "de", off) == []
        assert off.search_calls == []
