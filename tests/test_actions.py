from pathlib import Path

from katachi.schema.importer import load_yaml
from katachi.utils.fs_utils import get_filesystem
from katachi.validation.validators import SchemaValidator


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
