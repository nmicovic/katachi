# Katachi API Reference

Katachi is a Python package for validating, processing, and parsing directory structures against defined schemas.

## Overview

The package provides tools to:

- Define schemas for directory structures
- Load schemas from YAML files
- Validate existing directories against schemas
- Command-line interface for easy validation

## Modules

### Schema Node

The foundation of Katachi is the schema node system, which defines how directory structures should be organized.

```python
# Example usage
from katachi.schema.schema_node import SchemaDirectory, SchemaFile
from pathlib import Path

# Create a schema for a simple photo directory
photos = SchemaDirectory(path=Path("photos"), semantical_name="Photos", description="Photo collection")
photos.add_child(SchemaFile(path=Path("photos/image.jpg"), semantical_name="Image", extension="jpg"))
```

::: katachi.schema.schema_node

### Schema Importer

Load schema definitions from YAML files to create SchemaNode structures.

```python
# Example usage
from katachi.schema.importer import load_yaml
from pathlib import Path

result = load_yaml(Path("schema.yaml"), Path("target_directory"))
if result.is_success():
    schema = result.schema
    # Use the schema
else:
    print(f"Error: {result.error_message}")
```

::: katachi.schema.importer

### Schema Validator

Validate directory structures against schema definitions.

```python
# Example usage
from katachi.schema.validate import validate_schema
from pathlib import Path

is_valid = validate_schema(schema, Path("directory_to_validate"))
```

::: katachi.schema.validate

### Command Line Interface

Katachi provides a convenient command-line interface for validating directory structures.

```bash
# Example usage
katachi validate schema.yaml target_directory
```

::: katachi.cli
