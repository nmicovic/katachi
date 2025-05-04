from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, ClassVar, Optional

from katachi.schema.schema_node import SchemaNode


@dataclass
class ValidationResult:
    """Result of a validation check with detailed information."""

    is_valid: bool
    message: str
    path: Path
    validator_name: str
    context: Optional[dict[str, Any]] = None

    def __bool__(self) -> bool:
        """Allow using validation result in boolean contexts."""
        return self.is_valid


class ValidationReport:
    """Collection of validation results with formatted output."""

    def __init__(self) -> None:
        self.results: list[ValidationResult] = []

    def add_result(self, result: ValidationResult) -> None:
        self.results.append(result)

    def add_results(self, results: list[ValidationResult]) -> None:
        self.results.extend(results)

    def is_valid(self) -> bool:
        return all(result.is_valid for result in self.results)

    def format_report(self) -> str:
        """Format validation results into human-readable output."""
        if self.is_valid():
            return "All validations passed successfully!"

        failures = [r for r in self.results if not r.is_valid]
        report_lines = ["Validation failed with the following issues:"]

        for failure in failures:
            report_lines.append(f"❌ {failure.path}: {failure.message}")

        return "\n".join(report_lines)


class ValidatorRegistry:
    """Registry for custom validators."""

    # Dictionary of validator functions by name
    _validators: ClassVar[dict[str, Callable]] = {}

    @classmethod
    def register(cls, name: str, validator_func: Callable) -> None:
        """Register a new validator function."""
        cls._validators[name] = validator_func

    @classmethod
    def get_validator(cls, name: str) -> Optional[Callable]:
        """Get a registered validator function by name."""
        return cls._validators.get(name)

    @classmethod
    def run_validators(cls, node: SchemaNode, path: Path) -> list[ValidationResult]:
        """Run all registered validators for a given node and path."""
        results = []

        for name, validator_func in cls._validators.items():
            try:
                result = validator_func(node, path)
                if isinstance(result, ValidationResult):
                    results.append(result)
                elif isinstance(result, list):
                    results.extend([r for r in result if isinstance(r, ValidationResult)])
            except Exception as e:
                # Ensure validator failures don't crash the entire validation
                results.append(
                    ValidationResult(
                        is_valid=False,
                        message=f"Validator '{name}' failed with error: {e!s}",
                        path=path,
                        validator_name=name,
                    )
                )

        return results
