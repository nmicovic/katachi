"""
Benchmark Katachi on a synthetic dataset.

Generates ``<dirs>`` date directories, each with ``<files>`` image/label pairs, then times
schema loading + validation. Usage::

    uv run python benchmarks/bench.py --dirs 200 --files 250      # 100k files
    uv run python benchmarks/bench.py --profile                   # cProfile top functions
    uv run python benchmarks/bench.py --latency-ms 20             # simulate a remote filesystem
"""

from __future__ import annotations

import argparse
import cProfile
import os
import pstats
import tempfile
import time
from pathlib import Path

SCHEMA = """
semantical_name: dataset
type: directory
children:
  - semantical_name: day
    type: directory
    pattern_name: "\\\\d{4}-\\\\d{2}-\\\\d{2}"
    children:
      - semantical_name: image
        type: file
        pattern_name: "img_\\\\d+"
        extension: .jpg
      - semantical_name: label
        type: file
        pattern_name: "img_\\\\d+"
        extension: .json
      - semantical_name: pairs
        type: predicate
        predicate_type: pair_comparison
        elements: [image, label]
  - semantical_name: readme
    type: file
    pattern_name: README
    extension: .md
"""


def build_tree(root: Path, dirs: int, files: int) -> int:
    (root / "README.md").write_text("hi")
    count = 1
    for d in range(dirs):
        day = (
            root / f"2025-{1 + d // 28 % 12:02d}-{1 + d % 28:02d}"
            if d < 336
            else root / f"{2026 + d // 336}-01-{1 + d % 28:02d}"
        )
        day.mkdir(exist_ok=True)
        for i in range(files):
            for ext in (".jpg", ".json"):
                fd = os.open(day / f"img_{d * files + i}{ext}", os.O_CREAT | os.O_WRONLY)
                os.close(fd)
                count += 1
    return count


def remote_like_fs(latency: float):
    """A local filesystem that behaves like object storage: every metadata call costs a round trip."""
    from fsspec.implementations.local import LocalFileSystem

    import threading

    local = threading.local()

    class SlowFS(LocalFileSystem):
        protocol = ("slow",)
        calls = 0

        def _delay(self):
            SlowFS.calls += 1
            time.sleep(latency)

        def ls(self, path, detail=False, **kwargs):
            # Object stores return entry details with the listing: one round trip per listing
            self._delay()
            local.in_ls = True
            try:
                return super().ls(path, detail=detail, **kwargs)
            finally:
                local.in_ls = False

        def info(self, path, **kwargs):
            if not getattr(local, "in_ls", False):
                self._delay()
            return super().info(path, **kwargs)

        def isdir(self, path):
            self._delay()
            return super().isdir(path)

        def isfile(self, path):
            self._delay()
            return super().isfile(path)

    return SlowFS(skip_instance_cache=True)


def run(root: Path, schema_file: Path, latency: float = 0.0) -> tuple[float, bool]:
    from katachi.schema.importer import load_yaml
    from katachi.utils.fs_utils import get_filesystem
    from katachi.validation.validators import SchemaValidator

    start = time.perf_counter()
    fs, path = get_filesystem(str(root))
    if latency:
        fs = remote_like_fs(latency)
    schema_fs, schema_path = get_filesystem(str(schema_file))
    schema = load_yaml(schema_path, path, schema_fs, fs)
    report = SchemaValidator.validate_schema(schema, path, fs)
    return time.perf_counter() - start, report.is_valid()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dirs", type=int, default=100)
    parser.add_argument("--files", type=int, default=100)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--root", type=Path, help="Reuse/create the synthetic tree here")
    parser.add_argument("--latency-ms", type=float, default=0.0, help="Simulated per-call latency (remote storage)")
    args = parser.parse_args()

    tmp = None
    if args.root:
        root = args.root
    else:
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name) / "dataset"
    schema_file = root.parent / "bench_schema.yaml"
    if not root.exists():
        root.mkdir(parents=True)
        t = time.perf_counter()
        n = build_tree(root, args.dirs, args.files)
        print(f"generated {n} entries in {time.perf_counter() - t:.1f}s")
    schema_file.write_text(SCHEMA)

    if args.profile:
        profiler = cProfile.Profile()
        profiler.enable()
        run(root, schema_file)
        profiler.disable()
        pstats.Stats(profiler).sort_stats("tottime").print_stats(25)
        return

    times = []
    for _ in range(args.repeat):
        elapsed, valid = run(root, schema_file, args.latency_ms / 1000)
        times.append(elapsed)
    print(f"valid={valid} best={min(times):.3f}s median={sorted(times)[len(times) // 2]:.3f}s")


if __name__ == "__main__":
    main()
