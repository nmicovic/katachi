# Katachi API Reference

Katachi is a Python package for validating, processing, and parsing directory structures against defined schemas.

## Core Concepts

### Schema Nodes

Schema nodes represent the elements in your directory structure:

- **SchemaNode**: Abstract base class for all schema elements
- **SchemaDirectory**: Represents a directory in the schema
- **SchemaFile**: Represents a file in the schema
- **SchemaPredicateNode**: Represents a validation rule between elements

### Two-Phase Validation

Katachi uses a two-phase validation approach:

1. **Structural Validation**: Validates the existence and properties of files and directories
2. **Predicate Evaluation**: Validates relationships between elements that passed structural validation

## Modules

### Schema Node (`katachi.schema.schema_node`)

The foundation of Katachi is the schema node system, which defines how directory structures should be organized.

```python
from katachi.schema.schema_node import SchemaDirectory, SchemaFile, SchemaPredicateNode
from pathlib import Path

# Create a schema hierarchy
root = SchemaDirectory(path=Path("data"), semantical_name="data", description="Data directory")

# Add file templates
root.add_child(SchemaFile(
    path=Path("data/image.jpg"),
    semantical_name="image",
    extension=".jpg",
    pattern_validation=r"img\d+"
))

root.add_child(SchemaFile(
    path=Path("data/metadata.json"),
    semantical_name="metadata",
    extension=".json",
    pattern_validation=r"img\d+"
))

# Add a predicate to validate relationships
root.add_child(SchemaPredicateNode(
    path=Path("data"),
    semantical_name="file_pairs_check",
    predicate_type="pair_comparison",
    elements=["image", "metadata"],
    description="Check if images have corresponding metadata files"
))
```

::: katachi.schema.schema_node

### Schema Importer (`katachi.schema.importer`)

Load schema definitions from YAML files to create SchemaNode structures.

```python
from katachi.schema.importer import load_yaml
from pathlib import Path

# Load schema from YAML file
schema = load_yaml(Path("schema.yaml"), Path("target_directory"))

# Now schema contains a fully constructed schema hierarchy
if schema:
    print(f"Loaded schema for {schema.semantical_name}")
else:
    print("Failed to load schema")
```

::: katachi.schema.importer

### Schema Validator (`katachi.schema.validate`)

Validate directory structures against schema definitions.

```python
from katachi.schema.validate import validate_schema, format_validation_results
from pathlib import Path

# Validate target directory against schema
report = validate_schema(schema, Path("directory_to_validate"))

# Check if validation was successful
if report.is_valid():
    print("Validation successful!")
else:
    # Print formatted validation results
    print(format_validation_results(report))
```

::: katachi.schema.actions

### Schema Actions (`katachi.schema.actions`)

Register and execute actions to process files during schema traversal.

```python
from katachi.schema.actions import register_action, NodeContext
from pathlib import Path
from typing import Any, list, dict

# Define a custom action function
def process_image(
    node: SchemaNode,
    path: Path,
    parent_contexts: list[NodeContext],
    context: dict[str, Any]
) -> None:
    """Process an image file during schema traversal."""
    print(f"Processing image: {path}")

    # Find parent timestamp directory
    timestamp_path = None
    for node, path in parent_contexts:
        if node.semantical_name == "timestamp":
            timestamp_path = path
            break

    if timestamp_path:
        print(f"Image from date: {timestamp_path.name}")

    # Use context data if provided
    if "target_dir" in context:
        target_path = context["target_dir"] / path.name
        print(f"Would copy to: {target_path}")

# Register the action with a semantical name
register_action("image", process_image)
```

::: katachi.schema.actions

### Validation Registry (`katachi.validation.registry`)

Track and query validated nodes across the schema hierarchy.

```python
from katachi.validation.registry import NodeRegistry
from katachi.schema.schema_node import SchemaNode
from pathlib import Path

# Create a registry
registry = NodeRegistry()

# Register nodes as they're validated
registry.register_node(schema_node, path, parent_paths)

# Query nodes by semantical name
image_paths = registry.get_paths_by_name("image")

# Get all nodes under a specific directory
nodes = list(registry.get_nodes_under_path(Path("data/01.01.2023")))
```

::: katachi.validation.registry

### Validation Core (`katachi.validation.core`)

Core validation components for creating custom validators.

```python
from katachi.validation.core import ValidationResult, ValidationReport, ValidatorRegistry
from katachi.schema.schema_node import SchemaNode
from pathlib import Path

# Define a custom validator
def image_dimensions_validator(node: SchemaNode, path: Path):
    """Check if image dimensions meet requirements."""
    from PIL import Image

    try:
        with Image.open(path) as img:
            width, height = img.size

            # Check if size meets requirements
            min_width = node.metadata.get("min_width", 0)
            min_height = node.metadata.get("min_height", 0)

            if width < min_width:
                return ValidationResult(
                    is_valid=False,
                    message=f"Image width ({width}px) is less than minimum ({min_width}px)",
                    path=path,
                    validator_name="image_dimensions"
                )

            if height < min_height:
                return ValidationResult(
                    is_valid=False,
                    message=f"Image height ({height}px) is less than minimum ({min_height}px)",
                    path=path,
                    validator_name="image_dimensions"
                )

            return ValidationResult(
                is_valid=True,
                message="Image dimensions are valid",
                path=path,
                validator_name="image_dimensions"
            )
    except:
        return ValidationResult(
            is_valid=False,
            message="Failed to open image file",
            path=path,
            validator_name="image_dimensions"
        )

# Register the custom validator
ValidatorRegistry.register("image_dimensions", image_dimensions_validator)
```

::: katachi.validation.core

### Command Line Interface (`katachi.cli`)

Katachi provides a convenient command-line interface for validating directory structures.

```bash
# Basic validation
katachi validate schema.yaml target_directory

# Detailed reporting
katachi validate schema.yaml target_directory --detail-report

# Execute actions during validation
katachi validate schema.yaml target_directory --execute-actions

# Provide custom context for actions
katachi validate schema.yaml target_directory --execute-actions --context '{"target_dir": "output"}'
```

::: katachi.cli

## Extending Katachi

### Custom Validators

You can extend Katachi with custom validators to handle specific validation requirements.

```python
from pathlib import Path
from katachi.schema.schema_node import SchemaNode
from katachi.validation.core import ValidationResult, ValidatorRegistry

# Define a custom validator
def file_content_validator(node: SchemaNode, path: Path):
    """Check file content against a pattern."""
    import re

    # Only apply to files with content_pattern in metadata
    if not node.metadata.get("content_pattern"):
        return []

    # Read file content
    try:
        with open(path, "r") as f:
            content = f.read()

        # Validate against pattern
        pattern = re.compile(node.metadata["content_pattern"])
        if pattern.search(content):
            return ValidationResult(
                is_valid=True,
                message="File content matches pattern",
                path=path,
                validator_name="content_pattern"
            )
        else:
            return ValidationResult(
                is_valid=False,
                message=f"File content doesn't match pattern: {node.metadata['content_pattern']}",
                path=path,
                validator_name="content_pattern"
            )
    except Exception as e:
        return ValidationResult(
            is_valid=False,
            message=f"Error validating file content: {str(e)}",
            path=path,
            validator_name="content_pattern"
        )

# Register the validator
ValidatorRegistry.register("content_pattern", file_content_validator)
```

### Custom Predicates

The predicate system can be extended with new types of relationship validation.

Types of predicates currently supported:

| Predicate Type | Description |
|---------------|-------------|
| `pair_comparison` | Ensures files with the same base names exist across different element types |

To implement other predicate types, extend the `validate_predicate` method in the `SchemaValidator` class.
