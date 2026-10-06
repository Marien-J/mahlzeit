import uuid

from mahlzeit.ids import uuid7


def test_uuid7_has_version_and_variant() -> None:
    value = uuid7()
    assert value.version == 7
    assert value.variant == uuid.RFC_4122


def test_uuid7_is_time_ordered_and_unique() -> None:
    values = [uuid7() for _ in range(2000)]
    assert len(set(values)) == len(values)
    stamps = [v.int >> 80 for v in values]
    assert stamps == sorted(stamps)
