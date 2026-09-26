from __future__ import annotations

from pathlib import Path

from katachi.schema.actions import ActionRegistry, ActionTiming, register_action
from katachi.schema.importer import load_yaml
from katachi.utils.fs_utils import get_filesystem
from katachi.validation.validators import SchemaValidator
from tests.conftest import run_validation


def test_validation_without_actions() -> None:
    """Test that validation works correctly without actions."""
    # Setup test paths
    test_dir = Path("tests/schema_tests/test_depth_1")
    schema_path = str(test_dir / "schema.yaml")
    target_path = str(test_dir / "dataset")

    # Use get_filesystem to match CLI logic
    schema_fs, schema_path_no_prefix = get_filesystem(schema_path)
    target_fs, target_path_no_prefix = get_filesystem(target_path)

    # Load schema and validate
    schema = load_yaml(schema_path_no_prefix, target_path_no_prefix, schema_fs, target_fs)
    assert schema is not None, "Failed to load test schema"

    # Run validation
    report = SchemaValidator.validate_schema(schema, target_path_no_prefix, target_fs)

    # Check validation passed
    assert report.is_valid(), "Validation should pass"
    assert report.action_results == []


def test_validation_with_predicates() -> None:
    """Test that validation works correctly with predicates."""
    # Setup test paths
    test_dir = Path("tests/schema_tests/test_paired_files")
    schema_path = str(test_dir / "schema.yaml")
    target_path = str(test_dir / "data")

    # Use get_filesystem to match CLI logic
    schema_fs, schema_path_no_prefix = get_filesystem(schema_path)
    target_fs, target_path_no_prefix = get_filesystem(target_path)

    # Load schema and validate
    schema = load_yaml(schema_path_no_prefix, target_path_no_prefix, schema_fs, target_fs)
    assert schema is not None, "Failed to load test schema"

    # Run validation
    report = SchemaValidator.validate_schema(schema, target_path_no_prefix, target_fs)

    # Check validation passed
    assert report.is_valid(), "Validation should pass"


SCHEMA = """
semantical_name: dataset
type: directory
children:
  - semantical_name: day
    type: directory
    pattern_name: "(?P<date>\\\\d{4}-\\\\d{2}-\\\\d{2})"
    children:
      - {semantical_name: image, type: file, pattern_name: "img\\\\d+", extension: .jpg}
      - {semantical_name: meta, type: file, pattern_name: "img\\\\d+", extension: .json}
      - {semantical_name: pairs, type: predicate, predicate_type: pair_comparison, elements: [image, meta]}
"""


def test_during_actions_get_parents_captures_and_context(tree):
    calls = []

    @register_action("image")
    def on_image(node, path, parents, context):
        calls.append((Path(path).name, [n.semantical_name for n, _ in parents], context["run"]))

    root = tree("2025-01-01/img1.jpg", "2025-01-01/img1.json", "2025-01-02/img2.jpg", "2025-01-02/img2.json")
    report = run_validation(SCHEMA, root, execute_actions=True, context={"run": 7})
    assert report.is_valid()
    assert sorted(calls) == [("img1.jpg", ["dataset", "day"], 7), ("img2.jpg", ["dataset", "day"], 7)]
    assert all(a.success for a in report.action_results)
    captures = [c.captures for c in report.context["registry"].get_contexts_by_name("image")]
    assert sorted(c["date"] for c in captures) == ["2025-01-01", "2025-01-02"]


def test_actions_are_not_executed_without_flag(tree):
    calls = []
    register_action("image", lambda *args: calls.append(args))
    run_validation(SCHEMA, tree("2025-01-01/img1.jpg", "2025-01-01/img1.json"))
    assert calls == []


def test_actions_only_run_for_committed_matches(tree):
    """Discarded alternatives of an ambiguous schema never trigger actions."""
    schema = """
    type: directory
    children:
      - semantical_name: png_dir
        type: directory
        pattern_name: "d\\\\d"
        children: [{semantical_name: png, type: file, extension: .png}]
      - semantical_name: jpg_dir
        type: directory
        pattern_name: "d\\\\d"
        children: [{semantical_name: jpg, type: file, extension: .jpg}]
    """
    seen = []
    register_action("png_dir", lambda node, path, parents, ctx: seen.append(("png_dir", Path(path).name)))
    register_action("jpg_dir", lambda node, path, parents, ctx: seen.append(("jpg_dir", Path(path).name)))
    report = run_validation(schema, tree("d1/a.jpg", "d2/b.png"), execute_actions=True)
    assert report.is_valid()
    assert sorted(seen) == [("jpg_dir", "d1"), ("png_dir", "d2")]


def test_failing_action_is_captured(tree):
    @ActionRegistry.register("image")
    def broken(node, path, parents, context):
        raise RuntimeError("disk full")

    report = run_validation(SCHEMA, tree("2025-01-01/img1.jpg", "2025-01-01/img1.json"), execute_actions=True)
    assert report.is_valid()
    [result] = report.action_results
    assert not result.success
    assert result.message == "Action failed: disk full"
    assert result.to_dict()["action"] == "image"


def test_after_validation_actions_require_a_valid_tree(tree):
    calls = []
    register_action("meta", lambda *args: calls.append(args[1]), timing=ActionTiming.AFTER_VALIDATION)
    # Missing pair -> predicates fail -> AFTER actions don't run
    run_validation(SCHEMA, tree("2025-01-01/img1.jpg"), execute_actions=True)
    assert calls == []
    run_validation(SCHEMA, tree("2025-01-01/img1.jpg", "2025-01-01/img1.json"), execute_actions=True)
    assert len(calls) == 1
