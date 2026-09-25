# Command line & CI

```text
katachi validate SCHEMA TARGET   Validate a directory against a schema
katachi describe SCHEMA          Check a schema and show it as a tree
katachi check-schema SCHEMA...   Check schema files (used by the pre-commit hook)
katachi infer TARGET             Generate a schema from an existing directory
katachi init                     Create a starter schema from a template
katachi json-schema              Print the JSON Schema of schema files
katachi --version
```

`SCHEMA` and `TARGET` can be local paths or any [fsspec](https://filesystem-spec.readthedocs.io) URL
(`s3://bucket/data`, `abfs://container/data`, `gs://...`, `memory://...`).

## `katachi validate`

| Option | Description |
|--------|-------------|
| `-f, --format` | `rich` (default), `text` (one `path: severity [rule] message` line per problem), `json`, `github` (workflow annotations) |
| `--strict` | Treat warnings as errors |
| `-i, --ignore GLOB` | Skip entries with matching names everywhere (repeatable), e.g. `--ignore '.*'` |
| `--report-length N` | Show at most N problems (default 40, `0` = all) |
| `--detail-report` | Also show problems per rule, matches per schema node, passed predicates and actions |
| `-p, --plugin FILE_OR_MODULE` | Import Python code registering actions, validators or predicates (repeatable) |
| `--execute-actions` | Run registered actions for matched entries |
| `--context JSON` | JSON object passed to actions |
| `--workers N` | Concurrent directory listings (default 1 locally, 16 for remote filesystems) |
| `-v, --verbose` | Debug logs (global option: `katachi -v validate ...`) |

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Valid (warnings allowed unless `--strict`) |
| 1 | Validation failed, or an action failed |
| 2 | Invalid schema, arguments or plugin |

### JSON output

```bash
katachi validate katachi.yaml data/ --format json | jq '.results[] | select(.is_valid | not) | .relative_path'
```

```json
{
  "valid": false,
  "root": "/abs/path/data",
  "failure_count": 1,
  "warning_count": 0,
  "predicates_skipped": false,
  "stats": {"entries_checked": 2, "directories_listed": 1, "matches": {"root": 1}},
  "results": [
    {
      "is_valid": false,
      "message": "Filename does not match pattern: \\d+ (got 'wrong_name')",
      "path": "/abs/path/data/wrong_name.jpg",
      "relative_path": "wrong_name.jpg",
      "validator_name": "file_pattern",
      "node_origin": "image_file",
      "severity": "error"
    }
  ],
  "actions": [],
  "elapsed_seconds": 0.0012
}
```

## `katachi infer`

```bash
katachi infer data/ -o katachi.yaml
```

Sibling entries are grouped by their shape (runs of digits become `\d{n}` or `\d+`), directories
with the same shape are merged, entries present in every instance become `required`, and files
sharing the same names with different extensions get a `pair_comparison` predicate. Hidden
entries are ignored unless `--include-hidden` is passed. The result always validates the tree it
was inferred from; review and tighten it by hand.

## `katachi init`

```bash
katachi init --list
katachi init --template yolo -o katachi.yaml
```

Templates: `basic`, `yolo` (Ultralytics detection datasets), `imagefolder` (image classification,
`<split>/<class>/<image>`), `cookiecutter-data-science`.

## pre-commit

```yaml
repos:
  - repo: https://github.com/nmicovic/katachi
    rev: v0.1.0
    hooks:
      - id: katachi
        args: [katachi.yaml, data/]
      - id: katachi-check-schema        # validates schema files named katachi.yaml / *.katachi.yaml
```

## GitHub Actions

```yaml
jobs:
  structure:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: nmicovic/katachi@v0.1.0
        with:
          schema: katachi.yaml
          path: data/
          # extra-args: --strict --ignore '.*'
```

Problems are reported as annotations on the run. Without the action:

```yaml
- run: pipx run katachi validate katachi.yaml data/ --format github
```
