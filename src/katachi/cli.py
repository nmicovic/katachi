from pathlib import Path

import typer

from katachi.schema.importer import load_yaml
from katachi.schema.validate import validate_schema

app = typer.Typer(no_args_is_help=True)


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
    typer.echo(f"Describing schema {schema_path} for directory {target_path}")

    try:
        # Load the schema
        schema = load_yaml(schema_path, target_path)
        typer.echo(typer.style("Schema description:", fg=typer.colors.BLUE, bold=True))
        typer.echo(str(schema))
    except Exception as e:
        typer.echo(typer.style(f"❌ Failed to describe schema: {e!s}", fg=typer.colors.RED, bold=True))


@app.command()
def validate(schema_path: Path, target_path: Path) -> None:
    """
    Validates a directory structure against a schema.yaml file.

    Args:
        schema_path: Path to the schema.yaml file
        target_path: Path to the directory to validate

    Returns:
        True if validation was successful, False otherwise
    """
    typer.echo(f"Validating schema {schema_path} against directory {target_path}")

    # Load the schema
    schema = load_yaml(schema_path, target_path)

    if schema is None:
        typer.echo(typer.style("❌ Failed to load schema!", fg=typer.colors.RED, bold=True))
        return

    # Validate the directory structure against the schema
    status = validate_schema(schema, target_path)

    if status:
        typer.echo(typer.style("✅ Validation successful!", fg=typer.colors.GREEN, bold=True))
    else:
        typer.echo(typer.style("❌ Validation failed!", fg=typer.colors.RED, bold=True))


if __name__ == "__main__":
    app()
