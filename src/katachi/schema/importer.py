from typing import Any, Optional

import yaml
from fsspec import AbstractFileSystem

from katachi.schema.schema_node import SchemaDirectory, SchemaFile, SchemaNode, SchemaPredicateNode
from katachi.utils.logger import logger


def load_yaml(
    schema_path: str, target_path: str, schema_fs: AbstractFileSystem, target_fs: AbstractFileSystem
) -> Optional[SchemaNode]:
    """
    Load a YAML schema file and return a SchemaNode tree structure.

    Args:
        schema_path: Path to the YAML schema file
        target_path: Path to the directory that will be validated against the schema
        schema_fs: Filesystem to use for schema file
        target_fs: Filesystem to use for target path

    Returns:
        The root SchemaNode representing the schema hierarchy

    Raises:
        SchemaFileNotFoundError: If the schema file does not exist
        EmptySchemaFileError: If the schema file is empty
        InvalidYAMLContentError: If the YAML content cannot be parsed
        FailedToLoadYAMLFileError: If there are other errors loading the YAML file
    """
    try:
        with schema_fs.open(schema_path) as file:
            file_content = file.read()
            if not file_content.strip():
                logger.error(f"Schema file is empty: {schema_path}")
                return None

            data = yaml.safe_load(file_content)
            if data is None:
                logger.error(f"Invalid YAML content in file: {schema_path}")
                return None

            # Important: For the root node, we use the target_path directly
            # instead of constructing a path based on the schema node name
            return _parse_node(data, target_path, target_fs, is_root=True)
    except Exception:
        logger.exception(f"Failed to load schema file {schema_path}")
        return None


def _parse_node(
    node_data: dict[str, Any], parent_path: str, fs: AbstractFileSystem, is_root: bool = False
) -> Optional[SchemaNode]:
    """
    Recursively parse a node from the YAML data.

    Args:
        node_data: Dictionary containing the node data from YAML
        parent_path: Path to the parent directory
        fs: Filesystem to use for this node
        is_root: Whether this node is the root node of the schema

    Returns:
        SchemaNode representing this node and its children

    Raises:
        InvalidNodeDataError: If the node data has an invalid format
        InvalidNodeTypeError: If the node has an invalid or missing type
    """
    if not isinstance(node_data, dict):
        logger.error(f"Invalid node data format: {node_data}")
        return None

    node_type = node_data.get("type", "").lower()
    semantical_name = node_data.get("semantical_name", "")
    description = node_data.get("description")
    pattern_name = node_data.get("pattern_name")
    permissions = node_data.get("permissions")
    owner = node_data.get("owner")

    # For root node, use parent_path directly instead of appending the name
    # This makes the validation work with the actual directory structure
    node_path = parent_path if is_root else f"{parent_path}/{semantical_name}" if semantical_name else parent_path

    if node_type == "file":
        # Create a file node with its extension
        extension = node_data.get("extension", "")
        return SchemaFile(
            path=node_path,
            semantical_name=semantical_name,
            fs=fs,
            extension=extension,
            description=description,
            pattern_validation=pattern_name,
            permissions=permissions,
            owner=owner,
        )
    elif node_type == "directory":
        # Create a directory node
        directory = SchemaDirectory(
            path=node_path,
            semantical_name=semantical_name,
            fs=fs,
            description=description,
            pattern_validation=pattern_name,
            permissions=permissions,
            owner=owner,
        )

        # Parse children recursively if they exist
        children = node_data.get("children", [])
        for child_data in children:
            # Child nodes are never root nodes
            child_node = _parse_node(child_data, node_path, fs)
            if child_node:
                directory.add_child(child_node)
            else:
                logger.error(f"Failed to parse child node: {child_data}")
                return None

        return directory
    elif node_type == "predicate":
        # Parse predicate node
        predicate_type = node_data.get("predicate_type", "")
        elements = node_data.get("elements", [])

        if not predicate_type:
            logger.error(f"Predicate node missing required predicate_type: {node_data}")
            return None

        if not elements or not isinstance(elements, list):
            logger.error(f"Predicate node missing required elements list: {node_data}")
            return None

        return SchemaPredicateNode(
            path=node_path,
            semantical_name=semantical_name,
            fs=fs,
            predicate_type=predicate_type,
            elements=elements,
            description=description,
            permissions=permissions,
            owner=owner,
        )
    else:
        logger.error(f"Invalid or missing node type: {node_type}")
        return None
