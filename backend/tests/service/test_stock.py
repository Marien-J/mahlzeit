from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mahlzeit.domain.catalogue import BaseUnit, Category, TrackingMode
from mahlzeit.domain.day import EntryState, Slot
from mahlzeit.domain.errors import Invalid, NotFound
from mahlzeit.domain.stock import Status
from mahlzeit.ids import uuid7
from mahlzeit.models import ChangeRecord, Item, Purchase, ShoppingListItem, StockMovement
from mahlzeit.services import day, items, profiles, shopping, snapshot, stock
from mahlzeit.services.day import ComponentInput, EntryInput, EntryPatch
from mahlzeit.services.items import ItemInput
from mahlzeit.services.shopping import Op
from mahlzeit.services.stock import LineInput, PurchaseInput
from tests import factories
from tests.conftest import Clock

pytestmark = pytest.mark.usefixtures("clock")

TODAY = date(2026, 10, 6)
RICE, CHICKEN, BROCCOLI, OLIVE_OIL = "C352000", "V416100", "G312100", "Q120000"


def food(db: Session, member: factories.Member, code: str) -> Item:
    return factories.generic(db, member.actor, code)


def custom(db: Session, member: factories.Member, name: str, **kw: Any) -> Item:
    return items.create(db, member.actor, ItemInput(names={"de": name}, **kw))


def buy(db: Session, member: factories.Member, *lines: LineInput, **kw: Any) -> Purchase:
    return stock.record_purchase(
        db, member.actor, PurchaseInput(id=uuid7(), lines=list(lines), **kw)
    )


def level(db: Session, member: factories.Member, item: Item) -> float | None:
    return stock.item_stock(db, member.actor, item.id).level


def eat(
    db: Session,
    member: factories.Member,
    *components: tuple[Item, float],
    on: date = TODAY,
    **kw: Any,
):
    return day.log_food(
        db,
        member.actor,
        EntryInput(
            day=on,
            slot=Slot.DINNER,
            components=[ComponentInput(item_id=i.id, amount=a) for i, a in components],
            **kw,
        ),
    )


def movements(db: Session, member: factories.Member, item: Item) -> list[tuple[str, str, float]]:
    rows = db.scalars(
        select(StockMovement)
        .where(
            StockMovement.household_id == member.actor.household_id,
            StockMovement.item_id == item.id,
        )
        .order_by(StockMovement.created_at, StockMovement.id)
    )
    return [(m.reason, m.source, round(m.amount, 3)) for m in rows]


class TestPurchases:
    def test_bought_turns_the_checked_list_into_one_purchase(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        rice, oil = food(db, jonas, RICE), food(db, jonas, OLIVE_OIL)
        ops = [
            Op("add", uuid7(), fields={"item_id": rice.id, "quantity": "1 kg", "checked": True}),
            Op("add", uuid7(), fields={"item_id": oil.id, "checked": True}),
            Op("add", uuid7(), fields={"text": "Spülmittel", "checked": True}),
            Op("add", uuid7(), fields={"text": "Brot"}),  # not ticked: stays
        ]
        shopping.apply(db, jonas.actor, ops)
        lidl = next(s.id for s in shopping.stores(db, jonas.actor) if s.key == "lidl")
        purchase = buy(
            db,
            jonas,
            *(LineInput(list_item_id=op.id) for op in ops[:3]),
            store_id=lidl,
        )
        assert [(ln.text, ln.quantity, ln.amount) for ln in purchase.lines] == [
            (rice.name_de, "1 kg", 1000),
            (oil.name_de, None, None),
            ("Spülmittel", None, None),
        ]
        assert purchase.store_id == lidl and purchase.day == TODAY
        assert level(db, jonas, rice) == 1000
        assert stock.item_stock(db, jonas.actor, oil.id).status == Status.OK
        assert movements(db, jonas, oil) == []  # status-only items keep no amount
        assert [r.text for r in shopping.open_items(db, jonas.actor)] == ["Brot"]

    def test_the_same_purchase_sent_twice_is_recorded_once(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        rice = food(db, jonas, RICE)
        data = PurchaseInput(id=uuid7(), lines=[LineInput(item_id=rice.id, amount=500)])
        first = stock.record_purchase(db, jonas.actor, data)
        again = stock.record_purchase(db, jonas.actor, data)
        assert again.id == first.id
        assert level(db, jonas, rice) == 500

    def test_another_households_purchase_id_is_not_found(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        other, _ = factories.household(db, "Kim", "Lou")
        rice = food(db, jonas, RICE)
        data = PurchaseInput(id=uuid7(), lines=[LineInput(item_id=rice.id, amount=500)])
        stock.record_purchase(db, jonas.actor, data)
        with pytest.raises(NotFound):
            stock.record_purchase(db, other.actor, data)
        with pytest.raises(NotFound):
            stock.get_purchase(db, other.actor, data.id)

    def test_by_hand_with_packages_prices_and_a_past_day(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        skyr = custom(db, jonas, "Skyr", package_size=450, category=Category.DAIRY_EGGS)
        purchase = buy(
            db,
            jonas,
            LineInput(item_id=skyr.id, quantity="2", price_cents=338),
            LineInput(text="Kerzen", price_cents=199),
            day=TODAY - timedelta(days=2),
        )
        assert purchase.day == TODAY - timedelta(days=2)
        assert [ln.amount for ln in purchase.lines] == [900, None]
        assert level(db, jonas, skyr) == 900

    def test_a_line_without_a_readable_quantity_adds_nothing(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        rice = food(db, jonas, RICE)
        buy(db, jonas, LineInput(item_id=rice.id, quantity="ein paar"))
        assert level(db, jonas, rice) == 0
        assert movements(db, jonas, rice) == []

    @pytest.mark.parametrize(
        ("data", "code"),
        [
            ({"lines": []}, "purchase_empty"),
            ({"day": TODAY + timedelta(days=1)}, "purchase_day_invalid"),
            ({"lines": [LineInput(text="x", price_cents=-1)]}, "price_invalid"),
            ({"lines": [LineInput(text="x", amount=-5)]}, "stock_amount_invalid"),
            ({"lines": [LineInput(text=" ")]}, "list_text_empty"),
        ],
    )
    def test_invalid_purchases(self, db: Session, data: dict[str, Any], code: str) -> None:
        jonas, _ = factories.household(db)
        payload = {"lines": [LineInput(text="Brot")], **data}
        with pytest.raises(Invalid) as err:
            stock.record_purchase(db, jonas.actor, PurchaseInput(id=uuid7(), **payload))
        assert err.value.code == code

    def test_a_purchase_is_a_change_record(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        purchase = buy(db, jonas, LineInput(text="Brot", price_cents=250))
        change = db.scalars(select(ChangeRecord).where(ChangeRecord.entity_id == purchase.id)).one()
        assert (change.entity, change.action, change.after["spend_cents"]) == (
            "purchase",
            "create",
            250,
        )


class TestMeals:
    def test_eating_takes_the_dish_out_of_stock(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        rice = food(db, jonas, RICE)
        buy(db, jonas, LineInput(item_id=rice.id, amount=1000))
        eat(db, jonas, (rice, 150))
        assert level(db, jonas, rice) == 850

    def test_a_joint_meal_takes_the_whole_dish_once(self, db: Session) -> None:
        jonas, sam = factories.household(db, "Jonas", "Sam")
        chicken = food(db, jonas, CHICKEN)
        buy(db, jonas, LineInput(item_id=chicken.id, amount=600))
        entry = day.plan_meal(
            db,
            jonas.actor,
            EntryInput(
                day=TODAY,
                slot=Slot.DINNER,
                joint=True,
                components=[ComponentInput(item_id=chicken.id, amount=400)],
            ),
        )
        assert level(db, jonas, chicken) == 600  # a plan takes nothing
        day.set_state(db, jonas.actor, entry.id, EntryState.LOGGED)
        assert level(db, jonas, chicken) == 200
        day.set_state(db, sam.actor, entry.id, EntryState.LOGGED)  # Sam taps Eaten as well
        assert level(db, jonas, chicken) == 200
        day.delete_entry(db, jonas.actor, entry.id)  # Sam still ate it
        assert level(db, jonas, chicken) == 200
        day.delete_entry(db, sam.actor, entry.id)
        assert level(db, jonas, chicken) == 600

    def test_eating_more_than_there_is_lands_on_zero_and_undoing_restores_it(
        self, db: Session
    ) -> None:
        jonas, _ = factories.household(db)
        rice = food(db, jonas, RICE)
        buy(db, jonas, LineInput(item_id=rice.id, amount=100))
        entry = eat(db, jonas, (rice, 300))
        assert level(db, jonas, rice) == 0
        assert movements(db, jonas, rice)[1:] == [
            ("consumption", "entry", -300),
            ("correction", "shortfall", 200),
        ]
        day.delete_entry(db, jonas.actor, entry.id)
        assert level(db, jonas, rice) == 100

    def test_never_blocks_logging_without_any_stock(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        rice = food(db, jonas, RICE)
        eat(db, jonas, (rice, 300))
        assert level(db, jonas, rice) == 0

    def test_not_eaten_after_all_gives_it_back(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        rice = food(db, jonas, RICE)
        buy(db, jonas, LineInput(item_id=rice.id, amount=500))
        entry = eat(db, jonas, (rice, 200))
        day.set_state(db, jonas.actor, entry.id, EntryState.PLANNED)
        assert level(db, jonas, rice) == 500

    def test_changing_the_amount_or_the_food_follows(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        rice, broccoli = food(db, jonas, RICE), food(db, jonas, BROCCOLI)
        buy(
            db,
            jonas,
            LineInput(item_id=rice.id, amount=500),
            LineInput(item_id=broccoli.id, amount=500),
        )
        entry = eat(db, jonas, (rice, 200))
        day.update_entry(
            db,
            jonas.actor,
            entry.id,
            EntryPatch(components=[ComponentInput(item_id=rice.id, amount=120)]),
        )
        assert level(db, jonas, rice) == 380
        day.update_entry(
            db,
            jonas.actor,
            entry.id,
            EntryPatch(components=[ComponentInput(item_id=broccoli.id, amount=300)]),
        )
        assert (level(db, jonas, rice), level(db, jonas, broccoli)) == (500, 200)

    def test_moving_a_meal_to_another_day_moves_its_movements(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        rice = food(db, jonas, RICE)
        buy(db, jonas, LineInput(item_id=rice.id, amount=500), day=TODAY - timedelta(days=3))
        entry = eat(db, jonas, (rice, 200))
        day.update_entry(db, jonas.actor, entry.id, EntryPatch(day=TODAY - timedelta(days=1)))
        days = db.execute(
            select(StockMovement.day, func.sum(StockMovement.amount))
            .where(StockMovement.item_id == rice.id, StockMovement.source == "entry")
            .group_by(StockMovement.day)
        ).all()
        assert {d: round(a) for d, a in days} == {TODAY: 0, TODAY - timedelta(days=1): -200}
        assert level(db, jonas, rice) == 300

    def test_eaten_out_quick_adds_and_status_items_leave_stock_alone(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        rice, oil = food(db, jonas, RICE), food(db, jonas, OLIVE_OIL)
        buy(db, jonas, LineInput(item_id=rice.id, amount=500))
        entry = eat(db, jonas, (rice, 200), eaten_out=True)
        day.log_food(
            db,
            jonas.actor,
            EntryInput(
                day=TODAY, slot=Slot.SNACK, components=[ComponentInput(quick_name="Bar", kcal=200)]
            ),
        )
        eat(db, jonas, (oil, 10))
        assert level(db, jonas, rice) == 500
        assert movements(db, jonas, oil) == []
        day.update_entry(db, jonas.actor, entry.id, EntryPatch(eaten_out=False))
        assert level(db, jonas, rice) == 300  # it was eaten at home after all

    def test_copying_a_day_takes_stock_again(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        rice = food(db, jonas, RICE)
        buy(db, jonas, LineInput(item_id=rice.id, amount=500), day=TODAY - timedelta(days=1))
        eat(db, jonas, (rice, 100), on=TODAY - timedelta(days=1))
        day.copy_day(db, jonas.actor, source_day=TODAY - timedelta(days=1), day=TODAY)
        assert level(db, jonas, rice) == 300

    def test_households_have_their_own_stock(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        kim, _ = factories.household(db, "Kim", "Lou")
        rice = food(db, jonas, RICE)
        buy(db, jonas, LineInput(item_id=rice.id, amount=500))
        eat(db, kim, (rice, 100))
        assert (level(db, jonas, rice), level(db, kim, rice)) == (500, 0)


class TestByHand:
    def test_counting_sets_the_level(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        rice = food(db, jonas, RICE)
        buy(db, jonas, LineInput(item_id=rice.id, amount=1000))
        row = stock.adjust(db, jonas.actor, rice.id, count=400)
        assert row.level == 400
        assert movements(db, jonas, rice)[-1] == ("correction", "manual", -600)

    def test_counting_after_a_level_below_zero_starts_from_zero(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        rice = food(db, jonas, RICE)
        db.add(
            StockMovement(
                household_id=jonas.actor.household_id,
                item_id=rice.id,
                amount=-50,
                reason="correction",
                source="manual",
                day=TODAY,
            )
        )
        db.flush()
        assert stock.adjust(db, jonas.actor, rice.id, count=300).level == 300

    def test_waste_and_found_more(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        rice = food(db, jonas, RICE)
        buy(db, jonas, LineInput(item_id=rice.id, amount=100))
        assert stock.adjust(db, jonas.actor, rice.id, waste=250).level == 0  # at most what is there
        assert stock.adjust(db, jonas.actor, rice.id, add=50).level == 50
        assert movements(db, jonas, rice)[1:] == [
            ("waste", "manual", -100),
            ("correction", "manual", 50),
        ]

    def test_status_items_are_flipped(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        oil = food(db, jonas, OLIVE_OIL)
        row = stock.adjust(db, jonas.actor, oil.id, status=Status.LOW)
        assert (row.mode, row.status, row.level) == (TrackingMode.STATUS, Status.LOW, None)

    @pytest.mark.parametrize(
        "change", [{}, {"count": 1, "waste": 1}, {"add": 0}, {"count": -1}, {"waste": 0}]
    )
    def test_one_valid_change_at_a_time(self, db: Session, change: dict[str, Any]) -> None:
        jonas, _ = factories.household(db)
        with pytest.raises(Invalid):
            stock.adjust(db, jonas.actor, food(db, jonas, RICE).id, **change)

    def test_another_households_item_is_not_found(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        kim, _ = factories.household(db, "Kim", "Lou")
        skyr = custom(db, jonas, "Skyr")
        for call in (
            lambda: stock.adjust(db, kim.actor, skyr.id, count=1),
            lambda: stock.set_mode(db, kim.actor, skyr.id, TrackingMode.STATUS),
            lambda: stock.item_stock(db, kim.actor, skyr.id),
            lambda: stock.movements(db, kim.actor, skyr.id),
            lambda: stock.check_category(db, kim.actor, "other", counts={skyr.id: 1}),
            lambda: buy(db, kim, LineInput(item_id=skyr.id, amount=1)),
        ):
            with pytest.raises(NotFound):
                call()

    def test_the_household_chooses_how_an_item_is_tracked(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        oil, rice = food(db, jonas, OLIVE_OIL), food(db, jonas, RICE)
        assert stock.set_mode(db, jonas.actor, oil.id, TrackingMode.COUNTED).level == 0
        buy(db, jonas, LineInput(item_id=oil.id, amount=750))
        assert level(db, jonas, oil) == 750
        row = stock.set_mode(db, jonas.actor, rice.id, TrackingMode.STATUS)
        assert (row.mode, row.status) == (TrackingMode.STATUS, Status.OK)
        assert stock.set_mode(db, jonas.actor, oil.id, None).mode == TrackingMode.STATUS

    def test_a_pantry_check_fixes_an_aisle_in_one_go(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        foods = [custom(db, jonas, f"Dose {n}", category=Category.CANNED) for n in range(30)]
        buy(db, jonas, *(LineInput(item_id=f.id, amount=400) for f in foods))
        counts = {f.id: 400.0 if n % 3 else 0.0 for n, f in enumerate(foods)}
        check = stock.check_category(db, jonas.actor, "canned", counts=counts)
        assert check.checked_by == jonas.user.id
        view = stock.get_stock(db, jonas.actor, category="canned")
        assert sum(1 for r in view.rows if r.level == 0) == 10
        assert view.checks["canned"].checked_at == check.checked_at
        pantry = db.scalar(
            select(func.count()).select_from(StockMovement).where(StockMovement.source == "pantry")
        )
        assert pantry == 10  # only what changed

    def test_an_unknown_aisle(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        with pytest.raises(Invalid):
            stock.check_category(db, jonas.actor, "attic")


class TestStockPage:
    def test_aisle_by_aisle_and_gone_items_drop_off(self, db: Session, clock: Clock) -> None:
        jonas, _ = factories.household(db)
        rice, broccoli, oil = (food(db, jonas, c) for c in (RICE, BROCCOLI, OLIVE_OIL))
        buy(
            db,
            jonas,
            LineInput(item_id=rice.id, amount=500),
            LineInput(item_id=broccoli.id, amount=300),
            LineInput(item_id=oil.id),
        )
        eat(db, jonas, (broccoli, 300))
        names = [(r.item.category, r.level) for r in stock.get_stock(db, jonas.actor).rows]
        assert names == [("produce", 0), ("dry_goods", 500), ("oils_fats", None)]
        clock.advance(timedelta(days=stock.RECENT_DAYS + 1))
        rows = stock.get_stock(db, jonas.actor).rows
        assert [r.item.id for r in rows] == [rice.id, oil.id]

    def test_the_stepper_moves_a_package_or_a_serving(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        skyr = custom(db, jonas, "Skyr", package_size=450)
        egg = custom(db, jonas, "Ei", servings=[("egg", 60)])
        assert stock.item_stock(db, jonas.actor, skyr.id).step == 450
        assert stock.item_stock(db, jonas.actor, egg.id).step == 60

    def test_the_snapshot_says_what_is_in_stock(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        rice, oil = food(db, jonas, RICE), food(db, jonas, OLIVE_OIL)
        buy(db, jonas, LineInput(item_id=rice.id, amount=500))
        stock.adjust(db, jonas.actor, oil.id, status=Status.OUT)
        snap = snapshot.household_snapshot(db, jonas.actor, language="en")
        assert [(r.item.id, r.level) for r in snap.stock.in_stock] == [(rice.id, 500)]
        assert snap.stock.out == [oil.name_en]
        assert snap.not_yet_available == ()


class TestSuggestions:
    def _plan(self, db: Session, member: factories.Member, on: date, *components) -> Any:
        return day.plan_meal(
            db,
            member.actor,
            EntryInput(
                day=on,
                slot=Slot.DINNER,
                components=[ComponentInput(item_id=i.id, amount=a) for i, a in components],
            ),
        )

    def test_what_planned_meals_need_beyond_stock(self, db: Session) -> None:
        jonas, sam = factories.household(db, "Jonas", "Sam")
        chicken, rice = food(db, jonas, CHICKEN), food(db, jonas, RICE)
        buy(db, jonas, LineInput(item_id=chicken.id, amount=100))
        buy(db, jonas, LineInput(item_id=rice.id, amount=1000))
        self._plan(db, jonas, TODAY + timedelta(days=1), (chicken, 200), (rice, 150))
        self._plan(db, sam, TODAY + timedelta(days=2), (chicken, 200))
        self._plan(db, sam, TODAY + timedelta(days=3), (chicken, 500))  # beyond 3 days
        found = stock.suggestions(db, jonas.actor, language="en")
        assert [(s.item.id, s.reason, s.amount, s.quantity) for s in found] == [
            (chicken.id, "planned", 300, "300 g")
        ]
        profiles.update_profile(db, jonas.actor, list_plan_days=4)
        assert stock.suggestions(db, jonas.actor)[0].amount == 800

    def test_items_on_the_list_and_eaten_meals_are_left_out(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        chicken, rice = food(db, jonas, CHICKEN), food(db, jonas, RICE)
        self._plan(db, jonas, TODAY, (chicken, 200))
        eaten = self._plan(db, jonas, TODAY, (rice, 200))
        day.set_state(db, jonas.actor, eaten.id, EntryState.LOGGED)
        shopping.apply(db, jonas.actor, [Op("add", uuid7(), fields={"item_id": chicken.id})])
        assert stock.suggestions(db, jonas.actor) == []

    def test_staples_low_or_out(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        oil = food(db, jonas, OLIVE_OIL)
        stock.adjust(db, jonas.actor, oil.id, status=Status.LOW)
        assert [(s.item.id, s.reason) for s in stock.suggestions(db, jonas.actor)] == [
            (oil.id, "low")
        ]
        buy(db, jonas, LineInput(item_id=oil.id))
        assert stock.suggestions(db, jonas.actor) == []

    def test_usual_purchases_that_are_not_in_stock(self, db: Session, clock: Clock) -> None:
        jonas, _ = factories.household(db)
        milk = custom(db, jonas, "Milch", base_unit=BaseUnit.ML, package_size=1000)
        for weeks in (3, 2, 1):
            buy(
                db,
                jonas,
                LineInput(item_id=milk.id, quantity="2"),
                day=TODAY - timedelta(weeks=weeks),
            )
        assert level(db, jonas, milk) == 6000
        assert stock.suggestions(db, jonas.actor) == []
        stock.adjust(db, jonas.actor, milk.id, count=0)
        assert [(s.reason, s.quantity) for s in stock.suggestions(db, jonas.actor)] == [
            ("usual", "2")
        ]
        clock.advance(timedelta(days=80))  # the oldest purchases leave the window
        assert stock.suggestions(db, jonas.actor) == []

    def test_plan_days_are_bounded(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        for days in (0, 15):
            with pytest.raises(Invalid):
                profiles.update_profile(db, jonas.actor, list_plan_days=days)


class TestReport:
    def test_one_shop_and_three_days_of_logging(self, db: Session) -> None:
        jonas, sam = factories.household(db, "Jonas", "Sam")
        rice, chicken = food(db, jonas, RICE), food(db, jonas, CHICKEN)
        start = TODAY - timedelta(days=3)
        buy(
            db,
            jonas,
            LineInput(item_id=rice.id, amount=1000, price_cents=199),
            LineInput(item_id=chicken.id, amount=600, price_cents=899),
            LineInput(text="Kerzen", price_cents=250),
            day=start,
        )
        for n in range(3):
            on = start + timedelta(days=n + 1)
            eat(db, jonas, (rice, 100), on=on)
            eat(db, sam, (chicken, 250), on=on)  # the third time there is only 100 g left
        stock.adjust(db, jonas.actor, rice.id, waste=50)
        stock.adjust(db, jonas.actor, rice.id, count=600)
        result = stock.report(db, jonas.actor, start=start, end=TODAY, language="en")
        rows = {r.item.id: r for r in result.rows}
        assert [r.item.id for r in result.rows] == [rice.id, chicken.id]
        assert (
            rows[rice.id].purchased,
            rows[rice.id].logged,
            rows[rice.id].wasted,
            rows[rice.id].corrected,
            rows[rice.id].level,
        ) == (1000, 300, 50, -50, 600)
        assert (rows[chicken.id].logged, rows[chicken.id].shortfall, rows[chicken.id].level) == (
            750,
            150,
            0,
        )
        assert rows[rice.id].spend_cents == 199
        assert result.spend_cents == 199 + 899 + 250

    def test_the_period_is_bounded(self, db: Session) -> None:
        jonas, _ = factories.household(db)
        for start, end in (
            (TODAY, TODAY - timedelta(days=1)),
            (TODAY - timedelta(days=400), TODAY),
        ):
            with pytest.raises(Invalid):
                stock.report(db, jonas.actor, start=start, end=end)


def test_bought_list_items_leave_the_list_for_the_partner_too(db: Session) -> None:
    jonas, sam = factories.household(db, "Jonas", "Sam")
    op = Op("add", uuid7(), fields={"text": "Brot", "checked": True})
    shopping.apply(db, sam.actor, [op])
    buy(db, jonas, LineInput(list_item_id=op.id))
    row = db.get(ShoppingListItem, op.id)
    assert row is not None and row.deleted_at is not None
    assert shopping.open_items(db, sam.actor) == []
    # Sam's phone, offline meanwhile, ticks it again: removing is final.
    later = Op("update", op.id, fields={"checked": False})
    assert shopping.apply(db, sam.actor, [later])[0].status == "removed"


def test_a_list_item_of_another_household_is_ignored(db: Session) -> None:
    jonas, _ = factories.household(db)
    kim, _ = factories.household(db, "Kim", "Lou")
    op = Op("add", uuid7(), fields={"text": "Brot", "checked": True})
    shopping.apply(db, kim.actor, [op])
    purchase = buy(db, jonas, LineInput(text="Brot", list_item_id=op.id))
    assert purchase.lines[0].list_item_id is None
    assert [r.id for r in shopping.open_items(db, kim.actor)] == [op.id]
