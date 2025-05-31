from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel

from katachi.schema.importer import load_yaml
from katachi.schema.schema_node import SchemaNode

console = Console()


def load_schema(schema_path: Path, target_path: Path) -> Optional[SchemaNode]:
    """
    Load the schema from the given path.

    Args:
        schema_path: Path to the schema.yaml file
        target_path: Path to the directory to validate

    Returns:
        Loaded schema object or None if loading failed
    """
    try:
        schema = load_yaml(schema_path, target_path)
        if schema is None:
            console.print(Panel("Failed to load schema!", title="Error", border_style="red", expand=False))
            return None
        else:
            return schema
    except Exception as e:
        console.print(Panel(f"Failed to load schema: {e!s}", title="Error", border_style="red", expand=False))
        return None
