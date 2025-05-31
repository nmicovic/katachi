from abc import ABC, abstractmethod
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
        path: str,
        semantical_name: str,
        description: Optional[str] = None,
        pattern_validation: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        permissions: Optional[str] = None,
        owner: Optional[str] = None,
    ):
        """
        Initialize a schema node.

        Args:
            path: Path to this node
            semantical_name: The semantic name of this node in the schema
            description: Optional description of the node
            pattern_validation: Optional regex pattern for name validation
            metadata: Optional metadata for custom validations
            permissions: Optional Unix-style permissions string (e.g., "0750")
            owner: Optional expected owner of the file/directory
        """
        self.path: str = path
        self.semantical_name: str = semantical_name
        self.description: Optional[str] = description
        self.pattern_validation: Optional[Pattern] = None
        self.metadata: dict[str, Any] = metadata or {}
        self.permissions: Optional[str] = permissions
        self.owner: Optional[str] = owner

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

    @classmethod
    def from_dict(cls, data: dict[str, Any], parent_path: str) -> Optional["SchemaNode"]:
        """
        Create a SchemaNode instance from a dictionary.

        Args:
            data: Dictionary containing node data
            parent_path: Path to the parent directory

        Returns:
            Optional[SchemaNode]: The created node or None if the data is invalid
        """
        node_type = data.get("type", "").lower()
        semantical_name = data.get("semantical_name", "")
        description = data.get("description")
        pattern_validation = data.get("pattern_name")
        permissions = data.get("permissions")
        owner = data.get("owner")
        metadata = data.get("metadata")

        node_path = f"{parent_path}/{semantical_name}" if semantical_name else parent_path

        if node_type == "file":
            extension = data.get("extension", "")
            return SchemaFile(
                path=node_path,
                semantical_name=semantical_name,
                extension=extension,
                description=description,
                pattern_validation=pattern_validation,
                metadata=metadata,
                permissions=permissions,
                owner=owner,
            )
        elif node_type == "directory":
            directory = SchemaDirectory(
                path=node_path,
                semantical_name=semantical_name,
                description=description,
                pattern_validation=pattern_validation,
                metadata=metadata,
                permissions=permissions,
                owner=owner,
            )
            children = data.get("children", [])
            for child_data in children:
                child_node = cls.from_dict(child_data, node_path)
                if child_node:
                    directory.add_child(child_node)
            return directory
        elif node_type == "predicate":
            predicate_type = data.get("predicate_type", "")
            elements = data.get("elements", [])
            if not predicate_type or not elements:
                return None
            return SchemaPredicateNode(
                path=node_path,
                semantical_name=semantical_name,
                predicate_type=predicate_type,
                elements=elements,
                description=description,
                metadata=metadata,
                permissions=permissions,
                owner=owner,
            )
        else:
            return None


class SchemaFile(SchemaNode):
    """
    Represents a file in the schema.
    """

    def __init__(
        self,
        path: str,
        semantical_name: str,
        extension: str,
        description: Optional[str] = None,
        pattern_validation: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        permissions: Optional[str] = None,
        owner: Optional[str] = None,
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
            permissions: Optional Unix-style permissions string (e.g., "0750")
            owner: Optional expected owner of the file
        """
        super().__init__(path, semantical_name, description, pattern_validation, metadata, permissions, owner)
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
        path: str,
        semantical_name: str,
        description: Optional[str] = None,
        pattern_validation: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        permissions: Optional[str] = None,
        owner: Optional[str] = None,
    ):
        """
        Initialize a schema directory node.

        Args:
            path: Path to this directory
            semantical_name: The semantic name of this directory in the schema
            description: Optional description of the directory
            pattern_validation: Optional regex pattern for name validation
            metadata: Optional metadata for custom validations
            permissions: Optional Unix-style permissions string (e.g., "0750")
            owner: Optional expected owner of the directory
        """
        super().__init__(path, semantical_name, description, pattern_validation, metadata, permissions, owner)
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


class SchemaPredicateNode(SchemaNode):
    """
    Represents a predicate node in the schema.
    Used for validating relationships between other schema nodes.
    """

    def __init__(
        self,
        path: str,
        semantical_name: str,
        predicate_type: str,
        elements: list[str],
        description: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        permissions: Optional[str] = None,
        owner: Optional[str] = None,
    ):
        """
        Initialize a schema predicate node.

        Args:
            path: Path to this node
            semantical_name: The semantic name of this node in the schema
            predicate_type: Type of predicate (e.g., 'pair_comparison')
            elements: List of semantical names of nodes this predicate operates on
            description: Optional description of the predicate
            metadata: Optional metadata for custom validations
            permissions: Optional Unix-style permissions string (e.g., "0750")
            owner: Optional expected owner of the predicate node
        """
        super().__init__(path, semantical_name, description, None, metadata, permissions, owner)
        self.predicate_type: str = predicate_type
        self.elements: list[str] = elements

    def get_type(self) -> str:
        return "predicate"

    def __repr__(self) -> str:
        """Detailed string representation of the predicate node."""
        return f"{self.__class__.__name__}(path='{self.path}', semantical_name='{self.semantical_name}', predicate_type='{self.predicate_type}')"
