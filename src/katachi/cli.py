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
from katachi.validation.core import ValidationReport, ValidationResult
from katachi.validation.validators import SchemaValidator

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
    Create a detailed tree report of validation results.

    Args:
        validation_report: The report to display

    Returns:
        A rich Tree object for display
    """
    tree = Tree("Validation Results")
    _add_validation_results_to_tree(tree, validation_report)
    _add_action_results_to_tree(tree, validation_report)
    return tree


def _add_validation_results_to_tree(tree: Tree, validation_report: ValidationReport) -> None:
    """
    Add validation results to the tree.

    Args:
        tree: The tree to populate
        validation_report: The report containing validation results
    """
    results_by_path = _group_results_by_path(validation_report.results)

    for path_str, results in sorted(results_by_path.items()):
        path = Path(path_str)
        style = "red" if any(not r.is_valid for r in results) else "green"
        path_name = path.name if path.name else path.absolute()
        path_node = tree.add(f"[{style}]{path_name}[/] [{style}]({path})[/]")

        _add_passed_validations(path_node, results)
        _add_failed_validations(path_node, results)


def _add_action_results_to_tree(tree: Tree, validation_report: ValidationReport) -> None:
    """
    Add action results to the tree if available.

    Args:
        tree: The tree to populate
        validation_report: The report containing action results
    """
    if hasattr(validation_report, "context") and "action_results" in validation_report.context:
        action_results = validation_report.context["action_results"]
        if action_results:
            action_node = tree.add("[blue]Actions[/]")
            actions_by_path = _group_results_by_path(action_results)

            for path_str, results in sorted(actions_by_path.items()):
                path = Path(path_str)
                path_name = path.name if path.name else path.absolute()
                action_path_node = action_node.add(f"[blue]{path_name}[/] ([blue]{path}[/])")

                for result in results:
                    style = "green" if result.is_valid else "red"
                    action_path_node.add(f"[{style}]✓[/] {result.message}")


def _group_results_by_path(results: list[ValidationResult]) -> dict[str, list[ValidationResult]]:
    """
    Group results by their path.

    Args:
        results: List of results to group

    Returns:
        A dictionary with paths as keys and lists of results as values
    """
    results_by_path: dict[str, list[ValidationResult]] = {}
    for result in results:
        path_str = str(result.path)
        if path_str not in results_by_path:
            results_by_path[path_str] = []
        results_by_path[path_str].append(result)
    return results_by_path


def _add_passed_validations(path_node: Tree, results: list[ValidationResult]) -> None:
    """
    Add passed validations to the tree node.

    Args:
        path_node: The tree node to populate
        results: List of validation results
    """
    passed = [r for r in results if r.is_valid]
    if passed:
        passed_node = path_node.add("[green]Passed Validations[/]")
        for p in passed:
            msg = p.message if p.message else f"Passed {p.validator_name} check"
            passed_node.add(f"[green]✓[/] {msg}")


def _add_failed_validations(path_node: Tree, results: list[ValidationResult]) -> None:
    """
    Add failed validations to the tree node.

    Args:
        path_node: The tree node to populate
        results: List of validation results
    """
    failed = [r for r in results if not r.is_valid]
    if failed:
        failed_node = path_node.add("[red]Failed Validations[/]")
        for f in failed:
            failed_node.add(f"[red]✗[/] [{f.validator_name}] {f.message}")


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
    schema = _load_schema(schema_path, target_path)
    if schema is None:
        console.print(Panel("Failed to load schema!", title="Error", border_style="red", expand=False))
        return

    # Parse context JSON if provided
    context = None
    if context_json:
        try:
            import json

            context = json.loads(context_json)
        except json.JSONDecodeError:
            console.print(Panel("Invalid JSON in context parameter", title="Error", border_style="red", expand=False))
            return

    # Validate the directory structure against the schema
    validation_report = SchemaValidator.validate_schema(
        schema, target_path, execute_actions=execute_actions, context=context
    )

    # Display the results
    _display_validation_results(validation_report, detail_report)

    # Exit with error code if validation failed
    if not validation_report.is_valid():
        return


if __name__ == "__main__":
    app()
