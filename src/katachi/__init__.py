"""
Katachi (形, "shape") validates directory structures against YAML schemas.

Quick start::

    import katachi

    report = katachi.validate("schema.yaml", "data/")
    if not report.is_valid():
        for failure in report.failures:
            print(failure.path, failure.message)
"""

from __future__ import annotations

from typing import Any

from katachi.schema.actions import ActionRegistry, ActionTiming, register_action
from katachi.schema.importer import SchemaError, load_schema_file, parse_schema
from katachi.schema.schema_node import SchemaDirectory, SchemaFile, SchemaNode, SchemaPredicateNode
from katachi.validation.core import ValidationReport, ValidationResult, ValidatorRegistry
from katachi.validation.predicates import register_predicate
from katachi.validation.registry import NodeContext

register_validator = ValidatorRegistry.register


def load_schema(schema: str) -> SchemaNode:
    """
    Load a schema from a local path or fsspec URL.

    Raises:
        SchemaError: If the schema can't be read or is invalid
    """
    from katachi.utils.schema_loader import load_schema_or_raise

    return load_schema_or_raise(schema)


def validate(
    schema: str | SchemaNode | dict[str, Any],
    target: str,
    *,
    execute_actions: bool = False,
    context: dict[str, Any] | None = None,
    ignore: tuple[str, ...] | list[str] = (),
    workers: int | None = None,
) -> ValidationReport:
    """
    Validate a directory against a schema.

    Args:
        schema: Path/URL of a schema file, a parsed schema, or a schema document (dict)
        target: Directory to validate (local path or fsspec URL such as ``s3://bucket/data``)
        execute_actions: Run registered actions for matched entries
        context: Context passed to actions
        ignore: Glob patterns of entry names to skip everywhere
        workers: Concurrent directory listings for remote filesystems

    Raises:
        SchemaError: If the schema is invalid
    """
    from katachi.utils.fs_utils import get_filesystem
    from katachi.validation.validators import SchemaValidator

    if isinstance(schema, str):
        schema = load_schema(schema)
    elif isinstance(schema, dict):
        schema = parse_schema(schema)
    fs, path = get_filesystem(target)
    return SchemaValidator.validate_schema(
        schema, path, fs, execute_actions=execute_actions, context=context, ignore=ignore, workers=workers
    )


__all__ = [
    "ActionRegistry",
    "ActionTiming",
    "NodeContext",
    "SchemaDirectory",
    "SchemaError",
    "SchemaFile",
    "SchemaNode",
    "SchemaPredicateNode",
    "ValidationReport",
    "ValidationResult",
    "ValidatorRegistry",
    "load_schema",
    "load_schema_file",
    "parse_schema",
    "register_action",
    "register_predicate",
    "register_validator",
    "validate",
]
