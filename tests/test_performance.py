"""
Performance guards (generous bounds, meant to catch regressions like per-entry stat/isdir calls).

For real numbers run ``uv run python benchmarks/bench.py`` (see benchmarks/README.md).
"""

from __future__ import annotations

import threading
import time

import fsspec
from fsspec.implementations.memory import MemoryFileSystem

from katachi.schema.importer import parse_schema
from katachi.validation.validators import SchemaValidator
from tests.conftest import make_tree, run_validation

SCHEMA = {
    "type": "directory",
    "children": [
        {
            "semantical_name": "day",
            "type": "directory",
            "pattern_name": r"day\d+",
            "children": [
                {"semantical_name": "image", "type": "file", "pattern_name": r"img_\d+", "extension": ".jpg"},
                {"semantical_name": "label", "type": "file", "pattern_name": r"img_\d+", "extension": ".json"},
                {
                    "semantical_name": "pairs",
                    "type": "predicate",
                    "predicate_type": "pair_comparison",
                    "elements": ["image", "label"],
                },
            ],
        }
    ],
}


def test_ten_thousand_local_files_are_fast(tmp_path):
    root = make_tree(
        tmp_path / "ds", [f"day{d}/img_{i}{ext}" for d in range(20) for i in range(250) for ext in (".jpg", ".json")]
    )
    start = time.perf_counter()
    report = run_validation(SCHEMA, root)
    elapsed = time.perf_counter() - start
    assert report.is_valid()
    assert report.stats.entries_checked == 10_021
    assert elapsed < 3.0, f"validating 10k files took {elapsed:.2f}s"


class LatencyFS(MemoryFileSystem):
    """Memory filesystem where every call costs a (simulated) network round trip."""

    protocol = ("latency",)

    def __init__(self, latency: float):
        super().__init__(skip_instance_cache=True)
        self.latency = latency
        self.calls = 0
        self.lock = threading.Lock()

    def _round_trip(self):
        with self.lock:
            self.calls += 1
        time.sleep(self.latency)

    def ls(self, path, detail=True, **kwargs):
        self._round_trip()
        return super().ls(path, detail=detail, **kwargs)

    def info(self, path, **kwargs):
        self._round_trip()
        return super().info(path, **kwargs)


def test_remote_filesystems_use_one_call_per_directory_and_prefetch_concurrently():
    fs = LatencyFS(latency=0.02)
    MemoryFileSystem.store.clear()
    fs.pipe({f"/remote/day{d}/img_{i}{ext}": b"" for d in range(40) for i in range(10) for ext in (".jpg", ".json")})
    schema = parse_schema(SCHEMA, "/remote")

    start = time.perf_counter()
    report = SchemaValidator.validate_schema(schema, "/remote", fs)
    elapsed = time.perf_counter() - start

    assert report.is_valid()
    # 1 info for the root + 1 listing per directory; nothing per file
    assert fs.calls == 1 + 1 + 40
    # Sequentially that's 42 x 20ms = 0.84s; with 16 concurrent listings it is ~4 round trips
    assert elapsed < 0.6, f"remote validation took {elapsed:.2f}s"


def test_workers_can_be_disabled():
    fs = LatencyFS(latency=0.0)
    MemoryFileSystem.store.clear()
    fs.pipe({"/r/day1/img_1.jpg": b"", "/r/day1/img_1.json": b""})
    report = SchemaValidator.validate_schema(parse_schema(SCHEMA, "/r"), "/r", fs, workers=1)
    assert report.is_valid()
    assert fsspec.filesystem("memory") is not fs
