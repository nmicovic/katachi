from pathlib import Path
from typing import Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from katachi.validation.core import ValidationReport, ValidationResult

console = Console()


def create_failures_table(failures: list[ValidationResult]) -> Table:
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
    table.add_column("Node Origin", style="blue")

    for failure in failures:
        table.add_row(str(failure.path), failure.message, failure.validator_name, failure.node_origin)

    return table


def create_detailed_report_tree(validation_report: ValidationReport) -> Tree:
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


def display_validation_results(
    report: ValidationReport, detail_report: bool = False, report_length: Optional[int] = None
) -> None:
    """
    Display validation results in a formatted way.

    Args:
        report: The validation report to display
        detail_report: Whether to show a detailed report
    """
    if report.is_valid():
        console.print(Panel("✅ All validations passed successfully!", style="green"))
        return

    # Create a table for the results
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Status", style="dim")
    table.add_column("Path")
    table.add_column("Message")

    clipped_results = False
    displayed_count = 0

    # Add all results to the table
    for i, result in enumerate(report.results):
        status = "✅" if result.is_valid else "❌"
        style = "green" if result.is_valid else "red"
        table.add_row(status, result.path, result.message, style=style)
        displayed_count += 1
        if report_length and i >= report_length - 1:
            clipped_results = True
            break

    # Display the table
    console.print(table)

    if not report_length and clipped_results:
        skipped_count = len(report.results) - displayed_count
        console.print(
            f"Showing first {displayed_count} results, skipped {skipped_count} more results. Use --report-length to limit output."
        )
        print("WTF")

    # If detailed report is requested, show additional information
    if detail_report:
        _display_detailed_report(report)


def _display_detailed_report(report: ValidationReport) -> None:
    """
    Display a detailed validation report.

    Args:
        report: The validation report to display
    """
    # Group results by validator
    validator_results: dict[str, list[ValidationResult]] = {}
    for result in report.results:
        if result.validator_name not in validator_results:
            validator_results[result.validator_name] = []
        validator_results[result.validator_name].append(result)

    # Display results by validator
    for validator_name, results in validator_results.items():
        console.print(Panel(f"Validator: {validator_name}", style="bold blue"))

        # Create a table for this validator's results
        table = Table(show_header=True, header_style="bold")
        table.add_column("Status", style="dim")
        table.add_column("Path")
        table.add_column("Message")
        table.add_column("Node")

        # Add results to the table
        for result in results:
            status = "✅" if result.is_valid else "❌"
            style = "green" if result.is_valid else "red"
            table.add_row(status, result.path, result.message, result.node_origin, style=style)

        console.print(table)

    # Display any action results if present
    if "action_results" in report.context:
        console.print(Panel("Action Results", style="bold yellow"))
        action_table = Table(show_header=True, header_style="bold")
        action_table.add_column("Status", style="dim")
        action_table.add_column("Validator")
        action_table.add_column("Path")
        action_table.add_column("Message")

        for result in report.context["action_results"]:
            status = "✅" if result.is_valid else "❌"
            style = "green" if result.is_valid else "red"
            action_table.add_row(status, result.validator_name, result.path, result.message, style=style)

        console.print(action_table)
