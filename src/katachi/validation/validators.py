from pathlib import Path

from katachi.schema.schema_node import SchemaDirectory, SchemaFile, SchemaNode
from katachi.validation.core import ValidationReport, ValidationResult


class SchemaValidator:
    """Validator for schema nodes against filesystem paths."""

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
