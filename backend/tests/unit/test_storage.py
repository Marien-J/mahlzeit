from pathlib import Path

import pytest

from mahlzeit.storage import LocalStorage


def test_put_get_delete(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path)
    store.put("receipts/2026/a.pdf", b"%PDF")
    assert store.get("receipts/2026/a.pdf") == b"%PDF"
    store.delete("receipts/2026/a.pdf")
    store.delete("receipts/2026/a.pdf")
    assert not (tmp_path / "receipts/2026/a.pdf").exists()


@pytest.mark.parametrize("key", ["../outside", "/etc/passwd", "a/../../b", ""])
def test_keys_cannot_escape_the_root(tmp_path: Path, key: str) -> None:
    with pytest.raises(ValueError):
        LocalStorage(tmp_path).put(key, b"x")
