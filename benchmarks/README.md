# Benchmarks

`bench.py` generates a synthetic dataset (date directories containing image/label pairs) and
times schema loading + validation, including the `pair_comparison` predicate.

```bash
uv run python benchmarks/bench.py --dirs 200 --files 250          # 100k files
uv run python benchmarks/bench.py --dirs 50 --files 20 --latency-ms 20   # simulated remote storage
uv run python benchmarks/bench.py --profile                        # cProfile, sorted by self time
```

## Results

Linux container, Python 3.11, best of several runs. v0.0.2 is the previous release; it did not
evaluate predicates (they were a placeholder), so it did strictly less work.

| Tree | v0.0.2 | v0.1.0 | Speed-up |
|------|--------|--------|----------|
| 20k files, local | 0.24 s | 0.08 s | 2.9× |
| 100k files, local | 1.18 s | 0.42 s | 2.8× |
| 1M files, local | 16.5 s | 5.2 s | 3.2× |
| 2k files, 20 ms per call (object storage) | 63.7 s | 0.16 s | ≈400× |

For reference, `find` walks the 1M file tree in 0.66 s.

## Where the time went

- **One listing per directory.** v0.0.2 called `isdir`/`isfile` for every entry and every
  candidate schema node, plus `ls` per directory. v0.1.0 lists each directory once with
  `ls(detail=True)` and matches in memory. On object storage every call is a round trip, which
  is where the ≈400× comes from. Remote directories reachable by the schema are also listed
  concurrently (16 workers by default, `--workers`).
- **No `stat` per entry locally.** Local directories are read with `os.scandir`, whose entry
  types come from `readdir`; `stat` is only called for size/permission/owner checks.
- **Exact prefilter.** Each schema file node compiles one regex for pattern + extensions; leaf
  nodes without metadata checks are matched without building intermediate objects.
- **Garbage collector paused during validation.** Validation allocates millions of small,
  acyclic objects; the cyclic GC rescanning them cost ~45% of the run on 1M files.

## Should Katachi be rewritten in Rust?

Not now. The remaining cost is ~5 µs per entry of Python work. A Rust core could plausibly bring
1M local files from ~5 s to ~1 s, but:

- on remote storage (a main use case) run time is dominated by listing latency, which Rust
  doesn't change and which is already parallelized;
- Katachi's extensibility (actions, validators, predicates in Python) and the fsspec ecosystem
  (S3, Azure, GCS, archives, ...) are its core value, and would have to cross a language boundary;
- 100k files validate in well under a second, fast enough for pre-commit and CI.

If multi-million file local trees become a common use case, the natural next step is an
optional compiled scanner (e.g. a PyO3 extension) behind the `FsSnapshot` interface, keeping
the schema model and plugin API in Python.
