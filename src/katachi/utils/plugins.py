"""Loading user plugins (modules registering actions, validators and predicates)."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType


class PluginError(ImportError):
    """Raised when a plugin cannot be imported."""


def _load_file(path: Path) -> ModuleType:
    if not path.is_file():
        raise PluginError(f"Plugin file not found: {path}")
    module_name = f"katachi_plugin_{path.stem}"
    module_spec = importlib.util.spec_from_file_location(module_name, path)
    if module_spec is None or module_spec.loader is None:
        raise PluginError(f"Cannot import plugin file: {path}")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_name] = module
    try:
        module_spec.loader.exec_module(module)
    except Exception as e:
        del sys.modules[module_name]
        raise PluginError(f"Failed to load plugin '{path}': {type(e).__name__}: {e}") from e
    return module


def load_plugin(spec: str) -> ModuleType:
    """
    Import a plugin given as a Python file path (``checks/actions.py``) or a module name (``mypkg.actions``).

    Importing the module is enough: plugins register their actions, validators and predicates
    at import time with ``register_action`` / ``register_validator`` / ``register_predicate``.

    Raises:
        PluginError: If the plugin can't be found or raises while being imported
    """
    path = Path(spec)
    if path.suffix == ".py" or path.exists():
        return _load_file(path)
    try:
        return importlib.import_module(spec)
    except Exception as e:
        raise PluginError(f"Failed to load plugin '{spec}': {type(e).__name__}: {e}") from e
