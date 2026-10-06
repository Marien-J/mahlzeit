"""File storage behind a small interface. Only a local-disk implementation exists."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Protocol

from mahlzeit.config import get_settings


class Storage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or get_settings().files_dir).resolve()

    def _path(self, key: str) -> Path:
        rel = PurePosixPath(key)
        if rel.is_absolute() or ".." in rel.parts or not rel.parts:
            raise ValueError("invalid storage key")
        return self.root.joinpath(*rel.parts)

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)
