from collections import namedtuple

import pytest

from katachi.schema.importer import load_yaml
from katachi.utils.fs_utils import get_filesystem
from katachi.validation.validators import SchemaValidator

FailingSchemaCase = namedtuple("FailingSchemaCase", ["desc", "schema_path", "target_path", "expected_error"])

FAILING_SCHEMA_TESTS = [
    FailingSchemaCase(
        desc="missing image: json file present instead of jpg",
        schema_path="tests/schema_falling_tests/simple_missing_image/schema.yaml",
        target_path="tests/schema_falling_tests/simple_missing_image/data",
        expected_error="File extension mismatch: expected jpg, got json",
    ),
    FailingSchemaCase(
        desc="wrong filename pattern: name should be digits only",
        schema_path="tests/schema_falling_tests/simple_wrong_name_image/schema.yaml",
        target_path="tests/schema_falling_tests/simple_wrong_name_image/data",
        expected_error="Filename does not match pattern: \\d+",
    ),
]


@pytest.mark.parametrize("case", FAILING_SCHEMA_TESTS, ids=[case.desc for case in FAILING_SCHEMA_TESTS])
def test_schema_validation_failing_cases(case):
    # Load the schema
    schema_fs, schema_path_no_prefix = get_filesystem(case.schema_path)
    target_fs, target_path_no_prefix = get_filesystem(case.target_path)
    schema = load_yaml(schema_path_no_prefix, target_path_no_prefix, schema_fs, target_fs)

    # Assert that schema was loaded successfully
    assert schema is not None, f"Failed to load schema: {case.schema_path}"

    # Run validation
    report = SchemaValidator.validate_schema(schema, target_path_no_prefix, target_fs)

    # Assert that validation failed
    assert not report.is_valid(), "Validation should have failed but passed"

    # Assert that the expected error message is in the results
    error_messages = [r.message for r in report.results if not r.is_valid]
    assert any(case.expected_error in msg for msg in error_messages), (
        f"Expected error message '{case.expected_error}' not found in validation results: {error_messages}"
    )
