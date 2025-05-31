"""
Actions module for Katachi.

This module provides functionality for registering and executing callbacks
when traversing the file system according to a schema.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, ClassVar, Optional

from katachi.schema.schema_node import SchemaNode
from katachi.validation.registry import NodeRegistry

# Type definition for node context: tuple of (schema_node, path)
NodeContext = tuple[SchemaNode, str]

# Type for action callbacks: current node, path, parent contexts, and additional context
ActionCallback = Callable[[SchemaNode, str, Sequence[NodeContext], dict[str, Any]], None]


class ActionResult:
    """Represents the result of an action execution."""

    def __init__(self, success: bool, message: str, path: str, action_name: str):
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

    DURING_VALIDATION = auto()
    AFTER_VALIDATION = auto()


@dataclass
class ActionRegistration:
    """Registration information for an action."""

    callback: ActionCallback
    timing: ActionTiming


class ActionRegistry:
    """Registry for actions to be executed during schema validation."""

    _actions: ClassVar[dict[str, ActionRegistration]] = {}

    @classmethod
    def register(
        cls,
        node_name: str,
        timing: ActionTiming = ActionTiming.DURING_VALIDATION,
    ) -> Callable:
        """
        Register an action for a specific node.

        Args:
            node_name: Name of the node to register the action for
            timing: When the action should be executed

        Returns:
            Decorator function
        """

        def decorator(func: ActionCallback) -> ActionCallback:
            cls._actions[node_name] = ActionRegistration(callback=func, timing=timing)
            return func

        return decorator

    @classmethod
    def get(cls, node_name: str) -> Optional[ActionRegistration]:
        """
        Get the registration for a node.

        Args:
            node_name: Name of the node to get the registration for

        Returns:
            ActionRegistration if found, None otherwise
        """
        return cls._actions.get(node_name)

    @classmethod
    def execute_actions(
        cls,
        registry: NodeRegistry,
        context: Optional[dict[str, Any]] = None,
        timing: ActionTiming = ActionTiming.DURING_VALIDATION,
    ) -> list[ActionResult]:
        """
        Execute all registered actions for a given timing.

        Args:
            registry: Registry of validated nodes
            context: Additional context data
            timing: Which actions to execute

        Returns:
            List of action results
        """
        results: list[ActionResult] = []
        context = context or {}

        for node_name, registration in cls._actions.items():
            if registration.timing != timing:
                continue

            # Get all contexts for this node type
            node_contexts = registry.get_contexts_by_name(node_name)
            for node_context in node_contexts:
                try:
                    # Execute the action
                    registration.callback(
                        node_context.node,
                        node_context.path,
                        [],
                        context,
                    )
                    results.append(
                        ActionResult(
                            success=True,
                            message="Action executed successfully",
                            path=node_context.path,
                            action_name=node_name,
                        )
                    )
                except Exception as e:
                    results.append(
                        ActionResult(
                            success=False,
                            message=f"Action failed: {e!s}",
                            path=node_context.path,
                            action_name=node_name,
                        )
                    )

        return results


def process_node(
    node: SchemaNode,
    path: str,
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
