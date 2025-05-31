"""
Registry module for tracking validated nodes.

This module provides functionality for registering and querying nodes
that have passed validation, to support cross-level predicate evaluation.
"""

from collections.abc import Iterator
from typing import Optional

from katachi.schema.schema_node import SchemaNode


class NodeContext:
    """Context information about a validated node."""

    def __init__(self, node: SchemaNode, path: str, parent_paths: Optional[list[str]] = None):
        """
        Initialize a node context.

        Args:
            node: The schema node
            path: The path that was validated
            parent_paths: List of parent paths in the hierarchy
        """
        self.node = node
        self.path = path
        self.parent_paths = parent_paths or []

    def __repr__(self) -> str:
        return f"NodeContext({self.node.semantical_name}, {self.path})"


class NodeRegistry:
    """Registry for tracking nodes that passed validation."""

    def __init__(self) -> None:
        """Initialize the node registry."""
        # Dictionary mapping semantical names to lists of node contexts
        self._nodes_by_name: dict[str, list[NodeContext]] = {}
        # Dictionary mapping paths to node contexts
        self._nodes_by_path: dict[str, NodeContext] = {}
        # Set of directories that have been processed
        self._processed_dirs: set[str] = set()

    def register_node(self, node: SchemaNode, path: str, parent_paths: Optional[list[str]] = None) -> None:
        """
        Register a node that passed validation.

        Args:
            node: Schema node that was validated
            path: Path that was validated
            parent_paths: List of parent paths in the hierarchy
        """
        context = NodeContext(node, path, parent_paths)

        # Register by semantical name
        if node.semantical_name not in self._nodes_by_name:
            self._nodes_by_name[node.semantical_name] = []
        self._nodes_by_name[node.semantical_name].append(context)

        # Register by path
        self._nodes_by_path[path] = context

    def register_processed_dir(self, dir_path: str) -> None:
        """
        Register a directory as processed.

        Args:
            dir_path: Path to the processed directory
        """
        self._processed_dirs.add(dir_path)

    def is_dir_processed(self, dir_path: str) -> bool:
        """
        Check if a directory has been processed.

        Args:
            dir_path: Path to check

        Returns:
            True if the directory has been processed, False otherwise
        """
        return dir_path in self._processed_dirs

    def get_paths_by_name(self, name: str) -> list[str]:
        """
        Get all paths registered for a given semantical name.

        Args:
            name: Semantical name to look up

        Returns:
            List of paths registered for this name
        """
        return [context.path for context in self._nodes_by_name.get(name, [])]

    def get_context_by_path(self, path: str) -> Optional[NodeContext]:
        """
        Get the context for a specific path.

        Args:
            path: Path to look up

        Returns:
            NodeContext if found, None otherwise
        """
        return self._nodes_by_path.get(path)

    def get_contexts_by_name(self, name: str) -> list[NodeContext]:
        """
        Get all contexts registered for a given semantical name.

        Args:
            name: Semantical name to look up

        Returns:
            List of NodeContext objects for this name
        """
        return self._nodes_by_name.get(name, [])

    def iter_contexts(self) -> Iterator[NodeContext]:
        """
        Iterate over all registered contexts.

        Returns:
            Iterator over all NodeContext objects
        """
        return iter(self._nodes_by_path.values())
