import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from katachi.display.report_display import display_validation_results
from katachi.display.schema_display import create_schema_tree
from katachi.utils.schema_loader import load_schema
from katachi.validation.validators import SchemaValidator

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command()
def describe(schema_path: Path, target_path: Optional[Path] = None) -> None:
    """
    Visualize and describe a schema file structure.

    Args:
        schema_path: Path to the schema.yaml file
        target_path: Optional path to the directory (used for schema resolution)

    Returns:
        None
    """
    console.print(f"Describing schema: [bold cyan]{schema_path}[/]")

    # If target_path is not provided, use the schema's parent directory
    if target_path is None:
        target_path = schema_path.parent
        console.print(f"Using default target directory: [dim]{target_path}[/]")

    try:
        # Load the schema
        schema = load_schema(schema_path, target_path)
        if schema is None:
            return

        # Create the schema visualization
        schema_tree = create_schema_tree(schema)
        console.print(Panel(schema_tree, title="Schema Structure", border_style="blue", expand=True))

    except Exception as e:
        console.print(Panel(f"Failed to describe schema: {e!s}", title="Error", border_style="red", expand=False))


@app.command()
def validate(
    schema_path: Path,
    target_path: Path,
    detail_report: bool = typer.Option(False, "--detail-report", help="Show detailed validation report"),
    execute_actions: bool = typer.Option(False, "--execute-actions", help="Execute actions during/after validation"),
    context_json: str = typer.Option(None, "--context", help="JSON string with context data for actions"),
) -> None:
    """
    Validates a directory structure against a schema.yaml file.

    Args:
        schema_path: Path to the schema.yaml file
        target_path: Path to the directory to validate
        detail_report: Whether to show a detailed validation report
        execute_actions: Whether to execute registered actions
        context_json: JSON string with context data for actions

    Returns:
        None
    """
    console.print(f"Validating schema [bold cyan]{schema_path}[/] against directory [bold cyan]{target_path}[/]")

    # Load the schema
    schema = load_schema(schema_path, target_path)
    if schema is None:
        return

    # Parse context JSON if provided
    context = None
    if context_json:
        try:
            context = json.loads(context_json)
        except json.JSONDecodeError:
            console.print(Panel("Invalid JSON in context parameter", title="Error", border_style="red", expand=False))
            return

    # Validate the directory structure against the schema
    validation_report = SchemaValidator.validate_schema(
        schema, target_path, execute_actions=execute_actions, context=context
    )

    validation_report.sort_by_longest_path()

    # Display the results
    display_validation_results(validation_report, detail_report)

    # Exit with error code if validation failed
    if not validation_report.is_valid():
        return


if __name__ == "__main__":
    app()
