# Contributing to `katachi`

Contributions are welcome, and they are greatly appreciated!
Every little bit helps, and credit will always be given.

You can contribute in many ways:

# Types of Contributions

## Report Bugs

Report bugs at <https://github.com/nmicovic/katachi/issues>

If you are reporting a bug, please include:

- Your operating system name and version.
- Any details about your local setup that might be helpful in troubleshooting.
- Detailed steps to reproduce the bug.

## Fix Bugs

Look through the GitHub issues for bugs.
Anything tagged with "bug" and "help wanted" is open to whoever wants to implement a fix for it.

## Implement Features

Look through the GitHub issues for features.
Anything tagged with "enhancement" and "help wanted" is open to whoever wants to implement it.

## Write Documentation

katachi could always use more documentation, whether as part of the official docs, in docstrings, or even on the web in blog posts, articles, and such.

## Submit Feedback

The best way to send feedback is to file an issue at <https://github.com/nmicovic/katachi/issues>.

If you are proposing a new feature:

- Explain in detail how it would work.
- Keep the scope as narrow as possible, to make it easier to implement.
- Remember that this is a volunteer-driven project, and that contributions
  are welcome :)

# Get Started

You need [`uv`](https://docs.astral.sh/uv/) and Git.

```bash
git clone git@github.com:YOUR_NAME/katachi.git
cd katachi
make install          # uv sync + pre-commit hooks
```

Everyday commands:

| Command | What it does |
|---------|--------------|
| `make test` | Run the test suite with coverage |
| `make check` | Lockfile check, pre-commit (ruff, formatting, actionlint, ...), mypy, deptry |
| `make docs` | Serve the documentation locally (`make docs-test` builds it strictly) |
| `make bench` | Benchmark validation on a 100k file tree |
| `make json-schema` | Regenerate `katachi.schema.json` after changing schema keys |
| `uv run --python 3.10 pytest` | Run the tests on another Python version (uv downloads it if needed) |

CI runs the same checks on Linux (Python 3.10 to 3.14), Windows and macOS, plus a job with the
lowest supported dependency versions and a job that builds the package and smoke-tests the
installed wheel.

# Architecture

```text
src/katachi/
  cli.py                  Typer CLI (validate, describe, check-schema, infer, init, json-schema)
  __init__.py             Public Python API (validate, load_schema, register_*)
  schema/
    schema_node.py        SchemaNode / SchemaDirectory / SchemaFile / SchemaPredicateNode
    importer.py           YAML -> schema nodes, strict key checking, SchemaError with locations
    json_schema.py        JSON Schema for editors (keep in sync with importer.ALLOWED_KEYS)
    infer.py              Infer a schema from an existing tree
    actions.py            Action registry (callbacks for matched entries)
  validation/
    snapshot.py           Cached directory listings (one ls per directory, concurrent prefetch)
    validators.py         Matching engine: structure -> predicates -> actions
    predicates.py         Built-in and custom predicates
    registry.py           Matched entries (NodeContext) used by predicates and actions
    core.py               ValidationResult / ValidationReport / custom validator registry
  display/                Rich tables, JSON / GitHub / text output, schema tree
  templates/              Schemas shipped with `katachi init`
```

Validation is a pure function of a filesystem snapshot and a schema: `SchemaValidator.validate_schema`
lists directories through `FsSnapshot`, matches entries in memory (`_Matcher`), then evaluates
predicates on the chosen matches and finally runs actions. Performance matters: run `make bench`
before and after changes to the matcher or snapshot (see `benchmarks/README.md`).

## Adding a schema key

1. Parse and validate it in `schema/importer.py` (add it to `ALLOWED_KEYS`) and store it on the node.
2. Describe it in `schema/json_schema.py` (`PROPERTIES`), then run `make json-schema`.
3. Implement the check in `validation/validators.py` and add tests.
4. Document it in `docs/schema.md` and `CHANGELOG.md`.

`tests/test_schema_loading.py` fails if the JSON Schema and the parser disagree.

# Releasing

1. Update the version in `pyproject.toml` (`uv version --bump minor`) and `CHANGELOG.md`, merge to `main`.
2. Create a GitHub release with the tag `vX.Y.Z`. The release workflow checks that the tag matches
   the version, runs the tests, publishes to PyPI with trusted publishing and deploys the docs.

# Pull Request Guidelines

Before you submit a pull request, check that it meets these guidelines:

1. The pull request should include tests.
2. If the pull request adds functionality, the docs (`docs/`) and `CHANGELOG.md` should be updated.
3. `make check` and `make test` pass.
