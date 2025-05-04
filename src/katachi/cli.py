from pathlib import Path
from typing import Optional

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from katachi.schema.importer import load_yaml
from katachi.schema.schema_node import SchemaNode
from katachi.schema.validate import validate_schema
from katachi.validation.core import ValidationReport, ValidationResult

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command()
def describe(schema_path: Path, target_path: Path) -> None:
    """
    Describes the schema of a directory structure.

    Args:
        schema_path: Path to the schema.yaml file
        target_path: Path to the directory to describe

    Returns:
        None
    """
    console.print(f"Describing schema [bold cyan]{schema_path}[/] for directory [bold cyan]{target_path}[/]")

    try:
        # Load the schema
        schema = load_yaml(schema_path, target_path)
        console.print(Panel(str(schema), title="Schema Description", border_style="blue", expand=False))
    except Exception as e:
        console.print(Panel(f"Failed to describe schema: {e!s}", title="Error", border_style="red", expand=False))


def _load_schema(schema_path: Path, target_path: Path) -> Optional[SchemaNode]:
    """
    Load the schema from the given path.

    Args:
        schema_path: Path to the schema.yaml file
        target_path: Path to the directory to validate

    Returns:
        Loaded schema object

    Raises:
        typer.Exit: If schema loading fails
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


def _create_failures_table(failures: list[ValidationResult]) -> Table:
    """
    Create a rich table showing validation failures.

    Args:
        failures: List of ValidationResult objects representing failures

    Returns:
        A Rich Table object
    """
    table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
    table.add_column("Path", style="cyan", no_wrap=True)
    table.add_column("Error", style="red")
    table.add_column("Validator", style="blue")

    for failure in failures:
        table.add_row(str(failure.path), failure.message, failure.validator_name)

    return table


def _create_detailed_report_tree(validation_report: ValidationReport) -> Tree:
    """
    Create a tree view of all validations grouped by path.

    Args:
        validation_report: ValidationReport object

    Returns:
        A Rich Tree object
    """
    # Group results by path for better readability
    path_results: dict[str, list[ValidationResult]] = {}
    for result in validation_report.results:
        path_str = str(result.path)
        if path_str not in path_results:
            path_results[path_str] = []
        path_results[path_str].append(result)

    # Create a tree view of validations by path
    tree = Tree("📂 Validation Results", guide_style="dim")

    for path_str, results in sorted(path_results.items()):
        path_node = tree.add(f"[cyan]{path_str}[/]")

        # Add passed validations
        passed = [r for r in results if r.is_valid]
        if passed:
            passed_node = path_node.add("[green]Passed Validations[/]")
            for p in passed:
                msg = p.message if p.message else f"Passed {p.validator_name} check"
                passed_node.add(f"[green]✓[/] {msg}")

        # Add failed validations
        failed = [r for r in results if not r.is_valid]
        if failed:
            failed_node = path_node.add("[red]Failed Validations[/]")
            for f in failed:
                failed_node.add(f"[red]✗[/] [{f.validator_name}] {f.message}")

    return tree


def _display_validation_results(validation_report: ValidationReport, detail_report: bool = False) -> None:
    """
    Display validation results to the console.

    Args:
        validation_report: ValidationReport object
        detail_report: Whether to show a detailed report

    Returns:
        None
    """
    if validation_report.is_valid():
        console.print(
            Panel("Validation successful! All checks passed.", title="Success", border_style="green", expand=False)
        )
        return

    # Display failure summary
    console.print(Panel("Validation failed! See details below.", title="Error", border_style="red", expand=False))

    # Get invalid results
    failures = [r for r in validation_report.results if not r.is_valid]

    # Show the failures by default
    failures_table = _create_failures_table(failures)
    console.print(Panel(failures_table, title="Validation Failures", border_style="red", expand=False))

    # If detailed report is requested, show all validations including passed ones
    if detail_report:
        detailed_tree = _create_detailed_report_tree(validation_report)
        console.print(Panel(detailed_tree, title="Detailed Report", border_style="blue", expand=False))


@app.command()
def validate(
    schema_path: Path,
    target_path: Path,
    detail_report: bool = typer.Option(False, "--detail-report", help="Show detailed validation report"),
) -> None:
    """
    Validates a directory structure against a schema.yaml file.

    Args:
        schema_path: Path to the schema.yaml file
        target_path: Path to the directory to validate
        detail_report: Whether to show a detailed validation report

    Returns:
        None
    """
    console.print(f"Validating schema [bold cyan]{schema_path}[/] against directory [bold cyan]{target_path}[/]")

    # Load the schema
    schema = _load_schema(schema_path, target_path)
    if schema is None:
        console.print(Panel("Failed to load schema!", title="Error", border_style="red", expand=False))
        raise typer.Exit(code=1)

    # Validate the directory structure against the schema
    validation_report = validate_schema(schema, target_path)

    # Display the results
    _display_validation_results(validation_report, detail_report)

    # Exit with error code if validation failed
    if not validation_report.is_valid():
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
