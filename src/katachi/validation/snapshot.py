"""
Cached, read-only view of a filesystem used during validation.

Every directory is listed at most once with ``fs.ls(path, detail=True)``, which returns
entry types, sizes and (on local filesystems) modes and owners in a single call. This
turns validation into an in-memory problem and matters a lot for remote filesystems
(Azure Blob Storage, S3, ...) where every call is a network round trip. For remote
filesystems the directories that the schema can reach are also prefetched concurrently.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fsspec import AbstractFileSystem

from katachi.schema.schema_node import SchemaDirectory
from katachi.utils.logger import logger


class Entry:
    """
    A single file or directory as reported by the filesystem.

    ``size``, ``mode`` and ``uid`` may be loaded lazily (one ``stat`` call on first access),
    so checks that don't need them never pay for them.
    """

    __slots__ = ("_mode", "_size", "_source", "_uid", "name", "path", "type")

    def __init__(
        self,
        path: str,
        name: str,
        type: str,  # noqa: A002
        size: int | None = None,
        mode: int | None = None,
        uid: int | None = None,
        source: os.DirEntry | None = None,
    ):
        self.path = path
        self.name = name
        self.type = type
        self._size = size
        self._mode = mode
        self._uid = uid
        self._source = source

    def _load(self) -> None:
        source, self._source = self._source, None
        if source is not None:
            try:
                st = source.stat()
            except OSError:
                return
            self._size, self._mode, self._uid = st.st_size, st.st_mode, st.st_uid

    @property
    def size(self) -> int | None:
        self._load()
        return self._size

    @property
    def mode(self) -> int | None:
        self._load()
        return self._mode

    @property
    def uid(self) -> int | None:
        self._load()
        return self._uid

    @property
    def is_dir(self) -> bool:
        return self.type == "directory"

    @property
    def is_file(self) -> bool:
        return self.type == "file"

    def __repr__(self) -> str:
        return f"Entry({self.path!r}, type={self.type!r})"

    @classmethod
    def from_info(cls, info: dict[str, Any]) -> Entry:
        path = str(info["name"])
        if len(path) > 1:
            path = path.rstrip("/")
        name = path.rsplit("/", 1)[-1] or path
        size = info.get("size")
        return cls(
            path=path,
            name=name,
            type=str(info.get("type", "other")),
            size=int(size) if isinstance(size, int | float) else None,
            mode=info.get("mode"),
            uid=info.get("uid"),
        )


def _scandir(path: str) -> list[Entry]:
    """Fast local listing: entry types come from ``readdir`` without a ``stat`` per entry."""
    entries = []
    prefix = path.rstrip("/")
    with os.scandir(path) as it:
        for de in it:
            try:
                if de.is_dir():
                    kind = "directory"
                elif de.is_file():
                    kind = "file"
                else:
                    kind = "other"
            except OSError:
                kind = "other"
            entries.append(Entry(f"{prefix}/{de.name}", de.name, kind, source=de))
    return entries


def is_local(fs: AbstractFileSystem) -> bool:
    """Check whether a filesystem is the local filesystem."""
    protocol = fs.protocol if isinstance(fs.protocol, str) else fs.protocol[0]
    return protocol in ("file", "local")


class FsSnapshot:
    """Lazily populated cache of directory listings."""

    def __init__(self, fs: AbstractFileSystem):
        self.fs = fs
        self._listings: dict[str, list[Entry]] = {}
        self._errors: dict[str, OSError] = {}
        self._lock = threading.Lock()
        self._local = is_local(fs)

    @property
    def directories_listed(self) -> int:
        return len(self._listings)

    def info(self, path: str) -> Entry | None:
        """Return the entry for a path, or None if it does not exist."""
        try:
            return Entry.from_info(self.fs.info(path))
        except FileNotFoundError:
            return None

    def _fetch(self, path: str) -> list[Entry]:
        if self._local:
            entries = _scandir(path)
            entries.sort(key=lambda e: e.name)
            return entries
        raw = self.fs.ls(path, detail=True)
        entries = []
        for info in raw:
            entry = Entry.from_info(info)
            # Some filesystems include the directory itself in its listing
            if entry.path != path.rstrip("/"):
                entries.append(entry)
        entries.sort(key=lambda e: e.name)
        return entries

    def listdir(self, path: str) -> list[Entry]:
        """
        List a directory (cached).

        Raises:
            OSError: If the directory cannot be listed (e.g. permission denied)
        """
        with self._lock:
            if path in self._listings:
                return self._listings[path]
            if path in self._errors:
                raise self._errors[path]
        try:
            entries = self._fetch(path)
        except OSError as e:
            with self._lock:
                self._errors[path] = e
            raise
        with self._lock:
            self._listings[path] = entries
        return entries

    def prefetch(self, schema: SchemaDirectory, root: Entry, workers: int) -> None:
        """
        Concurrently list every directory the schema could descend into, level by level.

        Only directories whose name matches a schema directory that itself declares
        children are listed, so the prefetch never reads more than validation would.
        """
        if workers <= 1:
            return
        level: list[tuple[Entry, list[SchemaDirectory]]] = [(root, [schema])]
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="katachi-ls") as pool:
            while level:
                futures = [(entry, candidates, pool.submit(self._safe_list, entry.path)) for entry, candidates in level]
                next_level: list[tuple[Entry, list[SchemaDirectory]]] = []
                for _entry, candidates, future in futures:
                    for child in future.result():
                        if not child.is_dir:
                            continue
                        child_candidates = list(_descendable(candidates, child.name))
                        if child_candidates:
                            next_level.append((child, child_candidates))
                level = next_level
        logger.debug(f"Prefetched {self.directories_listed} directory listings with {workers} workers")

    def _safe_list(self, path: str) -> list[Entry]:
        try:
            return self.listdir(path)
        except OSError:
            return []


def _descendable(candidates: Iterable[SchemaDirectory], name: str) -> Iterable[SchemaDirectory]:
    for parent in candidates:
        if parent.is_ignored(name):
            continue
        for child in parent.structural_children:
            if isinstance(child, SchemaDirectory) and child.structural_children and child.name_matches(name):
                yield child
