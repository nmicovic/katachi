from pathlib import Path
from typing import Any, Optional

from katachi.schema.actions import NodeContext, process_node
from katachi.schema.schema_node import SchemaDirectory, SchemaFile, SchemaNode
from katachi.validation.core import ValidationReport, ValidationResult, ValidatorRegistry


class SchemaValidator:
    """Validator for schema nodes against filesystem paths."""

    @staticmethod
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

            # Add current node to parent contexts before processing children
            parent_contexts.append((schema, target_path))

            for child_path in child_paths:
                child_valid = False
                child_reports: list[ValidationReport] = []

                for child in schema.children:
                    child_report = SchemaValidator.validate_schema(
                        child, child_path, execute_actions, parent_contexts, context
                    )
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

    @staticmethod
    def validate_node(node: SchemaNode, path: Path) -> ValidationReport:
        """
        Validate a path against a schema node.

        Args:
            node: Schema node to validate against
            path: Path to validate

        Returns:
            ValidationReport with results
        """
        if isinstance(node, SchemaFile):
            return SchemaValidator.validate_file(node, path)
        elif isinstance(node, SchemaDirectory):
            return SchemaValidator.validate_directory(node, path)
        else:
            report = ValidationReport()
            report.add_result(
                ValidationResult(
                    is_valid=False,
                    message=f"Unknown schema node type: {type(node).__name__}",
                    path=path,
                    validator_name="schema_type",
                )
            )
            return report

    @staticmethod
    def validate_file(file_node: SchemaFile, path: Path) -> ValidationReport:
        """Validate a path against a file schema."""
        report = ValidationReport()
        context = {"node_name": file_node.semantical_name}

        # Check if it's a file
        is_file = path.is_file()
        report.add_result(
            ValidationResult(
                is_valid=is_file,
                message="" if is_file else f"Expected a file at {path}",
                path=path,
                validator_name="is_file",
                context=context,
            )
        )

        # If not a file, stop further validations
        if not is_file:
            return report

        # Check extension
        if file_node.extension:
            ext = file_node.extension if file_node.extension.startswith(".") else f".{file_node.extension}"
            has_ext = path.suffix == ext
            report.add_result(
                ValidationResult(
                    is_valid=has_ext,
                    message="" if has_ext else f'Expected extension "{ext}", got "{path.suffix}"',
                    path=path,
                    validator_name="extension",
                    context=context,
                )
            )

        # Check pattern
        if file_node.pattern_validation:
            matches_pattern = file_node.pattern_validation.fullmatch(path.stem) is not None
            report.add_result(
                ValidationResult(
                    is_valid=matches_pattern,
                    message=""
                    if matches_pattern
                    else f'{path.name} doesn\'t match pattern "{file_node.pattern_validation.pattern}"',
                    path=path,
                    validator_name="pattern",
                    context=context,
                )
            )

        return report

    @staticmethod
    def validate_directory(dir_node: SchemaDirectory, path: Path) -> ValidationReport:
        """Validate a path against a directory schema."""
        report = ValidationReport()
        context = {"node_name": dir_node.semantical_name}

        # Check if it's a directory
        is_dir = path.is_dir()
        report.add_result(
            ValidationResult(
                is_valid=is_dir,
                message="" if is_dir else f"Expected a directory at {path}",
                path=path,
                validator_name="is_directory",
                context=context,
            )
        )

        # If not a directory, stop further validations
        if not is_dir:
            return report

        # Check pattern
        if dir_node.pattern_validation:
            matches_pattern = dir_node.pattern_validation.fullmatch(path.name) is not None
            report.add_result(
                ValidationResult(
                    is_valid=matches_pattern,
                    message=""
                    if matches_pattern
                    else f'{path.name} doesn\'t match pattern "{dir_node.pattern_validation.pattern}"',
                    path=path,
                    validator_name="pattern",
                    context=context,
                )
            )

        return report
