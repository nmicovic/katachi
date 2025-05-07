"""
Actions module for Katachi.

This module provides functionality for registering and executing callbacks
when traversing the file system according to a schema.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, ClassVar, Optional

from katachi.schema.schema_node import SchemaNode
from katachi.validation.registry import NodeRegistry

# Type definition for node context: tuple of (schema_node, path)
NodeContext = tuple[SchemaNode, Path]

# Type for action callbacks: current node, path, parent contexts, and additional context
ActionCallback = Callable[[SchemaNode, Path, Sequence[NodeContext], dict[str, Any]], None]


class ActionResult:
    """Represents the result of an action execution."""

    def __init__(self, success: bool, message: str, path: Path, action_name: str):
        """
        Initialize an action result.

        Args:
            success: Whether the action succeeded
            message: Description of what happened
            path: The path the action was performed on
            action_name: Name of the action that was performed
        """
        self.success = success
        self.message = message
        self.path = path
        self.action_name = action_name

    def __str__(self) -> str:
        status = "Success" if self.success else "Failed"
        return f"{status} - {self.action_name} on {self.path}: {self.message}"


class ActionTiming(Enum):
    """When an action should be executed."""

    DURING_VALIDATION = auto()  # Run during structure validation (old behavior)
    AFTER_VALIDATION = auto()  # Run after all validation is complete (default new behavior)


@dataclass
class ActionRegistration:
    """Action registration details."""

    callback: ActionCallback
    timing: ActionTiming
    description: str


class ActionRegistry:
    """Registry for file and directory actions."""

    # Registry of callbacks by semantic name
    _registry: ClassVar[dict[str, ActionRegistration]] = {}

    @classmethod
    def register(
        cls,
        semantical_name: str,
        callback: ActionCallback,
        timing: ActionTiming = ActionTiming.AFTER_VALIDATION,
        description: str = "",
    ) -> None:
        """
        Register a callback for a specific schema node semantic name.

        Args:
            semantical_name: The semantic name to trigger the callback for
            callback: Function to call when traversing a node with this semantic name
            timing: When the action should be executed
            description: Human-readable description of what the action does
        """
        cls._registry[semantical_name] = ActionRegistration(
            callback=callback, timing=timing, description=description or f"Action for {semantical_name}"
        )

    @classmethod
    def get(cls, semantical_name: str) -> Optional[ActionRegistration]:
        """Get a registered action by semantical name."""
        return cls._registry.get(semantical_name)

    @classmethod
    def execute_actions(
        cls,
        registry: NodeRegistry,
        context: Optional[dict[str, Any]] = None,
        timing: ActionTiming = ActionTiming.AFTER_VALIDATION,
    ) -> list[ActionResult]:
        """
        Execute all registered actions on validated nodes.

        Args:
            registry: Registry of validated nodes
            context: Additional context data
            timing: Which set of actions to execute based on timing

        Returns:
            List of action results
        """
        results = []
        context = context or {}

        # Get all semantical names from the registry
        for semantical_name, registration in cls._registry.items():
            # Skip actions that don't match the requested timing
            if registration.timing != timing:
                continue

            # Get all nodes with this semantical name
            node_contexts = registry.get_nodes_by_name(semantical_name)
            for node_ctx in node_contexts:
                try:
                    # Get parent contexts
                    parent_contexts = []
                    for parent_path in node_ctx.parent_paths:
                        parent_node_ctx = registry.get_node_by_path(parent_path)
                        if parent_node_ctx:
                            parent_contexts.append((parent_node_ctx.node, parent_node_ctx.path))

                    # Execute the action
                    registration.callback(node_ctx.node, node_ctx.path, parent_contexts, context)
                    results.append(
                        ActionResult(
                            success=True,
                            message=f"Executed {registration.description}",
                            path=node_ctx.path,
                            action_name=semantical_name,
                        )
                    )
                except Exception as e:
                    results.append(
                        ActionResult(
                            success=False,
                            message=f"Action failed: {e!s}",
                            path=node_ctx.path,
                            action_name=semantical_name,
                        )
                    )

        return results


# Legacy functions for backward compatibility
def register_action(semantical_name: str, callback: ActionCallback) -> None:
    """
    Register a callback for a specific schema node semantic name.

    Args:
        semantical_name: The semantic name to trigger the callback for
        callback: Function to call when traversing a node with this semantic name
    """
    ActionRegistry.register(
        semantical_name,
        callback,
        timing=ActionTiming.DURING_VALIDATION,
        description=f"Legacy action for {semantical_name}",
    )


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
    registration = ActionRegistry.get(node.semantical_name)
    if registration and registration.timing == ActionTiming.DURING_VALIDATION:
        registration.callback(node, path, parent_contexts, context)
