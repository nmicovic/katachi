from pathlib import Path

import pytest

from katachi.cli import validate
from katachi.schema.importer import load_yaml
from katachi.schema.schema_node import SchemaDirectory, SchemaFile
from katachi.schema.validate import ValidationError, validate_schema


# Use fixtures for paths to avoid repetition
@pytest.fixture
def test_schemas_dir() -> Path:
    """Fixture to provide the path to the schema test directories."""
    return Path(__file__).parent / "schema_tests"


@pytest.fixture
def valid_test_cases(test_schemas_dir: Path) -> list[dict[str, Path]]:
    """Fixture to provide valid test cases for schema validation."""
    return [
        {
            "name": "sanity",
            "schema_path": test_schemas_dir / "test_sanity" / "schema.yaml",
            "dataset_path": test_schemas_dir / "test_sanity" / "dataset",
        },
        {
            "name": "depth_1",
            "schema_path": test_schemas_dir / "test_depth_1" / "schema.yaml",
            "dataset_path": test_schemas_dir / "test_depth_1" / "dataset",
        },
    ]


# Parameterized test for all valid cases
@pytest.mark.parametrize("case_name", ["sanity", "depth_1"])
def test_validate_schema_valid_cases(valid_test_cases: list[dict[str, Path]], case_name: str):
    """Test that all valid schemas validate successfully."""
    # Find the test case by name
    test_case = next(case for case in valid_test_cases if case["name"] == case_name)

    # Run validation
    result = validate(test_case["schema_path"], test_case["dataset_path"])
    assert result, f"Validation for {case_name} failed"


def test_schema_nodes_sanity(valid_test_cases: list[dict[str, Path]]):
    """Test that the schema nodes are correctly parsed for the sanity test case."""
    sanity_case = next(case for case in valid_test_cases if case["name"] == "sanity")

    # Load the schema using our importer
    schema = load_yaml(sanity_case["schema_path"], sanity_case["dataset_path"])

    # Verify the schema structure
    assert isinstance(schema, SchemaDirectory), "Root should be a directory"
    assert schema.semantical_name == "dataset_root", "Root name should be 'dataset_root'"
    assert len(schema.children) == 1, "Root should have one child"

    # Check file schema definition
    file_schema = schema.children[0]
    assert isinstance(file_schema, SchemaFile), "Child should be a file"
    assert file_schema.semantical_name == "image_item", "File name should be 'image_item'"
    assert file_schema.extension == "jpg", "Extension should be 'jpg'"


def test_schema_nodes_depth1(valid_test_cases: list[dict[str, Path]]):
    """Test that the schema nodes are correctly parsed for the depth_1 test case."""
    depth1_case = next(case for case in valid_test_cases if case["name"] == "depth_1")

    # Load the schema using our importer
    schema = load_yaml(depth1_case["schema_path"], depth1_case["dataset_path"])

    # Verify the schema structure
    assert isinstance(schema, SchemaDirectory), "Root should be a directory"
    assert schema.semantical_name == "dataset", "Root name should be 'dataset'"
    assert schema.description == "A dataset with a depth of 3", "Description should match"
    assert len(schema.children) == 1, "Root should have one child"

    # Verify the timestamp directory
    timestamp_dir = schema.children[0]
    assert isinstance(timestamp_dir, SchemaDirectory), "Child should be a directory"
    assert timestamp_dir.semantical_name == "timestamp", "Directory name should be 'timestamp'"
    assert "Data reprensetationf or the data in format dd.mm.yyyy" in timestamp_dir.description, (
        "Description should match"
    )
    assert len(timestamp_dir.children) == 1, "Timestamp dir should have one child"

    # Check the image file schema
    img_schema = timestamp_dir.children[0]
    assert isinstance(img_schema, SchemaFile), "Child should be a file"
    assert img_schema.semantical_name == "img_item", "File name should be 'img_item'"
    assert img_schema.extension == "jpg", "Extension should be 'jpg'"
    assert img_schema.description == "An image jpg file", "Description should match"


def test_file_existence():
    """Test that the validation correctly checks for file existence."""
    # Create a temporary test directory with schema
    test_dir = Path(__file__).parent
    schema_path = test_dir / "schema_tests" / "test_sanity" / "schema.yaml"
    # Point to a non-existent directory
    non_existent_path = test_dir / "non_existent_directory"

    # Validation should fail
    with pytest.raises(ValidationError, match="does not exist"):
        schema = load_yaml(schema_path, non_existent_path)
        validate_schema(schema)


def test_cli_validation_sanity():
    """Test the CLI validate command with the sanity schema."""
    test_dir = Path(__file__).parent
    schema_path = test_dir / "schema_tests" / "test_sanity" / "schema.yaml"
    dataset_path = test_dir / "schema_tests" / "test_sanity" / "dataset"

    # Use the CLI function
    assert validate(schema_path, dataset_path), "CLI validation failed for sanity test"


def test_cli_validation_depth1():
    """Test the CLI validate command with the depth_1 schema."""
    test_dir = Path(__file__).parent
    schema_path = test_dir / "schema_tests" / "test_depth_1" / "schema.yaml"
    dataset_path = test_dir / "schema_tests" / "test_depth_1" / "dataset"

    # Use the CLI function
    assert validate(schema_path, dataset_path), "CLI validation failed for depth_1 test"


if __name__ == "__main__":
    # This code won't run when executed via pytest
    pytest.main(["-v", __file__])
