from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from katachi.schema.actions import ActionRegistry
from katachi.schema.importer import parse_schema
from katachi.utils.fs_utils import get_filesystem
from katachi.validation.core import ValidationReport, ValidatorRegistry
from katachi.validation.predicates import PredicateRegistry
from katachi.validation.validators import SchemaValidator


@pytest.fixture(autouse=True)
def _isolate_registries() -> Iterator[None]:
    """Registries are global: snapshot them so tests can't leak actions/validators/predicates."""
    actions = dict(ActionRegistry._actions)
    validators = dict(ValidatorRegistry._validators)
    predicates = dict(PredicateRegistry._predicates)
    yield
    ActionRegistry._actions.clear()
    ActionRegistry._actions.update(actions)
    ValidatorRegistry._validators.clear()
    ValidatorRegistry._validators.update(validators)
    PredicateRegistry._predicates.clear()
    PredicateRegistry._predicates.update(predicates)


def make_tree(root: Path, entries: Iterable[str], content: bytes = b"") -> Path:
    """Create files/directories below ``root``; entries ending with ``/`` are directories."""
    root.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        path = root / entry
        if entry.endswith("/"):
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    return root


def run_validation(schema: str | dict[str, Any], root: str | Path, **kwargs: Any) -> ValidationReport:
    """Validate ``root`` against a schema given as YAML text or a dict."""
    data = yaml.safe_load(schema) if isinstance(schema, str) else schema
    fs, path = get_filesystem(str(root))
    return SchemaValidator.validate_schema(parse_schema(data, path), path, fs, **kwargs)


def messages(report: ValidationReport) -> list[str]:
    return [r.message for r in report.failures]


def rules(report: ValidationReport) -> list[str]:
    return sorted(r.validator_name for r in report.failures)


@pytest.fixture
def tree(tmp_path: Path) -> Callable[..., Path]:
    """``tree("a.jpg", "sub/")`` creates the entries in a fresh directory and returns it."""

    counter = iter(range(1_000_000))

    def factory(*entries: str, content: bytes = b"") -> Path:
        # A fresh directory named "root" per call, so trees never leak between calls
        return make_tree(tmp_path / f"tree{next(counter)}" / "root", entries, content)

    return factory
