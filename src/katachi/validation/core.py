from dataclasses import dataclass
from typing import Any, Callable, ClassVar, Optional

from katachi.schema.schema_node import SchemaNode


@dataclass
class ValidationResult:
    """Result of a validation check with detailed information."""

    is_valid: bool
    message: str
    path: str
    validator_name: str
    node_origin: str
    context: Optional[dict[str, Any]] = None

    def __bool__(self) -> bool:
        """Allow using validation result in boolean contexts."""
        return self.is_valid


class ValidationReport:
    """Report containing multiple validation results."""

    def __init__(self) -> None:
        """Initialize an empty validation report."""
        self.results: list[ValidationResult] = []
        self.context: dict[str, Any] = {}

    def add_result(self, result: ValidationResult) -> None:
        """
        Add a validation result to the report.

        Args:
            result: The validation result to add
        """
        self.results.append(result)

    def add_results(self, results: list[ValidationResult]) -> None:
        """
        Add multiple validation results to the report.

        Args:
            results: List of validation results to add
        """
        self.results.extend(results)

    def is_valid(self) -> bool:
        """
        Check if all validation results are valid.

        Returns:
            True if all results are valid, False otherwise
        """
        return all(result.is_valid for result in self.results)

    def sort_by_longest_path(self) -> None:
        """Sort results by path length (longest first)."""
        self.results.sort(key=lambda r: len(r.path), reverse=True)

    def __str__(self) -> str:
        """String representation of the validation report."""
        return f"ValidationReport with {len(self.results)} results"


class ValidatorRegistry:
    """Registry for custom validators."""

    _validators: ClassVar[dict[str, Callable[[SchemaNode, str], list[ValidationResult]]]] = {}

    @classmethod
    def register(cls, name: str) -> Callable:
        """
        Register a validator function.

        Args:
            name: Name of the validator

        Returns:
            Decorator function
        """

        def decorator(func: Callable[[SchemaNode, str], list[ValidationResult]]) -> Callable:
            cls._validators[name] = func
            return func

        return decorator

    @classmethod
    def run_validators(cls, node: SchemaNode, path: str) -> list[ValidationResult]:
        """
        Run all registered validators for a node.

        Args:
            node: Schema node to validate
            path: Path to validate

        Returns:
            List of validation results
        """
        results: list[ValidationResult] = []
        for validator_name, validator_func in cls._validators.items():
            try:
                validator_results = validator_func(node, path)
                results.extend(validator_results)
            except Exception as e:
                results.append(
                    ValidationResult(
                        is_valid=False,
                        message=f"Validator {validator_name} failed: {e!s}",
                        path=path,
                        validator_name=validator_name,
                        node_origin=node.semantical_name,
                    )
                )
        return results
