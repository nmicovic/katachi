# Python API & extending Katachi

## Validating from Python

```python
import katachi

report = katachi.validate("katachi.yaml", "data/")  # schema path/URL, dict or parsed schema
report = katachi.validate({"type": "directory", "children": [...]}, "s3://bucket/data")

report.is_valid()  # False if there is any error (warnings are allowed)
report.failures  # errors: ValidationResult(path, message, validator_name, node_origin, severity, ...)
report.warnings  # warning/info results
report.stats.matches  # Counter of matched entries per semantical name
report.to_dict()  # JSON serializable
```

Katachi logs through [loguru](https://github.com/Delgan/loguru) and, like any library, keeps
quiet until you opt in: `from loguru import logger; logger.enable("katachi")`.

`katachi.load_schema(path)` parses a schema (raising `katachi.SchemaError` with the location of
the problem) and `katachi.parse_schema(document)` parses an already loaded document.

## Actions

Actions are callbacks run for entries matched by a node (by semantical name). They only run for
matches that were finally chosen, never for alternatives discarded while resolving ambiguous
schemas.

```python
from katachi import ActionTiming, register_action


@register_action("image")
def resize(node, path, parents, context):
    """parents: [(schema_node, path), ...] from the root down to the parent directory."""
    day = dict((n.semantical_name, p) for n, p in parents)["day"]
    context["queue"].append((day, path))


@register_action("dataset", timing=ActionTiming.AFTER_VALIDATION)
def publish(node, path, parents, context):
    """AFTER_VALIDATION actions only run when the whole tree, predicates included, is valid."""
```

```python
queue = []
report = katachi.validate("katachi.yaml", "data/", execute_actions=True, context={"queue": queue})
[a for a in report.action_results if not a.success]  # exceptions are captured, not raised
```

Values captured by named groups are available on the registry contexts:

```python
registry = report.context["registry"]
for ctx in registry.get_contexts_by_name("frame"):
    print(ctx.path, ctx.captures["scene"])
```

## Custom validators

A validator runs for every entry that passed a node's built-in checks. Returning a failed result
makes the entry *not match* that node, so the next candidate node is tried.

```python
import os
from katachi import ValidationResult, register_validator


@register_validator("labels_not_empty")
def labels_not_empty(node, path):
    if node.semantical_name == "label" and os.path.getsize(path) == 0:
        return [ValidationResult(False, "label file is empty", path, "labels_not_empty", node.semantical_name)]
    return []
```

Use `node.metadata` to parametrize validators from the schema.

## Custom predicates

```python
from katachi import ValidationResult, register_predicate


@register_predicate("at_least_one_per_class")
def at_least_one_per_class(predicate, dir_path, elements):
    """elements: {semantical_name: [NodeContext, ...]} for this directory instance."""
    minimum = predicate.options.get("minimum", 1)
    ok = all(len(contexts) >= minimum for contexts in elements.values())
    return [
        ValidationResult(ok, f"need {minimum} of each", dir_path, "at_least_one_per_class", predicate.semantical_name)
    ]
```

```yaml
- semantical_name: balanced
  type: predicate
  predicate_type: at_least_one_per_class
  elements: [cat, dog]
  options: {minimum: 10}
```

## Using plugins from the CLI

Put registrations in a module and pass it with `--plugin` (a file path or an importable module):

```bash
katachi validate katachi.yaml data/ --plugin checks.py --execute-actions --context '{"out": "build"}'
```

Plugins are only loaded when explicitly passed: schemas never execute code by themselves.
