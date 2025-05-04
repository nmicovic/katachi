import logging
from pathlib import Path

from katachi.schema.schema_node import SchemaDirectory, SchemaNode
from katachi.validation.core import ValidationReport, ValidatorRegistry
from katachi.validation.validators import SchemaValidator


def validate_schema(schema: SchemaNode, target_path: Path) -> ValidationReport:
    """
    Validate a target path against a schema node recursively.

    Args:
        schema: Schema node to validate against
        target_path: Path to validate

    Returns:
        ValidationReport with all validation results
    """
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

    # For directories, validate children
    if isinstance(schema, SchemaDirectory) and target_path.is_dir():
        child_paths = list(target_path.iterdir())
        # logging.debug(f"[schema_parse] child_paths: {child_paths}")

        for child_path in child_paths:
            child_valid = False
            child_reports = []

            for child in schema.children:
                child_report = validate_schema(child, child_path)
                child_reports.append(child_report)

                # If we verified the child successfully, we can report the results and stop checking othe cchildren.
                if child_report.is_valid():
                    child_valid = True
                    report.add_results(child_report.results)
                    break

            # If we failed to validate a path with any child, we need to log the results of what we tried
            # for better undeerstanding of the failure. We may have tried multiple node childs for validation,
            # hence we must add all results as well.
            # This is important for the case where we have multiple children with different validation rules.
            if not child_valid:
                for child_report in child_reports:
                    for result in child_report.results:
                        report.add_result(result)

    return report


def format_validation_results(report: ValidationReport) -> str:
    """Format validation results into a user-friendly message."""
    return report.format_report()
