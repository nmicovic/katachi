from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar

from katachi.schema.schema_node import SchemaNode

ValidatorFunc = Callable[[SchemaNode, str], list["ValidationResult"]]


@dataclass
class ValidationResult:
    """Result of a validation check with detailed information."""

    is_valid: bool
    message: str
    path: str
    validator_name: str
    node_origin: str
    context: dict[str, Any] | None = None
    #: "error" results make validation fail; "warning" and "info" results are only reported
    severity: str = "error"

    @property
    def is_error(self) -> bool:
        """Whether this is a failed result with error severity."""
        return not self.is_valid and self.severity == "error"

    @property
    def is_warning(self) -> bool:
        """Whether this is a failed result with a non-error severity."""
        return not self.is_valid and self.severity != "error"

    def __bool__(self) -> bool:
        """Allow using validation result in boolean contexts."""
        return self.is_valid

    def to_dict(self) -> dict[str, Any]:
        """Convert the result to a JSON serializable dictionary."""
        data = asdict(self)
        if data["context"] is None:
            del data["context"]
        return data


@dataclass
class ValidationStats:
    """Counters collected while validating a directory tree."""

    entries_checked: int = 0
    directories_listed: int = 0
    matches: Counter = field(default_factory=Counter)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries_checked": self.entries_checked,
            "directories_listed": self.directories_listed,
            "matches": dict(self.matches),
        }


class ValidationReport:
    """Report containing multiple validation results."""

    def __init__(self) -> None:
        """Initialize an empty validation report."""
        self.results: list[ValidationResult] = []
        self.context: dict[str, Any] = {}
        self.stats: ValidationStats = ValidationStats()
        self.root_path: str | None = None

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
            True if no result is an error (warnings are allowed), False otherwise
        """
        return not any(result.is_error for result in self.results)

    @property
    def failures(self) -> list[ValidationResult]:
        """All failed validation results with error severity."""
        return [r for r in self.results if r.is_error]

    @property
    def warnings(self) -> list[ValidationResult]:
        """All failed validation results with warning/info severity."""
        return [r for r in self.results if r.is_warning]

    @property
    def action_results(self) -> list[Any]:
        """Results of executed actions (empty when actions were not executed)."""
        return list(self.context.get("action_results", []))

    @property
    def predicates_skipped(self) -> bool:
        """Whether predicates were not evaluated because the structure is invalid."""
        return bool(self.context.get("predicates_skipped"))

    def sort_by_longest_path(self) -> None:
        """Sort results by path length (longest first)."""
        self.results.sort(key=lambda r: len(r.path), reverse=True)

    def sort_by_path(self) -> None:
        """Sort results by path, failures of the same path keep their relative order."""
        self.results.sort(key=lambda r: r.path)

    def to_dict(self) -> dict[str, Any]:
        """Convert the report to a JSON serializable dictionary."""
        return {
            "valid": self.is_valid(),
            "root": self.root_path,
            "failure_count": len(self.failures),
            "warning_count": len(self.warnings),
            "predicates_skipped": self.predicates_skipped,
            "stats": self.stats.to_dict(),
            "results": [r.to_dict() for r in self.results],
            "actions": [a.to_dict() for a in self.action_results],
        }

    def __str__(self) -> str:
        """String representation of the validation report."""
        return f"ValidationReport with {len(self.results)} results ({len(self.failures)} failures)"


class ValidatorRegistry:
    """
    Registry for custom validators.

    A validator receives the schema node and the path of an entry that already passed
    the built-in checks for that node, and returns a list of results. Returning a failed
    result makes the entry not match the node.
    """

    _validators: ClassVar[dict[str, ValidatorFunc]] = {}

    @classmethod
    def register(cls, name: str, func: ValidatorFunc | None = None) -> Callable:
        """
        Register a validator function, either as a decorator or directly.

        Example::

            @ValidatorRegistry.register("my_check")
            def my_check(node, path):
                return []

            ValidatorRegistry.register("other_check", my_check)

        Args:
            name: Name of the validator
            func: Validator function, when not used as a decorator

        Returns:
            Decorator function (or the registered function when ``func`` is given)
        """

        def decorator(f: ValidatorFunc) -> ValidatorFunc:
            cls._validators[name] = f
            return f

        if func is not None:
            return decorator(func)
        return decorator

    @classmethod
    def unregister(cls, name: str) -> None:
        """Remove a registered validator (no-op if it does not exist)."""
        cls._validators.pop(name, None)

    @classmethod
    def clear(cls) -> None:
        """Remove all registered validators."""
        cls._validators.clear()

    @classmethod
    def names(cls) -> list[str]:
        """Names of all registered validators."""
        return list(cls._validators)

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
                results.extend(validator_results or [])
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
