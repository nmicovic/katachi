"""
Registry module for tracking validated nodes.

This module provides functionality for registering and querying nodes
that have passed validation, to support cross-level predicate evaluation.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Optional

from katachi.schema.schema_node import SchemaNode


class NodeContext:
    """Context information about a validated node."""

    def __init__(self, node: SchemaNode, path: Path, parent_paths: Optional[list[Path]] = None):
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
        self._nodes_by_path: dict[Path, NodeContext] = {}
        # Set of directories that have been processed
        self._processed_dirs: set[Path] = set()

    def register_node(self, node: SchemaNode, path: Path, parent_paths: Optional[list[Path]] = None) -> None:
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

    def register_processed_dir(self, dir_path: Path) -> None:
        """
        Register a directory as processed.

        Args:
            dir_path: Path to the processed directory
        """
        self._processed_dirs.add(dir_path)

    def is_dir_processed(self, dir_path: Path) -> bool:
        """
        Check if a directory has been processed.

        Args:
            dir_path: Path to check

        Returns:
            True if the directory has been processed, False otherwise
        """
        return dir_path in self._processed_dirs

    def get_nodes_by_name(self, semantical_name: str) -> list[NodeContext]:
        """
        Get all nodes with a given semantical name.

        Args:
            semantical_name: The semantical name to look up

        Returns:
            List of node contexts with the given semantical name
        """
        return self._nodes_by_name.get(semantical_name, [])

    def get_node_by_path(self, path: Path) -> Optional[NodeContext]:
        """
        Get a node by its path.

        Args:
            path: The path to look up

        Returns:
            Node context for the path, or None if not found
        """
        return self._nodes_by_path.get(path)

    def get_nodes_under_path(self, base_path: Path) -> Iterator[NodeContext]:
        """
        Get all nodes under a given path.

        Args:
            base_path: The base path to filter by

        Returns:
            Iterator of node contexts under the given path
        """
        for path, context in self._nodes_by_path.items():
            try:
                if base_path in path.parents or path == base_path:
                    yield context
            except ValueError:
                # This happens if paths are on different drives
                continue

    def get_paths_by_name(self, semantical_name: str) -> list[Path]:
        """
        Get all paths with a given semantical name.

        Args:
            semantical_name: The semantical name to look up

        Returns:
            List of paths with the given semantical name
        """
        return [context.path for context in self.get_nodes_by_name(semantical_name)]

    def clear(self) -> None:
        """Clear the registry."""
        self._nodes_by_name.clear()
        self._nodes_by_path.clear()
        self._processed_dirs.clear()

    def __str__(self) -> str:
        return f"NodeRegistry with {len(self._nodes_by_path)} nodes of {len(self._nodes_by_name)} types"
