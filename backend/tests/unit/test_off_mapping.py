import json
from pathlib import Path

from mahlzeit.domain.catalogue import Category
from mahlzeit.domain.off import map_product

FIXTURE = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "off_product_complete.json").read_text()
)


def test_complete_product_maps_every_field() -> None:
    draft = map_product(FIXTURE)
    assert draft is not None
    assert draft.barcode == "4008400401621"
    assert draft.names == {"de": "Nutella", "en": "Nutella", "nl": "Nutella"}
    assert draft.brand == "Nutella"
    assert draft.base_unit == "g"
    assert draft.package_size == 450
    assert draft.servings == [("serving", 15.0)]
    n = draft.nutrients
    assert n.kcal is not None and n.protein is not None and n.salt is not None
    assert n.fibre is None  # only estimated in OFF, so left for the person to fill in
    assert draft.missing == ["fibre"]
    assert not draft.complete


def test_not_found_returns_none() -> None:
    assert map_product({"status": "failure", "result": {"id": "product_not_found"}}) is None


def test_incomplete_product_lists_missing_fields() -> None:
    raw = {
        "status": "success",
        "code": "123",
        "product": {"product_name": "Mystery", "nutriments": {"energy-kcal_100g": 50}},
    }
    draft = map_product(raw)
    assert draft is not None
    assert draft.names == {"de": "Mystery"}
    assert draft.nutrients.kcal == 50
    assert set(draft.missing) >= {"protein", "carbs", "fat"}
    assert not draft.complete


def test_kcal_from_kj_when_kcal_missing() -> None:
    raw = {
        "status": "success",
        "code": "1",
        "product": {"product_name": "x", "nutriments": {"energy-kj_100g": 418.4}},
    }
    assert map_product(raw).nutrients.kcal == 100  # type: ignore[union-attr]


def test_liquids_use_ml() -> None:
    raw = {
        "status": "success",
        "code": "1",
        "product": {
            "product_name": "Saft",
            "product_quantity": 1000,
            "product_quantity_unit": "ml",
            "nutrition_data_per": "100ml",
            "nutriments": {},
        },
    }
    draft = map_product(raw)
    assert draft is not None
    assert draft.base_unit == "ml"
    assert draft.package_size == 1000


def test_category_guess_from_tags() -> None:
    assert map_product(FIXTURE).category is Category.SPICES_CONDIMENTS  # type: ignore[union-attr]
