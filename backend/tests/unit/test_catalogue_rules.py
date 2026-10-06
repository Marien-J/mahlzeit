import pytest

from mahlzeit.domain.catalogue import (
    Category,
    TrackingMode,
    check_barcode,
    check_label,
    check_names,
    check_serving,
)
from mahlzeit.domain.errors import Invalid
from mahlzeit.domain.nutrition import Nutrients


class TestLabel:
    def test_plausible_label_passes(self) -> None:
        check_label(
            Nutrients(
                kcal=372,
                protein=13.5,
                carbs=58.7,
                sugar=0.7,
                fat=7,
                sat_fat=1.3,
                fibre=10,
                salt=0.02,
            )
        )

    def test_empty_label_is_allowed(self) -> None:
        check_label(Nutrients())  # logging is never blocked by missing data

    @pytest.mark.parametrize(
        "n",
        [
            Nutrients(kcal=-1),
            Nutrients(kcal=950),
            Nutrients(protein=101),
            Nutrients(sugar=30, carbs=20),
            Nutrients(sat_fat=10, fat=5),
            Nutrients(protein=40, carbs=40, fat=40),
        ],
    )
    def test_implausible_labels(self, n: Nutrients) -> None:
        with pytest.raises(Invalid) as err:
            check_label(n)
        assert err.value.code == "label_implausible"


class TestNames:
    def test_needs_one_name(self) -> None:
        with pytest.raises(Invalid) as err:
            check_names({"de": " ", "en": None, "nl": ""})
        assert err.value.code == "item_name_required"

    def test_trims_and_drops_empty(self) -> None:
        assert check_names({"de": " Skyr ", "en": "", "nl": None}) == {"de": "Skyr"}


class TestBarcode:
    @pytest.mark.parametrize("code", ["4008400401621", "96385074", "0012345678905"])
    def test_valid(self, code: str) -> None:
        assert check_barcode(code) == code

    @pytest.mark.parametrize("code", ["", "abc", "123", "4008400401622"])
    def test_invalid(self, code: str) -> None:
        with pytest.raises(Invalid) as err:
            check_barcode(code)
        assert err.value.code == "barcode_invalid"


class TestServing:
    def test_valid(self) -> None:
        assert check_serving("egg", 55) == ("egg", 55)

    @pytest.mark.parametrize(
        ("label", "amount"), [("", 10), ("x" * 41, 10), ("egg", 0), ("egg", 5001)]
    )
    def test_invalid(self, label: str, amount: float) -> None:
        with pytest.raises(Invalid):
            check_serving(label, amount)


def test_enums() -> None:
    assert {c.value for c in Category} >= {"produce", "dairy_eggs", "meat_fish", "other"}
    assert {t.value for t in TrackingMode} == {"counted", "status"}
