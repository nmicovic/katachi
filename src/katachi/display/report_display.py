"""Display utilities for validation reports (rich terminal output, JSON, GitHub annotations, plain text)."""

from __future__ import annotations

import json
import os
from collections import Counter
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from katachi.validation.core import ValidationReport, ValidationResult

console = Console()

OUTPUT_FORMATS = ("rich", "text", "json", "github")


def relative_path(path: str, root: str | None) -> str:
    """Show a path relative to the validated root (``.`` for the root itself)."""
    if root:
        root = root.rstrip("/")
        if path == root:
            return "."
        if path.startswith(root + "/"):
            return path[len(root) + 1 :]
    return path


def _problems(report: ValidationReport, include_warnings: bool = True) -> list[ValidationResult]:
    return [r for r in report.results if r.is_error or (include_warnings and r.is_warning)]


def summary_line(report: ValidationReport, elapsed: float | None = None) -> str:
    """One line summary, e.g. ``✗ 3 errors, 1 warning · 20001 entries checked in 0.08s``."""
    errors, warnings = len(report.failures), len(report.warnings)
    parts = []
    if errors:
        parts.append(f"{errors} error{'s' if errors != 1 else ''}")
    if warnings:
        parts.append(f"{warnings} warning{'s' if warnings != 1 else ''}")
    status = "✓ Valid" if report.is_valid() else "✗ Invalid"
    detail = f": {', '.join(parts)}" if parts else ""
    timing = f" in {elapsed:.2f}s" if elapsed is not None else ""
    skipped = " · relationship checks skipped until structural errors are fixed" if report.predicates_skipped else ""
    return f"{status}{detail} · {report.stats.entries_checked} entries checked{timing}{skipped}"


def create_failures_table(failures: list[ValidationResult], root: str | None = None) -> Table:
    """
    Create a rich table showing validation failures.

    Args:
        failures: List of ValidationResult objects representing failures
        root: Root path used to shorten displayed paths

    Returns:
        A Rich Table object
    """
    table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
    table.add_column("", no_wrap=True)
    table.add_column("Path", style="cyan", overflow="fold")
    table.add_column("Problem", overflow="fold")
    table.add_column("Rule", style="blue", no_wrap=True)
    table.add_column("Node", style="dim", no_wrap=True)

    for failure in failures:
        icon, style = ("✗", "red") if failure.severity == "error" else ("!", "yellow")
        table.add_row(
            f"[{style}]{icon}[/]",
            relative_path(failure.path, root),
            f"[{style}]{failure.message}[/]",
            failure.validator_name,
            failure.node_origin,
        )
    return table


def create_detailed_report_tree(validation_report: ValidationReport) -> Tree:
    """
    Create a detailed tree report of validation results, grouped by path.

    Args:
        validation_report: The report to display

    Returns:
        A rich Tree object for display
    """
    root = validation_report.root_path
    tree = Tree(f"[bold]Validation results for[/] {root}")
    results_by_path: dict[str, list[ValidationResult]] = {}
    for result in validation_report.results:
        results_by_path.setdefault(result.path, []).append(result)
    for path, results in sorted(results_by_path.items()):
        style = (
            "red" if any(r.is_error for r in results) else "yellow" if any(r.is_warning for r in results) else "green"
        )
        node = tree.add(f"[{style}]{relative_path(path, root)}[/]")
        for r in results:
            icon = "✓" if r.is_valid else "✗" if r.is_error else "!"
            color = "green" if r.is_valid else "red" if r.is_error else "yellow"
            node.add(f"[{color}]{icon}[/] [{r.validator_name}] {r.message}")
    actions = validation_report.action_results
    if actions:
        action_node = tree.add("[blue]Actions[/]")
        for a in actions:
            icon = "[green]✓[/]" if a.success else "[red]✗[/]"
            action_node.add(f"{icon} {a.action_name} {relative_path(a.path, root)}: {a.message}")
    return tree


def display_validation_results(
    report: ValidationReport,
    detail_report: bool = False,
    report_length: int | None = None,
    elapsed: float | None = None,
    out: Console | None = None,
) -> None:
    """
    Display validation results in a formatted way.

    Args:
        report: The validation report to display
        detail_report: Whether to show a detailed report (per rule statistics, matches, actions)
        report_length: Show at most this many problems (all when None or 0)
        elapsed: Validation time in seconds, shown in the summary
        out: Console to print to
    """
    out = out or console
    problems = _problems(report)
    if problems:
        shown = problems[:report_length] if report_length else problems
        out.print(create_failures_table(shown, report.root_path))
        if len(shown) < len(problems):
            out.print(
                f"[dim]… {len(problems) - len(shown)} more problem(s) not shown (use --report-length 0 to show all)[/]"
            )

    if detail_report:
        _display_detailed_report(report, out)

    style = "green" if report.is_valid() else "red"
    out.print(Panel(summary_line(report, elapsed), style=style, expand=False))


def _display_detailed_report(report: ValidationReport, out: Console) -> None:
    """
    Display a detailed validation report.

    Args:
        report: The validation report to display
        out: Console to print to
    """
    rules = Counter(r.validator_name for r in _problems(report))
    if rules:
        table = Table(title="Problems by rule", box=box.SIMPLE, header_style="bold")
        table.add_column("Rule")
        table.add_column("Count", justify="right")
        for rule, count in rules.most_common():
            table.add_row(rule, str(count))
        out.print(table)

    if report.stats.matches:
        table = Table(title="Matched entries per schema node", box=box.SIMPLE, header_style="bold")
        table.add_column("Node")
        table.add_column("Matches", justify="right")
        for name, count in report.stats.matches.most_common():
            table.add_row(name, str(count))
        out.print(table)

    predicate_results = [r for r in report.results if r.is_valid]
    if predicate_results:
        table = Table(title="Passed predicates", box=box.SIMPLE, header_style="bold")
        table.add_column("Path")
        table.add_column("Predicate")
        table.add_column("Message")
        for r in predicate_results:
            table.add_row(relative_path(r.path, report.root_path), r.node_origin, r.message, style="green")
        out.print(table)

    if report.action_results:
        table = Table(title="Actions", box=box.SIMPLE, header_style="bold")
        table.add_column("")
        table.add_column("Action")
        table.add_column("Path")
        table.add_column("Message")
        for a in report.action_results:
            table.add_row(
                "✅" if a.success else "❌",
                a.action_name,
                relative_path(a.path, report.root_path),
                a.message,
                style="green" if a.success else "red",
            )
        out.print(table)


def report_to_json(report: ValidationReport, elapsed: float | None = None) -> str:
    """Serialize a report to JSON (paths are kept absolute, plus a ``relative_path`` field)."""
    data: dict[str, Any] = report.to_dict()
    for result in data["results"]:
        result["relative_path"] = relative_path(result["path"], report.root_path)
    if elapsed is not None:
        data["elapsed_seconds"] = round(elapsed, 4)
    return json.dumps(data, indent=2, default=str)


def _escape_github(value: str, is_property: bool = False) -> str:
    value = value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    if is_property:
        value = value.replace(":", "%3A").replace(",", "%2C")
    return value


def report_to_github(report: ValidationReport) -> str:
    """Format problems as GitHub Actions workflow commands (``::error file=...::message``)."""
    lines = []
    cwd = os.getcwd()
    for r in _problems(report):
        level = "error" if r.is_error else "warning" if r.severity == "warning" else "notice"
        path = os.path.relpath(r.path, cwd) if os.path.isabs(r.path) and r.path.startswith(cwd) else r.path
        lines.append(
            f"::{level} file={_escape_github(path, True)},title={_escape_github('katachi ' + r.validator_name, True)}"
            f"::{_escape_github(r.message)}"
        )
    lines.append(summary_line(report))
    return "\n".join(lines)


def report_to_text(report: ValidationReport, elapsed: float | None = None) -> str:
    """Plain, grep-friendly output: ``path: severity [rule] message`` per problem, then a summary."""
    lines = [
        f"{relative_path(r.path, report.root_path)}: {r.severity} [{r.validator_name}] {r.message}"
        for r in _problems(report)
    ]
    lines.append(summary_line(report, elapsed))
    return "\n".join(lines)
