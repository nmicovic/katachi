"""Command line interface: ``katachi validate | describe | check-schema | infer | init | json-schema``."""

from __future__ import annotations

import json
import time
from enum import Enum
from importlib import metadata, resources
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel

from katachi.display.report_display import (
    display_validation_results,
    report_to_github,
    report_to_json,
    report_to_text,
)
from katachi.display.schema_display import create_schema_tree
from katachi.schema.importer import SchemaError
from katachi.utils.fs_utils import get_filesystem
from katachi.utils.logger import logger, set_log_level
from katachi.utils.plugins import PluginError, load_plugin
from katachi.utils.schema_loader import load_schema_or_raise

app = typer.Typer(
    no_args_is_help=True,
    help="Katachi (形) validates directory structures against YAML schemas.",
    rich_markup_mode="rich",
)
console = Console()
err_console = Console(stderr=True)

#: Exit codes: 0 = valid, 1 = validation failed, 2 = usage/schema/runtime error
EXIT_OK, EXIT_INVALID, EXIT_ERROR = 0, 1, 2


class _Choice(str, Enum):
    """String enum used for CLI choices; ``str()`` gives the value (older typer versions rely on it)."""

    def __str__(self) -> str:
        return str(self.value)


class OutputFormat(_Choice):
    """Output formats of ``katachi validate`` (see ``display.report_display.OUTPUT_FORMATS``)."""

    RICH = "rich"
    TEXT = "text"
    JSON = "json"
    GITHUB = "github"


class Template(_Choice):
    """Schema templates shipped in ``katachi/templates``."""

    BASIC = "basic"
    YOLO = "yolo"
    IMAGEFOLDER = "imagefolder"
    COOKIECUTTER_DATA_SCIENCE = "cookiecutter-data-science"


def _fail(message: str, title: str = "Error") -> typer.Exit:
    err_console.print(Panel(message, title=title, border_style="red", expand=False))
    return typer.Exit(EXIT_ERROR)


def _version_callback(value: bool) -> None:
    if value:
        try:
            version = metadata.version("katachi")
        except metadata.PackageNotFoundError:  # pragma: no cover
            version = "unknown"
        console.print(f"katachi {version}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show the version and exit."),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show debug logs.")] = False,
) -> None:
    """Katachi (形) validates directory structures against YAML schemas."""
    set_log_level("DEBUG" if verbose else "WARNING")


@app.command()
def validate(
    schema_path: Annotated[
        str, typer.Argument(help="Schema file (local path or fsspec URL, e.g. abfs://c/schema.yaml).")
    ],
    target_path: Annotated[str, typer.Argument(help="Directory to validate (local path or fsspec URL).")],
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format.", case_sensitive=False),
    ] = OutputFormat.RICH,
    detail_report: Annotated[
        bool, typer.Option("--detail-report", help="Show statistics per rule and schema node, and actions.")
    ] = False,
    report_length: Annotated[int, typer.Option("--report-length", help="Show at most N problems (0 = all).")] = 40,
    strict: Annotated[bool, typer.Option("--strict", help="Treat warnings as errors.")] = False,
    ignore: Annotated[
        list[str] | None,
        typer.Option("--ignore", "-i", help="Glob of entry names to skip everywhere (repeatable), e.g. '.DS_Store'."),
    ] = None,
    plugins: Annotated[
        list[str] | None,
        typer.Option(
            "--plugin", "-p", help="Python file or module registering actions/validators/predicates (repeatable)."
        ),
    ] = None,
    execute_actions: Annotated[
        bool, typer.Option("--execute-actions", help="Execute registered actions for matched entries.")
    ] = False,
    context_json: Annotated[
        str | None, typer.Option("--context", help="JSON object passed to actions as context.")
    ] = None,
    workers: Annotated[
        int | None,
        typer.Option("--workers", help="Concurrent directory listings (default: 1 local, 16 remote)."),
    ] = None,
) -> None:
    """
    Validate a directory structure against a schema.

    Exit codes: [green]0[/] valid, [red]1[/] validation failed, [red]2[/] invalid schema/arguments.
    """
    from katachi.validation.validators import SchemaValidator

    context = None
    if context_json:
        try:
            context = json.loads(context_json)
        except json.JSONDecodeError as e:
            raise _fail(f"Invalid JSON in --context: {e}") from e
        if not isinstance(context, dict):
            raise _fail("--context must be a JSON object")

    for plugin in plugins or []:
        try:
            load_plugin(plugin)
        except PluginError as e:
            raise _fail(str(e), "Plugin error") from e

    try:
        schema = load_schema_or_raise(schema_path, target_path)
        target_fs, target = get_filesystem(target_path)
    except (SchemaError, ValueError) as e:
        raise _fail(str(e), "Schema error" if isinstance(e, SchemaError) else "Error") from e

    fmt = output_format.value
    rich_output = fmt == "rich"
    if rich_output:
        console.print(f"Validating [bold cyan]{target_path}[/] against [bold cyan]{schema_path}[/]")

    start = time.perf_counter()
    try:
        report = SchemaValidator.validate_schema(
            schema,
            target,
            target_fs,
            execute_actions=execute_actions,
            context=context,
            ignore=ignore or (),
            workers=workers,
        )
    except Exception as e:  # e.g. authentication or network errors from remote filesystems
        logger.opt(exception=e).debug("Validation aborted")
        raise _fail(f"Validation aborted: {type(e).__name__}: {e}\n(run with -v for details)") from e
    elapsed = time.perf_counter() - start
    report.sort_by_path()

    if rich_output:
        display_validation_results(report, detail_report, report_length, elapsed, out=console)
    elif fmt == "json":
        typer.echo(report_to_json(report, elapsed))
    elif fmt == "github":
        typer.echo(report_to_github(report))
    else:
        typer.echo(report_to_text(report, elapsed))

    failed_actions = [a for a in report.action_results if not a.success]
    if not report.is_valid() or (strict and report.warnings) or failed_actions:
        raise typer.Exit(EXIT_INVALID)


@app.command()
def describe(
    schema_path: Annotated[str, typer.Argument(help="Schema file (local path or fsspec URL).")],
    target_path: Annotated[str | None, typer.Argument(help="Unused, kept for backwards compatibility.")] = None,
) -> None:
    """Check a schema file and show it as a tree."""
    try:
        schema = load_schema_or_raise(schema_path, target_path)
    except SchemaError as e:
        raise _fail(str(e), "Schema error") from e
    console.print(Panel(create_schema_tree(schema), title=f"Schema: {schema_path}", border_style="blue", expand=False))


@app.command("check-schema")
def check_schema(
    schema_paths: Annotated[list[str], typer.Argument(help="Schema files to check (local paths or fsspec URLs).")],
) -> None:
    """Check schema files for errors (exit code 1 if any is invalid). Used by the pre-commit hook."""
    failed = False
    for schema_path in schema_paths:
        try:
            load_schema_or_raise(schema_path)
        except SchemaError as e:
            failed = True
            err_console.print(f"[red]✗[/] {schema_path}: {e}")
        else:
            console.print(f"[green]✓[/] {schema_path}")
    if failed:
        raise typer.Exit(EXIT_INVALID)


@app.command()
def infer(
    target_path: Annotated[str, typer.Argument(help="Directory to infer a schema from (local path or fsspec URL).")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write the schema to this file instead of stdout.")
    ] = None,
    max_depth: Annotated[int, typer.Option("--max-depth", help="Maximum depth to describe.")] = 16,
    include_hidden: Annotated[
        bool, typer.Option("--include-hidden", help="Describe hidden entries instead of ignoring them.")
    ] = False,
) -> None:
    """Generate a schema from an existing directory (a starting point to review and tighten)."""
    from katachi.schema.infer import dump_schema, infer_schema

    try:
        fs, path = get_filesystem(target_path)
        text = dump_schema(infer_schema(fs, path, max_depth=max_depth, include_hidden=include_hidden))
    except (ValueError, FileNotFoundError) as e:
        raise _fail(str(e)) from e
    if output:
        output.write_text(text)
        err_console.print(f"Wrote schema to [bold cyan]{output}[/]")
    else:
        typer.echo(text, nl=False)


@app.command()
def init(
    template: Annotated[Template, typer.Option("--template", "-t", help="Template to start from.")] = Template.BASIC,
    output: Annotated[Path, typer.Option("--output", "-o", help="File to create.")] = Path("katachi.yaml"),
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing file.")] = False,
    list_templates: Annotated[bool, typer.Option("--list", help="List available templates.")] = False,
) -> None:
    """Create a starter schema from a template (basic, yolo, imagefolder, cookiecutter-data-science)."""
    if list_templates:
        for name in Template:
            typer.echo(name.value)
        return
    if output.exists() and not force:
        raise _fail(f"{output} already exists (use --force to overwrite)")
    text = resources.files("katachi.templates").joinpath(f"{template.value}.yaml").read_text()
    output.write_text(text)
    err_console.print(
        f"Created [bold cyan]{output}[/] from the '{template}' template. Next: katachi validate {output} <dir>"
    )


@app.command("json-schema")
def json_schema() -> None:
    """Print the JSON Schema of Katachi schema files (for editor completion)."""
    from katachi.schema.json_schema import build_json_schema

    typer.echo(json.dumps(build_json_schema(), indent=2))


if __name__ == "__main__":
    app()


TEMPLATES = tuple(t.value for t in Template)
