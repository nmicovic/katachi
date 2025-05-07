from pathlib import Path

from katachi.schema.actions import ActionRegistry, ActionTiming
from katachi.schema.importer import load_yaml
from katachi.validation.validators import SchemaValidator

# Keep track of executed actions for tests
action_log = []


def setup_module() -> None:
    """Setup for the tests module - clear action log."""
    action_log.clear()


def test_action_execution_order() -> None:
    """Test that actions are executed in the correct order."""
    # Setup test paths
    test_dir = Path("tests/schema_tests/test_depth_1")
    schema_path = test_dir / "schema.yaml"
    target_path = test_dir / "dataset"

    # Clear action log
    action_log.clear()

    # Register test actions
    def test_directory_action(node, path, parent_contexts, context) -> None:
        """Test action for directories."""
        action_log.append(f"Directory action: {path.name}")

    def test_image_action(node, path, parent_contexts, context) -> None:
        """Test action for image files."""
        action_log.append(f"Image action: {path.name}")

    # Register actions with different timing
    ActionRegistry.register(
        "timestamp",
        test_directory_action,
        timing=ActionTiming.AFTER_VALIDATION,
        description="Process timestamp directories",
    )

    ActionRegistry.register(
        "img_item", test_image_action, timing=ActionTiming.AFTER_VALIDATION, description="Process image files"
    )

    # Load schema and validate with actions
    schema = load_yaml(schema_path, target_path)
    assert schema is not None, "Failed to load test schema"

    # Run validation with actions enabled
    report = SchemaValidator.validate_schema(schema, target_path, execute_actions=True)

    # Check validation passed
    assert report.is_valid(), "Validation should pass"

    # Check action results are in context
    assert "action_results" in report.context, "Action results should be in report context"
    assert len(report.context["action_results"]) > 0, "Should have action results"

    # Check actions were executed
    assert len(action_log) > 0, "Actions should have been executed"

    # Check directory actions before file actions
    dir_actions = [a for a in action_log if "Directory action" in a]
    img_actions = [a for a in action_log if "Image action" in a]

    assert len(dir_actions) > 0, "Should have directory actions"
    assert len(img_actions) > 0, "Should have image actions"


def test_legacy_action_compatibility() -> None:
    """Test that legacy action registration still works."""
    from katachi.schema.actions import register_action

    # Setup test paths
    test_dir = Path("tests/schema_tests/test_depth_1")
    schema_path = test_dir / "schema.yaml"
    target_path = test_dir / "dataset"

    # Clear action log
    action_log.clear()

    # Register test legacy action
    def legacy_action(node, path, parent_contexts, context) -> None:
        """Legacy action."""
        action_log.append(f"Legacy action: {path.name}")

    # Register with legacy registration
    register_action("img_item", legacy_action)

    # Load schema and validate with actions
    schema = load_yaml(schema_path, target_path)
    assert schema is not None, "Failed to load test schema"

    # Run validation with actions enabled
    report = SchemaValidator.validate_schema(schema, target_path, execute_actions=True)

    # Check validation passed
    assert report.is_valid(), "Validation should pass"

    # Check legacy actions were executed
    assert len(action_log) > 0, "Legacy actions should have been executed"
