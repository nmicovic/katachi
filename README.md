# katachi

[![Release](https://img.shields.io/github/v/release/nmicovic/katachi)](https://img.shields.io/github/v/release/nmicovic/katachi)
[![Build status](https://img.shields.io/github/actions/workflow/status/nmicovic/katachi/main.yml?branch=main)](https://github.com/nmicovic/katachi/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/nmicovic/katachi/branch/main/graph/badge.svg)](https://codecov.io/gh/nmicovic/katachi)
[![Commit activity](https://img.shields.io/github/commit-activity/m/nmicovic/katachi)](https://img.shields.io/github/commit-activity/m/nmicovic/katachi)
[![License](https://img.shields.io/github/license/nmicovic/katachi)](https://img.shields.io/github/license/nmicovic/katachi)

<div align="center">
  <img src="https://raw.githubusercontent.com/nmicovic/katachi/main/logo.png" alt="Logo" width="300"/>
</div>

**Katachi** (形, *"shape"*) checks that a directory tree has the shape you expect. Describe the
structure once in YAML, then validate datasets, data lakes and project layouts, locally or on
S3 / Azure Blob Storage / GCS, from the command line, in CI, or from Python.

```console
$ katachi validate katachi.yaml datasets/yolo
Validating datasets/yolo against katachi.yaml
╭───┬─────────────────────┬───────────────────────────────────────────────────┬────────────────┬───────╮
│   │ Path                │ Problem                                           │ Rule           │ Node  │
├───┼─────────────────────┼───────────────────────────────────────────────────┼────────────────┼───────┤
│ ✗ │ images/val/0003.JPG │ File extension mismatch: expected .jpg or .jpeg   │ file_extension │ image │
│   │                     │ or .png or .bmp or .webp, got .JPG (did you mean  │                │       │
│   │                     │ '0003.jpg' for image? names are case-sensitive)   │                │       │
╰───┴─────────────────────┴───────────────────────────────────────────────────┴────────────────┴───────╯
╭──────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ ✗ Invalid: 1 error · 727 entries checked in 0.00s · relationship checks skipped until structural     │
│ errors are fixed                                                                                     │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

- **GitHub repository**: <https://github.com/nmicovic/katachi/>
- **Documentation**: <https://nmicovic.github.io/katachi/>

## Features

- 📐 **Declarative schemas** in YAML: name patterns, extensions, required entries, counts, sizes,
  permissions, owners, naming conventions (`snake_case`, `kebab-case`, …)
- 🔗 **Relationships** between files: *every image has a label*, *counts match*, *no duplicate ids*,
  scoped per directory or across the whole tree
- 🧬 **Captures**: a name captured by a directory pattern (`(?P<scene>scene_\d+)`) can be required in
  its descendants (`{scene}_cam\d+.jpg`) and used to pair files (`key: "{split}/{stem}"`)
- 🪄 **`katachi infer`** writes a schema from an existing directory, and **`katachi init`** ships templates
  for YOLO, ImageFolder and cookiecutter-data-science layouts
- ☁️ **Any filesystem** supported by [fsspec](https://filesystem-spec.readthedocs.io): local, `s3://`,
  `abfs://`, `gs://`, `memory://`, zip archives, …
- ⚡ **Fast**: every directory is listed once, remote directories are listed concurrently
  (≈400× faster than v0.0.2 on high-latency storage, ≈3× locally; see [benchmarks](https://github.com/nmicovic/katachi/blob/main/benchmarks/README.md))
- 🤖 **CI-ready**: exit codes, `--format json|github|text`, warnings vs errors, a pre-commit hook
  and a GitHub Action
- 🧩 **Extensible** in Python: actions that process matched files, custom validators and predicates
- ✍️ **Editor completion** through a published JSON Schema

## Installation

```bash
pip install katachi              # local filesystems
pip install "katachi[azure]"     # + Azure Blob Storage (abfs://)
pip install katachi s3fs         # + S3; any fsspec implementation works
```

## Quick start

Generate a schema from a directory you consider correct, or start from a template:

```bash
katachi infer data/ -o katachi.yaml       # infer from an existing tree
katachi init --template yolo              # or: basic, imagefolder, cookiecutter-data-science
```

A schema describes the tree top-down:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/nmicovic/katachi/main/katachi.schema.json
semantical_name: dataset
type: directory
ignore: [".*"]                      # skip .DS_Store, .git, ...
children:
  - semantical_name: readme
    type: file
    pattern_name: README
    extension: .md
    required: true
  - semantical_name: day
    type: directory
    pattern_name: "\\d{4}-\\d{2}-\\d{2}"    # regex, must match the whole name
    min_count: 1
    children:
      - semantical_name: image
        type: file
        pattern_name: "img_\\d+"
        extension: [.jpg, .png]
        max_size: 10485760          # 10 MB
      - semantical_name: label
        type: file
        pattern_name: "img_\\d+"
        extension: .json
      - semantical_name: labeled
        type: predicate
        predicate_type: pair_comparison   # img_1.jpg <-> img_1.json, per day
        elements: [image, label]
```

Validate:

```bash
katachi validate katachi.yaml data/
katachi validate katachi.yaml s3://bucket/data --format json      # machine readable
katachi describe katachi.yaml                                      # show the schema as a tree
```

`validate` exits with **0** when the tree is valid, **1** when it is not (or, with `--strict`, when
there are warnings) and **2** for invalid schemas or arguments.

See the [schema reference](https://nmicovic.github.io/katachi/schema/) for every option.

## Use it in CI

**pre-commit**

```yaml
repos:
  - repo: https://github.com/nmicovic/katachi
    rev: v0.1.0
    hooks:
      - id: katachi
        args: [katachi.yaml, data/]
```

**GitHub Actions** (problems are shown as annotations):

```yaml
- uses: nmicovic/katachi@v0.1.0
  with:
    schema: katachi.yaml
    path: data/
```

## Python API

```python
import katachi

report = katachi.validate("katachi.yaml", "data/")  # or s3://..., abfs://..., a dict schema
if not report.is_valid():
    for problem in report.failures:
        print(problem.path, problem.validator_name, problem.message)

print(report.stats.matches)  # Counter of matched entries per schema node
print(report.to_dict())  # JSON serializable
```

### Process matched files with actions

```python
from katachi import register_action


@register_action("image")
def index_image(node, path, parents, context):
    day = next(p for n, p in parents if n.semantical_name == "day")
    context["index"].setdefault(day, []).append(path)


index = {}
report = katachi.validate("katachi.yaml", "data/", execute_actions=True, context={"index": index})
```

The same file can be used from the CLI: `katachi validate katachi.yaml data/ --plugin my_actions.py --execute-actions`.

### Custom validators and predicates

```python
import os

from katachi import ValidationResult, register_predicate, register_validator


@register_validator("not_empty")
def not_empty(node, path):
    if node.semantical_name == "label" and os.path.getsize(path) == 0:
        return [ValidationResult(False, "label file is empty", path, "not_empty", node.semantical_name)]
    return []


@register_predicate("same_count")
def same_count(predicate, dir_path, elements):
    counts = {name: len(contexts) for name, contexts in elements.items()}
    ok = len(set(counts.values())) <= 1
    return [ValidationResult(ok, f"counts: {counts}", dir_path, "same_count", predicate.semantical_name)]
```

See [extending Katachi](https://nmicovic.github.io/katachi/extending/) for details.

### Azure Blob Storage

```bash
pip install "katachi[azure]"
export AZURE_STORAGE_ACCOUNT_NAME="your_storage_account"
export AZURE_STORAGE_SAS_TOKEN="your_sas_token"      # or AZURE_STORAGE_ACCOUNT_KEY / AZURE_STORAGE_CONNECTION_STRING
katachi validate abfs://container/schema.yaml abfs://container/path
```

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](https://github.com/nmicovic/katachi/blob/main/CONTRIBUTING.md) for details.

## License

This project is licensed under the terms of the [MIT License](https://github.com/nmicovic/katachi/blob/main/LICENSE).
