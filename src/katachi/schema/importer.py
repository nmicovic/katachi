import logging
from pathlib import Path
from typing import Any, Optional, cast

import yaml

from katachi.schema.schema_node import SchemaDirectory, SchemaFile, SchemaNode


def load_yaml(schema_path: Path, target_path: Path) -> Optional[SchemaNode]:
    """
    Load a YAML schema file and return a SchemaNode tree structure.

    Args:
        schema_path: Path to the YAML schema file
        target_path: Path to the directory that will be validated against the schema

    Returns:
        The root SchemaNode representing the schema hierarchy

    Raises:
        SchemaFileNotFoundError: If the schema file does not exist
        EmptySchemaFileError: If the schema file is empty
        InvalidYAMLContentError: If the YAML content cannot be parsed
        FailedToLoadYAMLFileError: If there are other errors loading the YAML file
    """
    if not schema_path.exists():
        logging.error(f"Schema file not found: {schema_path}")
        return None

    try:
        with open(schema_path) as file:
            file_content = file.read()
            if not file_content.strip():
                logging.error(f"Schema file is empty: {schema_path}")
                return None

            data = yaml.safe_load(file_content)
            if data is None:
                logging.error(f"Invalid YAML content in file: {schema_path}")
                return None

            # Important: For the root node, we use the target_path directly
            # instead of constructing a path based on the schema node name
            return _parse_node(data, target_path, is_root=True)
    except yaml.YAMLError:
        logging.exception(f"Failed to load YAML file {schema_path}")
        return None
    except Exception:
        logging.exception(f"An error occurred while loading the YAML file {schema_path}")
        return None


def _parse_node(node_data: dict[str, Any], parent_path: Path, is_root: bool = False) -> Optional[SchemaNode]:
    """
    Recursively parse a node from the YAML data.

    Args:
        node_data: Dictionary containing the node data from YAML
        parent_path: Path to the parent directory
        is_root: Whether this node is the root node of the schema

    Returns:
        SchemaNode representing this node and its children

    Raises:
        InvalidNodeDataError: If the node data has an invalid format
        InvalidNodeTypeError: If the node has an invalid or missing type
    """
    if not isinstance(node_data, dict):
        logging.error(f"Invalid node data format: {node_data}")
        return None

    node_type = node_data.get("type", "").lower()
    semantical_name = node_data.get("semantical_name", "")
    description = node_data.get("description")
    pattern_name = node_data.get("pattern_name")

    # For root node, use parent_path directly instead of appending the name
    # This makes the validation work with the actual directory structure
    node_path = parent_path if is_root else parent_path / semantical_name if semantical_name else parent_path

    if node_type == "file":
        # Create a file node with its extension
        extension = node_data.get("extension", "")
        return SchemaFile(
            path=node_path,
            semantical_name=semantical_name,
            extension=extension,
            description=description,
            pattern_validation=pattern_name,
        )
    elif node_type == "directory":
        # Create a directory node
        directory = SchemaDirectory(
            path=node_path, semantical_name=semantical_name, description=description, pattern_validation=pattern_name
        )

        # Parse children recursively if they exist
        children = node_data.get("children", [])
        for child_data in children:
            # Child nodes are never root nodes
            child_node = _parse_node(child_data, node_path)
            if child_node:
                casted_value = cast(SchemaNode, child_node)
                directory.add_child(casted_value)
            else:
                logging.error(f"Failed to parse child node: {child_data}")
                return None

        return directory
    else:
        logging.error(f"Invalid or missing node type: {node_type}")
        return None
