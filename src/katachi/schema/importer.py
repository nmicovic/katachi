"""
Loading and parsing of YAML schema files.

Parsing is strict: unknown keys, invalid types and broken regular expressions are
reported as a :class:`SchemaError` pointing at the offending location in the schema,
e.g. ``root.children[1] (images): unknown key 'patern_name' (did you mean 'pattern_name'?)``.
"""

from __future__ import annotations

import re
from difflib import get_close_matches
from typing import Any

import yaml
from fsspec import AbstractFileSystem

from katachi.schema.schema_node import (
    NAME_CASES,
    PLACEHOLDER,
    SEVERITIES,
    SchemaDirectory,
    SchemaFile,
    SchemaNode,
    SchemaPredicateNode,
    template_to_regex,
)
from katachi.utils.logger import logger

NODE_TYPES = ("directory", "file", "predicate")

_COMMON_KEYS = {"type", "semantical_name", "description", "metadata", "severity"}
_ENTRY_KEYS = _COMMON_KEYS | {
    "pattern_name",
    "name_case",
    "permissions",
    "owner",
    "required",
    "min_count",
    "max_count",
}
ALLOWED_KEYS: dict[str, set[str]] = {
    "file": _ENTRY_KEYS | {"extension", "min_size", "max_size"},
    "directory": _ENTRY_KEYS | {"children", "ignore", "allow_extra"},
    # permissions/owner are accepted (and ignored) on predicates for backwards compatibility
    "predicate": _COMMON_KEYS | {"predicate_type", "elements", "options", "permissions", "owner"},
}


class SchemaError(ValueError):
    """Raised when a schema file cannot be loaded or is invalid."""

    def __init__(self, message: str, location: str | None = None):
        self.location = location
        self.reason = message
        super().__init__(f"{location}: {message}" if location else message)


def _suggest(key: str, options: set[str]) -> str:
    matches = get_close_matches(key, sorted(options), n=1)
    return f" (did you mean '{matches[0]}'?)" if matches else ""


def _get_bool(data: dict[str, Any], key: str, location: str, default: bool = False) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise SchemaError(f"'{key}' must be true or false, got {value!r}", location)
    return value


def _get_int(data: dict[str, Any], key: str, location: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SchemaError(f"'{key}' must be a non-negative integer, got {value!r}", location)
    return int(value)


def _get_str(data: dict[str, Any], key: str, location: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, int | float) and not isinstance(value, bool):
        return str(value)
    if not isinstance(value, str):
        raise SchemaError(f"'{key}' must be a string, got {value!r}", location)
    return value


def _get_str_list(data: dict[str, Any], key: str, location: str) -> list[str]:
    value = data.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise SchemaError(f"'{key}' must be a string or a list of strings, got {value!r}", location)
    return value


def _get_pattern(data: dict[str, Any], location: str, available_vars: set[str]) -> tuple[str | None, set[str]]:
    """Validate ``pattern_name`` and return it with the named groups it captures."""
    pattern = _get_str(data, "pattern_name", location)
    if pattern is None:
        return None, set()
    try:
        compiled = re.compile(template_to_regex(pattern))
    except re.error as e:
        raise SchemaError(f"invalid regular expression in 'pattern_name' {pattern!r}: {e}", location) from e
    for var in PLACEHOLDER.findall(pattern):
        if var not in available_vars:
            known = f" (captured names available here: {', '.join(sorted(available_vars))})" if available_vars else ""
            raise SchemaError(
                f"pattern_name {pattern!r} uses '{{{var}}}' but no parent pattern captures a group named "
                f"'{var}'; define it with (?P<{var}>...) in an ancestor's pattern_name{known}",
                location,
            )
    return pattern, set(compiled.groupindex)


def _get_choice(data: dict[str, Any], key: str, choices: tuple[str, ...], location: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if value not in choices:
        raise SchemaError(
            f"invalid {key} {value!r}, expected one of: {', '.join(choices)}{_suggest(str(value), set(choices))}",
            location,
        )
    return str(value)


def _get_permissions(data: dict[str, Any], location: str) -> str | None:
    value = data.get("permissions")
    if value is None:
        return None
    if not isinstance(value, str):
        # YAML reads an unquoted 0644 as the integer 420, so an unquoted value is ambiguous
        raise SchemaError(
            f"'permissions' must be a quoted octal string like \"0750\", got {value!r} (quote the value in YAML)",
            location,
        )
    if not re.fullmatch(r"(0o|0)?[0-7]{3}", value):
        raise SchemaError(f"'permissions' must be an octal string like \"0750\", got {value!r}", location)
    return value


def parse_node(
    node_data: Any,
    parent_path: str,
    is_root: bool = False,
    location: str = "",
    available_vars: set[str] | None = None,
) -> SchemaNode:
    """
    Recursively parse a node from YAML data.

    Args:
        node_data: Dictionary containing the node data from YAML
        parent_path: Path to the parent directory
        is_root: Whether this node is the root node of the schema
        location: Human readable location of this node in the schema, e.g. ``dataset > children[1]``
        available_vars: Named groups captured by ancestor patterns (usable as ``{name}`` placeholders)

    Returns:
        SchemaNode representing this node and its children

    Raises:
        SchemaError: If the node data is invalid
    """
    location = location or "root"
    if not isinstance(node_data, dict):
        raise SchemaError(
            f"expected a mapping describing a node, got {type(node_data).__name__}: {node_data!r}", location
        )

    semantical_name = node_data.get("semantical_name")
    if semantical_name is None:
        if not is_root:
            raise SchemaError("missing required key 'semantical_name'", location)
        semantical_name = "root"
    if not isinstance(semantical_name, str) or not semantical_name:
        raise SchemaError(f"'semantical_name' must be a non-empty string, got {semantical_name!r}", location)
    location = f"{location.rsplit(' > ', 1)[0]} > {semantical_name}" if " > " in location else semantical_name

    raw_type = node_data.get("type")
    if raw_type is None:
        raise SchemaError(f"missing required key 'type' (one of: {', '.join(NODE_TYPES)})", location)
    node_type = str(raw_type).lower()
    if node_type not in NODE_TYPES:
        raise SchemaError(
            f"invalid node type {raw_type!r}, expected one of: {', '.join(NODE_TYPES)}{_suggest(node_type, set(NODE_TYPES))}",
            location,
        )

    allowed = ALLOWED_KEYS[node_type]
    for key in node_data:
        if key not in allowed:
            raise SchemaError(f"unknown key '{key}' for a {node_type} node{_suggest(str(key), allowed)}", location)

    description = _get_str(node_data, "description", location)
    metadata = node_data.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise SchemaError(f"'metadata' must be a mapping, got {metadata!r}", location)

    # For root node, use parent_path directly instead of appending the name
    node_path = parent_path if is_root else f"{parent_path}/{semantical_name}"

    severity = _get_choice(node_data, "severity", SEVERITIES, location) or "error"
    if node_type == "predicate":
        predicate = _parse_predicate(node_data, node_path, semantical_name, description, metadata, location)
        predicate.severity = severity
        return predicate

    available_vars = set(available_vars or ())
    pattern, captured = _get_pattern(node_data, location, available_vars)
    common: dict[str, Any] = {
        "path": node_path,
        "semantical_name": semantical_name,
        "description": description,
        "pattern_validation": pattern,
        "severity": severity,
        "name_case": _get_choice(node_data, "name_case", tuple(NAME_CASES), location),
        "metadata": metadata,
        "permissions": _get_permissions(node_data, location),
        "owner": _get_str(node_data, "owner", location),
        "required": _get_bool(node_data, "required", location),
        "min_count": _get_int(node_data, "min_count", location),
        "max_count": _get_int(node_data, "max_count", location),
    }
    if (
        common["min_count"] is not None
        and common["max_count"] is not None
        and common["min_count"] > common["max_count"]
    ):
        raise SchemaError(
            f"'min_count' ({common['min_count']}) is greater than 'max_count' ({common['max_count']})", location
        )

    if node_type == "file":
        file_node = SchemaFile(
            extension=_get_str_list(node_data, "extension", location),
            min_size=_get_int(node_data, "min_size", location),
            max_size=_get_int(node_data, "max_size", location),
            **common,
        )
        if (
            file_node.min_size is not None
            and file_node.max_size is not None
            and file_node.min_size > file_node.max_size
        ):
            raise SchemaError("'min_size' is greater than 'max_size'", location)
        return file_node

    directory = SchemaDirectory(
        ignore=_get_str_list(node_data, "ignore", location),
        allow_extra=_get_bool(node_data, "allow_extra", location),
        **common,
    )
    children = node_data.get("children") or []
    if not isinstance(children, list):
        raise SchemaError(f"'children' must be a list of nodes, got {type(children).__name__}", location)
    for index, child_data in enumerate(children):
        directory.add_child(
            parse_node(
                child_data,
                node_path,
                location=f"{location} > children[{index}]",
                available_vars=available_vars | captured,
            )
        )

    _check_predicate_elements(directory, location)
    return directory


def _parse_predicate(
    node_data: dict[str, Any],
    node_path: str,
    semantical_name: str,
    description: str | None,
    metadata: dict[str, Any] | None,
    location: str,
) -> SchemaPredicateNode:
    predicate_type = _get_str(node_data, "predicate_type", location)
    if not predicate_type:
        raise SchemaError("predicate node is missing required key 'predicate_type'", location)
    elements = node_data.get("elements")
    if not elements or not isinstance(elements, list) or not all(isinstance(e, str) for e in elements):
        raise SchemaError("predicate node needs a non-empty 'elements' list of semantical names", location)
    options = node_data.get("options")
    if options is not None and not isinstance(options, dict):
        raise SchemaError(f"'options' must be a mapping, got {options!r}", location)
    return SchemaPredicateNode(
        path=node_path,
        semantical_name=semantical_name,
        predicate_type=predicate_type,
        elements=elements,
        description=description,
        metadata=metadata,
        options=options,
    )


def _check_predicate_elements(directory: SchemaDirectory, location: str) -> None:
    """Make sure every predicate only references nodes declared below the directory it lives in."""
    if not directory.predicates:
        return
    names = {n.semantical_name for n in directory.iter_nodes() if not isinstance(n, SchemaPredicateNode)}
    names.discard(directory.semantical_name)
    for predicate in directory.predicates:
        for element in predicate.elements:
            if element not in names:
                raise SchemaError(
                    f"predicate '{predicate.semantical_name}' references unknown element '{element}'"
                    f"{_suggest(element, names)}; elements must be declared inside the same directory",
                    location,
                )


def parse_schema(data: Any, target_path: str = "") -> SchemaNode:
    """
    Parse an already loaded schema document (e.g. a dict from YAML/JSON).

    Args:
        data: Schema document
        target_path: Path of the directory the schema will be validated against

    Raises:
        SchemaError: If the schema is invalid
    """
    if data is None:
        raise SchemaError("schema is empty")
    return parse_node(data, target_path, is_root=True)


def load_schema_file(
    schema_path: str, schema_fs: AbstractFileSystem | None = None, target_path: str = ""
) -> SchemaNode:
    """
    Load and parse a YAML schema file.

    Args:
        schema_path: Path to the YAML schema file
        schema_fs: Filesystem holding the schema (local filesystem by default)
        target_path: Path of the directory the schema will be validated against

    Raises:
        SchemaError: If the file does not exist, is not valid YAML or describes an invalid schema
    """
    if schema_fs is None:
        from fsspec.implementations.local import LocalFileSystem

        schema_fs = LocalFileSystem()
    try:
        with schema_fs.open(schema_path, "rb") as file:
            content = file.read()
    except FileNotFoundError as e:
        raise SchemaError(f"schema file not found: {schema_path}") from e
    except OSError as e:
        raise SchemaError(f"could not read schema file {schema_path}: {e}") from e

    if not content.strip():
        raise SchemaError(f"schema file is empty: {schema_path}")
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise SchemaError(f"invalid YAML in {schema_path}: {e}") from e
    return parse_schema(data, target_path)


def load_yaml(
    schema_path: str,
    target_path: str,
    schema_fs: AbstractFileSystem,
    target_fs: AbstractFileSystem | None = None,
) -> SchemaNode | None:
    """
    Load a YAML schema file and return a SchemaNode tree structure.

    Args:
        schema_path: Path to the YAML schema file
        target_path: Path to the directory that will be validated against the schema
        schema_fs: Filesystem to use for schema file
        target_fs: Unused, kept for backwards compatibility

    Returns:
        The root SchemaNode representing the schema hierarchy, or None when loading failed
        (the reason is logged). Use :func:`load_schema_file` to get the error as an exception.
    """
    try:
        return load_schema_file(schema_path, schema_fs, target_path)
    except SchemaError as e:
        logger.error(str(e))
        return None
