"""
JSON Schema describing Katachi schema files, for editor completion and validation.

Add this modeline at the top of a schema file (VS Code YAML extension, JetBrains, Neovim)::

    # yaml-language-server: $schema=https://raw.githubusercontent.com/nmicovic/katachi/main/katachi.schema.json

The committed ``katachi.schema.json`` at the repository root is generated with
``katachi json-schema > katachi.schema.json`` (a test checks it is up to date).
"""

from __future__ import annotations

from typing import Any

from katachi.schema.schema_node import NAME_CASES, SEVERITIES

_STR = {"type": "string"}
_COUNT = {"type": "integer", "minimum": 0}
_STR_OR_LIST = {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]}

PROPERTIES: dict[str, dict[str, Any]] = {
    "semantical_name": {**_STR, "description": "Name of this node in the schema (used by predicates and actions)."},
    "type": {"enum": ["directory", "file", "predicate"], "description": "Kind of node."},
    "description": {**_STR, "description": "Human readable description, shown by `katachi describe`."},
    "metadata": {"type": "object", "description": "Free-form data available to custom validators and actions."},
    "severity": {
        "enum": list(SEVERITIES),
        "description": "Severity of count/predicate violations of this node. Only errors fail validation.",
    },
    "pattern_name": {
        **_STR,
        "description": (
            "Regular expression the whole name must match (for files: the name without extension). "
            "Named groups (?P<id>...) can be referenced as {id} in descendant patterns."
        ),
    },
    "name_case": {"enum": list(NAME_CASES), "description": "Naming convention the name must follow."},
    "permissions": {
        **_STR,
        "pattern": "^(0o)?[0-7]{3,4}$",
        "description": 'Octal permissions, e.g. "0750". Special bits are only compared when given ("2775").',
    },
    "owner": {**_STR, "description": "Expected owner (user name or numeric uid)."},
    "required": {"type": "boolean", "description": "At least one matching entry must exist (same as min_count: 1)."},
    "min_count": {**_COUNT, "description": "Minimum number of matching entries in each parent directory."},
    "max_count": {**_COUNT, "description": "Maximum number of matching entries in each parent directory."},
    "extension": {**_STR_OR_LIST, "description": 'Accepted extension(s), e.g. ".jpg" or [".jpg", ".png"].'},
    "min_size": {**_COUNT, "description": "Minimum file size in bytes."},
    "max_size": {**_COUNT, "description": "Maximum file size in bytes."},
    "children": {"type": "array", "items": {"$ref": "#/$defs/node"}, "description": "Entries of this directory."},
    "ignore": {**_STR_OR_LIST, "description": "Glob patterns of entry names to skip in this directory."},
    "allow_extra": {"type": "boolean", "description": "Allow entries that match none of the children."},
    "predicate_type": {
        **_STR,
        "description": "Predicate to evaluate: pair_comparison, count_match, unique_keys or a registered one.",
        "examples": ["pair_comparison", "count_match", "unique_keys"],
    },
    "elements": {
        "type": "array",
        "items": _STR,
        "minItems": 1,
        "description": "Semantical names of the nodes the predicate relates.",
    },
    "options": {
        "type": "object",
        "description": "Predicate options that control how entries are paired up.",
        "properties": {
            "key": {**_STR, "description": 'Key template, e.g. "{split}/{stem}" (captures, {stem}, {name}).'},
            "key_pattern": {**_STR, "description": "Regex extracting the key from the name (group 'key' or 1)."},
        },
    },
}


def build_json_schema(allowed_keys: dict[str, set[str]] | None = None) -> dict[str, Any]:
    """Build the JSON Schema for Katachi schema files."""
    if allowed_keys is None:
        from katachi.schema.importer import ALLOWED_KEYS

        allowed_keys = ALLOWED_KEYS

    def variant(node_type: str, required: list[str]) -> dict[str, Any]:
        keys = sorted(allowed_keys[node_type], key=list(PROPERTIES).index)
        props = {k: PROPERTIES[k] for k in keys}
        props["type"] = {"const": node_type, "description": PROPERTIES["type"]["description"]}
        return {
            "type": "object",
            "if": {"properties": {"type": {"const": node_type}}, "required": ["type"]},
            "then": {"properties": props, "required": required, "additionalProperties": False},
        }

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://raw.githubusercontent.com/nmicovic/katachi/main/katachi.schema.json",
        "title": "Katachi schema",
        "description": "Describes the expected structure of a directory tree, validated with `katachi validate`.",
        "$ref": "#/$defs/node",
        "$defs": {
            "node": {
                "type": "object",
                "required": ["type"],
                "properties": {"type": PROPERTIES["type"]},
                "allOf": [
                    variant("directory", ["type"]),
                    variant("file", ["type"]),
                    variant("predicate", ["type", "predicate_type", "elements"]),
                ],
            }
        },
    }
