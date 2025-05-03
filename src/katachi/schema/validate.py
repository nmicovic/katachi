from pathlib import Path

from katachi.schema.schema_node import SchemaDirectory, SchemaFile, SchemaNode


# Base class for all validation errors
class ValidationError(Exception):
    """Base class for all validation-related errors."""

    pass


class PathNotFoundError(ValidationError):
    """Exception raised when a path does not exist."""

    def __init__(self, path: Path):
        super().__init__(f"Path {path} does not exist")
        self.path = path


class PathNotADirectoryError(ValidationError):
    """Exception raised when a path is not a directory."""

    def __init__(self, path: Path):
        super().__init__(f"Path {path} is not a directory")
        self.path = path


class NoSubdirectoriesFoundError(ValidationError):
    """Exception raised when no subdirectories are found."""

    def __init__(self, path: Path):
        super().__init__(f"No subdirectories found in {path}")
        self.path = path


class NoMatchingFilesError(ValidationError):
    """Exception raised when no matching files are found."""

    def __init__(self, extension: str, directory: Path):
        super().__init__(f"No files with extension .{extension} found in {directory}")
        self.extension = extension
        self.directory = directory


class NoFilesFoundError(ValidationError):
    """Exception raised when no files are found in a directory."""

    def __init__(self, directory: Path):
        super().__init__(f"No files found in {directory}")
        self.directory = directory


class UnknownNodeTypeError(ValidationError):
    """Exception raised when a node has an unknown type."""

    def __init__(self, node_type: type):
        super().__init__(f"Unknown node type: {node_type}")
        self.node_type = node_type


def validate_schema(root_node: SchemaNode) -> bool:
    """
    Validates a directory structure against a SchemaNode.

    Args:
        root_node: The root SchemaNode to validate

    Returns:
        True if validation was successful

    Raises:
        PathNotFoundError: If the path does not exist
        UnknownNodeTypeError: If the node has an unknown type
        Various other ValidationError subclasses: For specific validation failures
    """
    if not root_node.path.exists():
        raise PathNotFoundError(root_node.path)

    if isinstance(root_node, SchemaFile):
        return _validate_file(root_node)
    elif isinstance(root_node, SchemaDirectory):
        return _validate_directory(root_node)
    else:
        raise UnknownNodeTypeError(type(root_node))


def _validate_file(file_node: SchemaFile) -> bool:
    """
    Validates a file schema node against the actual filesystem.

    For files, we validate that a file with the specified extension exists.
    The semantical_name doesn't need to match the actual filename.

    Args:
        file_node: The SchemaFile to validate

    Returns:
        True if validation was successful

    Raises:
        PathNotADirectoryError: If the parent directory is not a directory
        NoMatchingFilesError: If no files with the specified extension are found
        NoFilesFoundError: If no files are found in the directory
    """
    # For files, we just need to check if the parent directory exists
    # and contains at least one file with the specified extension
    parent_dir = file_node.path.parent

    if not parent_dir.is_dir():
        raise PathNotADirectoryError(parent_dir)

    # Look for any file with the specified extension
    if file_node.extension:
        matching_files = list(parent_dir.glob(f"*.{file_node.extension}"))
        if not matching_files:
            raise NoMatchingFilesError(file_node.extension, parent_dir)
    else:
        # If no extension specified, just check if any file exists
        if not any(item.is_file() for item in parent_dir.iterdir()):
            raise NoFilesFoundError(parent_dir)

    return True


def _validate_directory(dir_node: SchemaDirectory) -> bool:
    """
    Validates a directory schema node against the actual filesystem.

    For directories, we validate that the directory exists and has appropriate children.

    Args:
        dir_node: The SchemaDirectory to validate

    Returns:
        True if validation was successful

    Raises:
        PathNotADirectoryError: If the path is not a directory
        NoSubdirectoriesFoundError: If no subdirectories are found
        UnknownNodeTypeError: If a child node has an unknown type
        Various other ValidationError subclasses: For specific validation failures
    """
    if not dir_node.path.is_dir():
        raise PathNotADirectoryError(dir_node.path)

    # Validate all children - for directories with semantic names like "timestamp",
    # we need special handling for multiple subdirectories
    for child in dir_node.children:
        if isinstance(child, SchemaFile):
            _validate_file(child)
        elif isinstance(child, SchemaDirectory):
            # Special case for "timestamp" directories - we need to find any subdirectories
            if child.semantical_name == "timestamp":
                # Find all subdirectories
                subdirs = [d for d in dir_node.path.iterdir() if d.is_dir()]
                if not subdirs:
                    raise NoSubdirectoriesFoundError(dir_node.path)

                # Validate each subdirectory against the timestamp schema
                for subdir in subdirs:
                    # Create a copy of the child schema node with the actual subdirectory path
                    subdir_node = SchemaDirectory(
                        path=subdir, semantical_name=child.semantical_name, description=child.description
                    )
                    subdir_node.children = child.children
                    _validate_directory(subdir_node)
            else:
                # Standard directory validation
                _validate_directory(child)
        else:
            raise UnknownNodeTypeError(type(child))

    return True
