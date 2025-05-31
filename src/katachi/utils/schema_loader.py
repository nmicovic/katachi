from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel

from katachi.schema.importer import load_yaml
from katachi.schema.schema_node import SchemaNode
from katachi.utils.fs_utils import get_filesystem

console = Console()


def load_schema(schema_path: str, target_path: Optional[str] = None) -> Optional[SchemaNode]:
    """
    Load the schema from the given path using the appropriate filesystem.

    Args:
        schema_path: Path to the schema.yaml file (can include fsspec prefix)
        target_path: Optional path to the directory (can include fsspec prefix)

    Returns:
        Optional[SchemaNode]: The loaded schema or None if loading failed
    """
    try:
        # Get filesystem for schema path
        schema_fs, schema_path_without_prefix = get_filesystem(schema_path)

        # If target_path is not provided, use the schema's parent directory
        if target_path is None:
            target_path = str(Path(schema_path_without_prefix).parent)

        # Get filesystem for target path
        target_fs, target_path_without_prefix = get_filesystem(target_path)

        # Load the schema
        schema = load_yaml(schema_path_without_prefix, target_path_without_prefix, schema_fs, target_fs)

        if schema is None:
            console.print(Panel("Failed to load schema!", title="Error", border_style="red", expand=False))
            return None
        else:
            return schema

    except Exception as e:
        console.print(Panel(f"Failed to load schema: {e!s}", title="Error", border_style="red", expand=False))
        return None
