import pytest

from katachi.schema.importer import load_yaml
from katachi.utils.fs_utils import get_filesystem
from katachi.validation.validators import SchemaValidator

SCHEMA_TESTS = [
    ("tests/schema_tests/test_sanity/schema.yaml", "tests/schema_tests/test_sanity/dataset"),
    ("tests/schema_tests/test_depth_1/schema.yaml", "tests/schema_tests/test_depth_1/dataset"),
    ("tests/schema_tests/test_paired_files/schema.yaml", "tests/schema_tests/test_paired_files/data"),
    ("tests/schema_tests/test_depth_2/schema.yaml", "tests/schema_tests/test_depth_2/dataset_root"),
    ("tests/schema_tests/test_ambiguous_dirs/schema.yaml", "tests/schema_tests/test_ambiguous_dirs/root"),
]


@pytest.mark.parametrize("schema_path,target_path", SCHEMA_TESTS)
def test_schema_validation_python_api(schema_path, target_path):
    schema_fs, schema_path_no_prefix = get_filesystem(schema_path)
    target_fs, target_path_no_prefix = get_filesystem(target_path)
    schema = load_yaml(schema_path_no_prefix, target_path_no_prefix, schema_fs, target_fs)
    assert schema is not None, f"Failed to load schema: {schema_path}"
    report = SchemaValidator.validate_schema(schema, target_path_no_prefix, target_fs)
    assert report.is_valid(), (
        f"Validation failed for {schema_path} {target_path}. Results: {[r.message for r in report.results if not r.is_valid]}"
    )
