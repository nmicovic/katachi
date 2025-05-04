from abc import ABC, abstractmethod
from pathlib import Path
from re import Pattern
from re import compile as re_compile
from typing import Any, Optional


class SchemaNode(ABC):
    """
    Base abstract class for all schema nodes.

    SchemaNode represents any node in the file/directory structure schema.
    It contains common properties and methods that all nodes should implement.
    """

    def __init__(
        self,
        path: Path,
        semantical_name: str,
        description: Optional[str] = None,
        pattern_validation: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ):
        """
        Initialize a schema node.

        Args:
            path: Path to this node
            semantical_name: The semantic name of this node in the schema
            description: Optional description of the node
            pattern_validation: Optional regex pattern for name validation
            metadata: Optional metadata for custom validations
        """
        self.path: Path = path
        self.semantical_name: str = semantical_name
        self.description: Optional[str] = description
        self.pattern_validation: Optional[Pattern] = None
        self.metadata: dict[str, Any] = metadata or {}

        if pattern_validation:
            self.pattern_validation = re_compile(pattern_validation)

    @abstractmethod
    def get_type(self) -> str:
        """
        Get the type of this node.

        Returns:
            String representing the node type ("file" or "directory").
        """
        pass

    def __str__(self) -> str:
        """String representation of the node."""
        return f"{self.get_type()}: {self.semantical_name} at {self.path}"

    def __repr__(self) -> str:
        """Detailed string representation of the node."""
        return f"{self.__class__.__name__}(path='{self.path}', semantical_name='{self.semantical_name}')"


class SchemaFile(SchemaNode):
    """
    Represents a file in the schema.
    """

    def __init__(
        self,
        path: Path,
        semantical_name: str,
        extension: str,
        description: Optional[str] = None,
        pattern_validation: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ):
        """
        Initialize a schema file node.

        Args:
            path: Path to this file
            semantical_name: The semantic name of this file in the schema
            extension: The file extension
            description: Optional description of the file
            pattern_validation: Optional regex pattern for name validation
            metadata: Optional metadata for custom validations
        """
        super().__init__(path, semantical_name, description, pattern_validation, metadata)
        self.extension: str = extension

    def get_type(self) -> str:
        return "file"

    def __repr__(self) -> str:
        """Detailed string representation of the file node."""
        return f"{self.__class__.__name__}(path='{self.path}', semantical_name='{self.semantical_name}', extension='{self.extension}')"


class SchemaDirectory(SchemaNode):
    """
    Represents a directory in the schema.
    Can contain children nodes (files or other directories).
    """

    def __init__(
        self,
        path: Path,
        semantical_name: str,
        description: Optional[str] = None,
        pattern_validation: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ):
        """
        Initialize a schema directory node.

        Args:
            path: Path to this directory
            semantical_name: The semantic name of this directory in the schema
            description: Optional description of the directory
            pattern_validation: Optional regex pattern for name validation
            metadata: Optional metadata for custom validations
        """
        super().__init__(path, semantical_name, description, pattern_validation, metadata)
        self.children: list[SchemaNode] = []

    def get_type(self) -> str:
        return "directory"

    def add_child(self, child: SchemaNode) -> None:
        """
        Add a child node to this directory.

        Args:
            child: The child node (file or directory) to add
        """
        self.children.append(child)

    def get_child_by_name(self, name: str) -> Optional[SchemaNode]:
        """
        Get a child node by its semantical name.

        Args:
            name: The semantical name of the child to find

        Returns:
            The child node if found, None otherwise
        """
        for child in self.children:
            if child.semantical_name == name:
                return child
        return None

    def __repr__(self) -> str:
        """Detailed string representation of the directory node."""
        return f"{self.__class__.__name__}(path='{self.path}', semantical_name='{self.semantical_name}', children={len(self.children)})"
