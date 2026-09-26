"""
Registry module for tracking validated nodes.

This module provides functionality for registering and querying nodes
that have passed validation, to support cross-level predicate evaluation
and actions.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence

from katachi.schema.schema_node import SchemaNode


class NodeContext:
    """Context information about a validated node."""

    __slots__ = ("_parent_paths", "captures", "node", "parents", "path")

    def __init__(
        self,
        node: SchemaNode,
        path: str,
        parent_paths: list[str] | None = None,
        parents: Sequence[tuple[SchemaNode, str]] | None = None,
        captures: dict[str, str] | None = None,
    ):
        """
        Initialize a node context.

        Args:
            node: The schema node
            path: The path that was validated
            parent_paths: List of parent paths in the hierarchy
            parents: List of parent ``(schema_node, path)`` tuples, outermost first
            captures: Values of named groups captured by this entry's and its ancestors' patterns
        """
        self.node = node
        self.path = path
        self.parents: Sequence[tuple[SchemaNode, str]] = parents or ()
        self._parent_paths = parent_paths
        self.captures: dict[str, str] = captures if captures is not None else {}

    @property
    def parent_paths(self) -> list[str]:
        """Paths of the parent directories, outermost first."""
        if self._parent_paths is None:
            self._parent_paths = [p for _, p in self.parents]
        return self._parent_paths

    @property
    def name(self) -> str:
        """Base name of the validated path."""
        return self.path.rsplit("/", 1)[-1]

    def __repr__(self) -> str:
        return f"NodeContext({self.node.semantical_name}, {self.path})"


class NodeRegistry:
    """Registry for tracking nodes that passed validation."""

    def __init__(self) -> None:
        """Initialize the node registry."""
        # Dictionary mapping semantical names to lists of node contexts
        self._nodes_by_name: dict[str, list[NodeContext]] = {}
        # Dictionary mapping schema node identity to lists of node contexts
        self._nodes_by_node: dict[int, list[NodeContext]] = {}
        # Dictionary mapping paths to node contexts
        self._nodes_by_path: dict[str, NodeContext] = {}
        # Set of directories that have been processed
        self._processed_dirs: set[str] = set()

    def register_node(
        self,
        node: SchemaNode,
        path: str,
        parent_paths: list[str] | None = None,
        parents: Sequence[tuple[SchemaNode, str]] | None = None,
    ) -> NodeContext:
        """
        Register a node that passed validation.

        Args:
            node: Schema node that was validated
            path: Path that was validated
            parent_paths: List of parent paths in the hierarchy
            parents: List of parent ``(schema_node, path)`` tuples

        Returns:
            The created context
        """
        context = NodeContext(node, path, parent_paths, parents)
        self.add_context(context)
        return context

    def add_context(self, context: NodeContext) -> None:
        """Register an already created context."""
        self._nodes_by_name.setdefault(context.node.semantical_name, []).append(context)
        self._nodes_by_node.setdefault(id(context.node), []).append(context)
        self._nodes_by_path[context.path] = context

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

    def get_context_by_path(self, path: str) -> NodeContext | None:
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

    def get_contexts_by_node(self, node: SchemaNode) -> list[NodeContext]:
        """
        Get all contexts registered for a specific schema node (by identity).

        Useful when several schema nodes share the same semantical name.
        """
        return self._nodes_by_node.get(id(node), [])

    def iter_contexts(self) -> Iterator[NodeContext]:
        """
        Iterate over all registered contexts in registration (depth first) order.

        Returns:
            Iterator over all NodeContext objects
        """
        return iter(self._nodes_by_path.values())

    def __len__(self) -> int:
        return len(self._nodes_by_path)
