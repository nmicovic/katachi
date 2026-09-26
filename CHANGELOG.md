# Changelog

## 0.1.0

A large overhaul: Katachi is now CI-ready, much faster and far more expressive.

### Breaking changes

- `pattern_name` must match the **whole** name (it used to be a prefix match, so `img\d+` accepted
  `img1_backup.jpg`). For files it is matched against the name without the declared extension.
- Extensions are exact and normalized: `jpg` means `.jpg` (it used to accept `xjpg`).
- Python 3.10+ is required (3.9 is end-of-life). Azure support is an extra: `pip install "katachi[azure]"`.
- Error messages changed (e.g. `File extension mismatch: expected .jpg, got .json`).
- `permissions` must be a quoted string (`"0750"`): YAML reads an unquoted `0750` as a number.

### Fixed

- `katachi validate` exits with 1 when validation fails (it always exited with 0) and with 2 for
  invalid schemas or arguments.
- Predicates are actually evaluated: `pair_comparison` used to be a placeholder that always passed.
- Missing entries are detected (`required`, `min_count`, `max_count`); before, only entries that
  existed were checked.
- Owner and permission checks work again (they were lost in the fsspec migration).
- Entries from discarded alternatives of ambiguous schemas are no longer registered, so
  predicates and actions only see real matches.
- `--detail-report` no longer crashes when actions ran; action exceptions are reported instead of
  aborting the run.
- The report clipping message is shown, and a stray debug print was removed.
- Unexpected errors during validation (e.g. remote authentication failures) are reported with
  exit code 2 instead of a traceback.
- Azure credentials are read from `AZURE_STORAGE_ACCOUNT_NAME`/`AZURE_STORAGE_ACCOUNT` with a SAS
  token, account key or connection string, as documented.

### Added

- Schema: `required`, `min_count`, `max_count`, `min_size`, `max_size`, `name_case`, `severity`,
  `ignore`, `allow_extra`, lists of extensions, named-group captures reused as `{placeholders}`.
- Predicates: scoped per directory instance, `count_match` and `unique_keys`, `key` / `key_pattern`
  options, custom predicates via `register_predicate`.
- Strict schema checking with locations and "did you mean" suggestions; published JSON Schema
  for editor completion (`katachi json-schema`, `katachi.schema.json`).
- CLI: `--format json|text|github`, `--strict`, `--ignore`, `--plugin`, `--workers`, `--version`,
  `-v`; new `infer`, `init` (templates: basic, yolo, imagefolder, cookiecutter-data-science),
  `check-schema` and `json-schema` commands; compact `describe` tree; case-mismatch hints.
- Any fsspec filesystem (`s3://`, `gs://`, `memory://`, ...), with helpful errors for missing packages.
- Top level Python API: `katachi.validate()`, `katachi.load_schema()`, `register_action`,
  `register_validator`, `register_predicate`; typed package (`py.typed`).
- pre-commit hooks, a GitHub Action and a Docker image definition.
- Tested on Linux, Windows and macOS, and against the lowest supported dependency versions.

### Performance

Every directory is listed once (remote directories concurrently), local listings avoid `stat`
calls, and matching uses an exact regex prefilter: ~3× faster locally and ~400× faster on
high-latency storage than 0.0.2. See [benchmarks](https://github.com/nmicovic/katachi/blob/main/benchmarks/README.md).
