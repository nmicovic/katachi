"""
Actions module for Katachi.

This module provides functionality for registering and executing callbacks
when traversing the file system according to a schema.
"""

from pathlib import Path
from typing import Any, Callable, Optional

from katachi.schema.schema_node import SchemaNode

# Type definition for node context: tuple of (schema_node, path)
NodeContext = tuple[SchemaNode, Path]

# Type for action callbacks: current node, path, parent contexts, and additional context
ActionCallback = Callable[[SchemaNode, Path, list[NodeContext], dict[str, Any]], None]

# Registry of callbacks by semantic name
_action_registry: dict[str, ActionCallback] = {}


def register_action(semantical_name: str, callback: ActionCallback) -> None:
    """
    Register a callback for a specific schema node semantic name.

    Args:
        semantical_name: The semantic name to trigger the callback for
        callback: Function to call when traversing a node with this semantic name
    """
    _action_registry[semantical_name] = callback


def process_node(
    node: SchemaNode,
    path: Path,
    parent_contexts: list[NodeContext],
    context: Optional[dict[str, Any]] = None,
) -> None:
    """
    Process a node by running any registered callbacks for it.

    Args:
        node: Current schema node being processed
        path: Path being validated
        parent_contexts: List of parent (node, path) tuples
        context: Additional context data
    """
    context = context or {}

    # Check if there's a callback registered for this node's semantic name
    callback = _action_registry.get(node.semantical_name)
    if callback:
        callback(node, path, parent_contexts, context)
