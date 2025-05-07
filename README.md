# katachi

[![Release](https://img.shields.io/github/v/release/nmicovic/katachi)](https://img.shields.io/github/v/release/nmicovic/katachi)
[![Build status](https://img.shields.io/github/actions/workflow/status/nmicovic/katachi/main.yml?branch=main)](https://github.com/nmicovic/katachi/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/nmicovic/katachi/branch/main/graph/badge.svg)](https://codecov.io/gh/nmicovic/katachi)
[![Commit activity](https://img.shields.io/github/commit-activity/m/nmicovic/katachi)](https://img.shields.io/github/commit-activity/m/nmicovic/katachi)
[![License](https://img.shields.io/github/license/nmicovic/katachi)](https://img.shields.io/github/license/nmicovic/katachi)

<div align="center">
  <img src="logo.png" alt="Logo" width="300"/>
</div>

**Katachi** is a Python package for validating, processing, and parsing directory structures against defined schemas.

> **Note**: Katachi is currently under active development and should be considered a work in progress. APIs may change in future releases.

- **GitHub repository**: <https://github.com/nmicovic/katachi/>
- **Documentation**: <https://nmicovic.github.io/katachi/>

## Features

- 📐 **Schema-based validation** - Define expected directory structures using YAML
- 🧩 **Extensible architecture** - Create custom validators and actions
- 🔄 **Relationship validation** - Validate relationships between files (like paired files)
- 🚀 **Command-line interface** - Easy to use CLI with rich formatting
- 📋 **Detailed reports** - Get comprehensive validation reports

## Installation

Install from PyPI:

```bash
pip install katachi
```

For development:

```bash
git clone https://github.com/nmicovic/katachi.git
cd katachi
make install
```

## Quick Start

### Define a schema (schema.yaml)

```yaml
semantical_name: data
type: directory
pattern_name: data
children:
  - semantical_name: image
    pattern_name: "img\\d+"
    type: file
    extension: .jpg
    description: "Image files with numeric identifiers"
  - semantical_name: metadata
    pattern_name: "img\\d+"
    type: file
    extension: .json
    description: "Metadata for image files"
  - semantical_name: file_pairs_check
    type: predicate
    predicate_type: pair_comparison
    description: "Check if images have matching metadata files"
    elements:
      - image
      - metadata
```

### Validate a directory structure

```bash
katachi validate schema.yaml target_directory
```

## Command-Line Examples

Validate a simple directory structure:
```bash
katachi validate "tests/schema_tests/test_sanity/schema.yaml" "tests/schema_tests/test_sanity/dataset"
```

Validate a nested directory structure:
```bash
katachi validate "tests/schema_tests/test_depth_1/schema.yaml" "tests/schema_tests/test_depth_1/dataset"
```

Validate paired files (e.g., ensure each .jpg has a matching .json file):
```bash
katachi validate "tests/schema_tests/test_paired_files/schema.yaml" "tests/schema_tests/test_paired_files/data"
```

## Python API

```python
from pathlib import Path
from katachi.schema.importer import load_yaml
from katachi.schema.validate import validate_schema

# Load schema from YAML
schema = load_yaml(Path("schema.yaml"), Path("data_directory"))

# Validate directory against schema
report = validate_schema(schema, Path("data_directory"))

# Check if validation passed
if report.is_valid():
    print("Validation successful!")
else:
    print("Validation failed with the following issues:")
    for result in report.results:
        if not result.is_valid:
            print(f"- {result.path}: {result.message}")
```

## Extending Katachi

### Custom validators

```python
from pathlib import Path
from katachi.schema.schema_node import SchemaNode
from katachi.validation.core import ValidationResult, ValidatorRegistry

def my_custom_validator(node: SchemaNode, path: Path) -> ValidationResult:
    # Custom validation logic
    return ValidationResult(
        is_valid=True,
        message="Custom validation passed",
        path=path,
        validator_name="custom_validator"
    )

# Register the validator
ValidatorRegistry.register("custom_validator", my_custom_validator)
```

### Custom file processing

```python
from pathlib import Path
from typing import Any
from katachi.schema.actions import register_action, NodeContext

def process_image(node, path: Path, parent_contexts: list[NodeContext], context: dict[str, Any]) -> None:
    # Custom image processing logic
    print(f"Processing image: {path}")
    # Access parent context if needed
    for parent_node, parent_path in parent_contexts:
        if parent_node.semantical_name == "timestamp":
            print(f"Image from date: {parent_path.name}")
            break

# Register the action
register_action("image", process_image)
```

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

This project is licensed under the terms of the [MIT License](LICENSE).
