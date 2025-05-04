import logging
from pathlib import Path
from typing import Any, Optional

from katachi.schema.actions import NodeContext, process_node
from katachi.schema.schema_node import SchemaDirectory, SchemaNode
from katachi.validation.core import ValidationReport, ValidatorRegistry
from katachi.validation.validators import SchemaValidator


def validate_schema(
    schema: SchemaNode,
    target_path: Path,
    execute_actions: bool = False,
    parent_contexts: Optional[list[NodeContext]] = None,
    context: Optional[dict[str, Any]] = None,
) -> ValidationReport:
    """
    Validate a target path against a schema node recursively.

    Args:
        schema: Schema node to validate against
        target_path: Path to validate
        execute_actions: Whether to execute registered actions
        parent_contexts: List of parent (node, path) tuples for context
        context: Additional context data

    Returns:
        ValidationReport with all validation results
    """
    # Initialize parent_contexts and context if needed
    parent_contexts = parent_contexts or []
    context = context or {}

    logging.debug(f"[schema_parse] <{schema.semantical_name}> @ {target_path}")

    # Create a report to collect validation results
    report = ValidationReport()

    # Run standard validation for this node
    node_report = SchemaValidator.validate_node(schema, target_path)
    report.add_results(node_report.results)

    # Run any custom validators
    custom_results = ValidatorRegistry.run_validators(schema, target_path)
    report.add_results(custom_results)

    # Early return if basic validation fails
    if not node_report.is_valid():
        return report

    # Execute actions for this node if validation passed and actions are enabled
    if execute_actions:
        process_node(schema, target_path, parent_contexts, context)

    # For directories, validate children
    if isinstance(schema, SchemaDirectory) and target_path.is_dir():
        child_paths = list(target_path.iterdir())
        logging.debug(f"[schema_parse] child_paths: {child_paths}")

        # Add current node to parent contexts before processing children
        parent_contexts.append((schema, target_path))

        for child_path in child_paths:
            child_valid = False
            child_reports: list[ValidationReport] = []

            for child in schema.children:
                child_report = validate_schema(child, child_path, execute_actions, parent_contexts, context)
                child_reports.append(child_report)

                if child_report.is_valid():
                    child_valid = True
                    report.add_results(child_report.results)
                    break

            if not child_valid:
                for child_report in child_reports:
                    report.add_results(child_report.results)

        # Remove current node from parent contexts after processing all children
        parent_contexts.pop()

    return report


def format_validation_results(report: ValidationReport) -> str:
    """Format validation results into a user-friendly message."""
    return report.format_report()
