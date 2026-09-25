from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from katachi.schema.importer import SchemaError, load_schema_file
from katachi.schema.schema_node import SchemaNode
from katachi.utils.fs_utils import get_filesystem

console = Console(stderr=True)


def load_schema_or_raise(schema_path: str, target_path: str | None = None) -> SchemaNode:
    """
    Load a schema from a local path or fsspec URL.

    Raises:
        SchemaError: If the schema can't be loaded or is invalid
    """
    try:
        schema_fs, schema_path_without_prefix = get_filesystem(schema_path)
        if target_path is None:
            target_path = str(Path(schema_path_without_prefix).parent)
            target_path_without_prefix = target_path
        else:
            _, target_path_without_prefix = get_filesystem(target_path)
    except ValueError as e:
        raise SchemaError(str(e)) from e
    return load_schema_file(schema_path_without_prefix, schema_fs, target_path_without_prefix)


def load_schema(schema_path: str, target_path: str | None = None) -> SchemaNode | None:
    """
    Load the schema from the given path using the appropriate filesystem.

    Args:
        schema_path: Path to the schema.yaml file (can include fsspec prefix)
        target_path: Optional path to the directory (can include fsspec prefix)

    Returns:
        The loaded schema, or None if loading failed (the error is printed)
    """
    try:
        return load_schema_or_raise(schema_path, target_path)
    except SchemaError as e:
        console.print(Panel(f"Failed to load schema: {e!s}", title="Schema error", border_style="red", expand=False))
        return None
