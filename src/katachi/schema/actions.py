"""
Actions module for Katachi.

This module provides functionality for registering and executing callbacks
for entries that matched a schema node, e.g. to process every image of a dataset.

Actions only ever run for entries that were actually matched (never for tentative
matches that were discarded while resolving ambiguous schemas).

- ``DURING_VALIDATION`` actions run for every matched entry, in depth-first order,
  and receive the chain of parent ``(schema_node, path)`` tuples.
- ``AFTER_VALIDATION`` actions run only when the whole tree (including predicates) is valid.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, ClassVar

from katachi.schema.schema_node import SchemaNode
from katachi.validation.registry import NodeContext as RegistryNodeContext
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

    def to_dict(self) -> dict[str, Any]:
        return {"success": self.success, "message": self.message, "path": self.path, "action": self.action_name}

    def __str__(self) -> str:
        status = "Success" if self.success else "Failed"
        return f"{status} - {self.action_name} on {self.path}: {self.message}"

    def __repr__(self) -> str:
        return f"ActionResult(success={self.success}, action_name={self.action_name!r}, path={self.path!r})"


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
            node_name: Semantical name of the node to register the action for
            timing: When the action should be executed

        Returns:
            Decorator function
        """

        def decorator(func: ActionCallback) -> ActionCallback:
            cls._actions[node_name] = ActionRegistration(callback=func, timing=timing)
            return func

        return decorator

    @classmethod
    def get(cls, node_name: str) -> ActionRegistration | None:
        """
        Get the registration for a node.

        Args:
            node_name: Name of the node to get the registration for

        Returns:
            ActionRegistration if found, None otherwise
        """
        return cls._actions.get(node_name)

    @classmethod
    def unregister(cls, node_name: str) -> None:
        """Remove the action registered for a node (no-op if there is none)."""
        cls._actions.pop(node_name, None)

    @classmethod
    def clear(cls) -> None:
        """Remove all registered actions."""
        cls._actions.clear()

    @classmethod
    def names(cls) -> list[str]:
        """Semantical names that have an action registered."""
        return list(cls._actions)

    @classmethod
    def _run(
        cls, registration: ActionRegistration, node_context: RegistryNodeContext, context: dict[str, Any]
    ) -> ActionResult:
        name = node_context.node.semantical_name
        try:
            registration.callback(node_context.node, node_context.path, list(node_context.parents), context)
        except Exception as e:
            return ActionResult(
                success=False, message=f"Action failed: {e!s}", path=node_context.path, action_name=name
            )
        return ActionResult(
            success=True, message="Action executed successfully", path=node_context.path, action_name=name
        )

    @classmethod
    def run_for_contexts(
        cls,
        contexts: Iterable[RegistryNodeContext],
        context: dict[str, Any] | None = None,
        timing: ActionTiming = ActionTiming.DURING_VALIDATION,
    ) -> list[ActionResult]:
        """
        Run the registered actions of the given timing for matched contexts, in the given order.

        Exceptions raised by actions are captured in failed :class:`ActionResult` objects.
        """
        context = context if context is not None else {}
        results: list[ActionResult] = []
        for node_context in contexts:
            registration = cls._actions.get(node_context.node.semantical_name)
            if registration and registration.timing == timing:
                results.append(cls._run(registration, node_context, context))
        return results

    @classmethod
    def execute_actions(
        cls,
        registry: NodeRegistry,
        context: dict[str, Any] | None = None,
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
        return cls.run_for_contexts(registry.iter_contexts(), context, timing)


def register_action(
    node_name: str,
    func: ActionCallback | None = None,
    timing: ActionTiming = ActionTiming.DURING_VALIDATION,
) -> Callable:
    """
    Register an action for the node with the given semantical name.

    Can be used directly (``register_action("image", process_image)``) or as a decorator
    (``@register_action("image")``).
    """
    decorator = ActionRegistry.register(node_name, timing)
    if func is not None:
        return decorator(func)  # type: ignore[no-any-return]
    return decorator


def process_node(
    node: SchemaNode,
    path: str,
    parent_contexts: list[NodeContext],
    context: dict[str, Any] | None = None,
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
