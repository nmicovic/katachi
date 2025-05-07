# Katachi

[![Release](https://img.shields.io/github/v/release/nmicovic/katachi)](https://img.shields.io/github/v/release/nmicovic/katachi)
[![Build status](https://img.shields.io/github/actions/workflow/status/nmicovic/katachi/main.yml?branch=main)](https://github.com/nmicovic/katachi/actions/workflows/main.yml?query=branch%3Amain)
[![Commit activity](https://img.shields.io/github/commit-activity/m/nmicovic/katachi)](https://img.shields.io/github/commit-activity/m/nmicovic/katachi)
[![License](https://img.shields.io/github/license/nmicovic/katachi)](https://img.shields.io/github/license/nmicovic/katachi)

<div align="center">
  <img src="logo.png" alt="Logo" width="300"/>
</div>

**Katachi** is a Python package for validating, processing, and parsing directory structures against defined schemas.

!!! warning "Work in Progress"
    Katachi is currently under active development and should be considered a work in progress. APIs may change in future releases.

## Overview

Katachi helps you define, validate, and process structured directory trees. It's particularly useful for:

- **Data validation**: Ensure datasets follow a consistent structure
- **Processing pipelines**: Process files based on their position in a directory tree
- **Schema enforcement**: Validate project structures against conventions
- **Relationship validation**: Verify relationships between files (like paired files)

## Features

- 📐 **Schema-based validation** - Define expected directory structures using YAML
- 🧩 **Extensible architecture** - Create custom validators and actions
- 🔄 **Relationship validation** - Validate relationships between files
- 🚀 **Command-line interface** - Easy to use CLI with rich formatting
- 📋 **Detailed reports** - Get comprehensive validation reports

## Installation

```bash
pip install katachi
```

## Quick Start

### 1. Define a schema (schema.yaml)

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

### 2. Validate a directory structure

```bash
katachi validate schema.yaml target_directory
```

### 3. Process the results

```
✅ Validation passed!
  - Found 2 image files
  - All image files have matching metadata files
```

## Next Steps

- Read the [API documentation](modules.md) to learn about the available modules
- Explore [examples](https://github.com/nmicovic/katachi/tree/main/examples) to see more use cases
- Learn how to [extend Katachi](modules.md#extending-katachi) with custom validators and actions
