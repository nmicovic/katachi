from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from fnmatch import fnmatchcase
from re import Pattern
from re import compile as re_compile
from re import error as re_error
from re import escape as re_escape
from typing import Any

#: ``{name}`` placeholders in patterns refer to named groups captured by ancestor patterns
PLACEHOLDER = re_compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

SEVERITIES = ("error", "warning", "info")

NAME_CASES: dict[str, str] = {
    "snake_case": r"[a-z0-9]+(?:_[a-z0-9]+)*",
    "kebab-case": r"[a-z0-9]+(?:-[a-z0-9]+)*",
    "camelCase": r"[a-z][a-zA-Z0-9]*",
    "PascalCase": r"[A-Z][a-zA-Z0-9]*",
    "SCREAMING_SNAKE_CASE": r"[A-Z0-9]+(?:_[A-Z0-9]+)*",
    "lowercase": r"[^A-Z]*",
    "UPPERCASE": r"[^a-z]*",
}


def template_to_regex(pattern: str) -> str:
    """Replace ``{name}`` placeholders with a generic wildcard (used for prefiltering and checks)."""
    return PLACEHOLDER.sub(".+", pattern)


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
        description: str | None = None,
        pattern_validation: str | Pattern | None = None,
        metadata: dict[str, Any] | None = None,
        permissions: str | None = None,
        owner: str | None = None,
        required: bool = False,
        min_count: int | None = None,
        max_count: int | None = None,
        severity: str = "error",
        name_case: str | None = None,
    ):
        """
        Initialize a schema node.

        Args:
            path: Path to this node
            semantical_name: The semantic name of this node in the schema
            description: Optional description of the node
            pattern_validation: Optional regex pattern the entry name must fully match
            metadata: Optional metadata for custom validations
            permissions: Optional Unix-style permissions string (e.g., "0750")
            owner: Optional expected owner (user name or numeric uid) of the file/directory
            required: Whether at least one matching entry must exist in the parent directory
            min_count: Minimum number of matching entries in the parent directory
            max_count: Maximum number of matching entries in the parent directory
            severity: Severity of count violations reported for this node ("error", "warning" or "info")
            name_case: Optional naming convention the name must follow (see ``NAME_CASES``)
        """
        self.path: str = path
        self.semantical_name: str = semantical_name
        self.description: str | None = description
        self.pattern_validation: Pattern | None = None
        self.metadata: dict[str, Any] = metadata or {}
        self.permissions: str | None = permissions
        self.owner: str | None = owner
        self.required: bool = required
        self.min_count: int | None = min_count
        self.max_count: int | None = max_count

        self.severity: str = severity
        self.name_case: str | None = name_case
        self.name_case_regex: Pattern | None = re_compile(NAME_CASES[name_case]) if name_case else None
        #: Names of the ``{placeholders}`` used in the pattern
        self.template_vars: tuple[str, ...] = ()
        self.pattern_template: str | None = None
        self._resolved_patterns: dict[tuple[str, ...], Pattern] = {}

        if pattern_validation is not None:
            if isinstance(pattern_validation, Pattern):
                self.pattern_validation = pattern_validation
            else:
                self.template_vars = tuple(dict.fromkeys(PLACEHOLDER.findall(pattern_validation)))
                if self.template_vars:
                    self.pattern_template = pattern_validation
                    self.pattern_validation = re_compile(template_to_regex(pattern_validation))
                else:
                    self.pattern_validation = re_compile(pattern_validation)

    @abstractmethod
    def get_type(self) -> str:
        """
        Get the type of this node.

        Returns:
            String representing the node type ("file", "directory" or "predicate").
        """

    @property
    def effective_min_count(self) -> int:
        """Minimum number of entries that must match this node inside a parent directory instance."""
        if self.min_count is not None:
            return self.min_count
        return 1 if self.required else 0

    @property
    def expected_mode(self) -> int | None:
        """Expected permission bits as an integer, parsed from the octal permissions string."""
        return int(str(self.permissions), 8) if self.permissions is not None else None

    def name_matches(self, name: str) -> bool:
        """Check whether a name fully matches this node's pattern (always true when no pattern is set)."""
        return self.pattern_validation is None or self.pattern_validation.fullmatch(name) is not None

    def resolve_pattern(self, scope: dict[str, str] | None = None) -> Pattern | None:
        """
        The pattern to match names against, with ``{placeholders}`` substituted from ``scope``.

        Args:
            scope: Values captured by named groups of ancestor patterns
        """
        if not self.template_vars or self.pattern_template is None:
            return self.pattern_validation
        scope = scope or {}
        key = tuple(scope.get(v, "") for v in self.template_vars)
        pattern = self._resolved_patterns.get(key)
        if pattern is None:
            template = self.pattern_template

            def substitute(m: Any) -> str:
                value = scope.get(m.group(1))
                return re_escape(value) if value is not None else ".+"

            pattern = re_compile(PLACEHOLDER.sub(substitute, template))
            self._resolved_patterns[key] = pattern
        return pattern

    @property
    def has_exact_prefilter(self) -> bool:
        """Whether the name can be checked with a single static regex (no templates or case rules)."""
        return not self.template_vars and self.name_case_regex is None

    @property
    def pattern_source(self) -> str | None:
        """The pattern as written in the schema (including ``{placeholders}``)."""
        if self.pattern_template is not None:
            return self.pattern_template
        return self.pattern_validation.pattern if self.pattern_validation else None

    def describe_constraints(self) -> str:
        """Short human readable summary of what this node accepts, e.g. ``img\\d+.jpg``."""
        return self.pattern_source or "*"

    def iter_nodes(self) -> Iterator[SchemaNode]:
        """Iterate over this node and all of its descendants (depth first)."""
        yield self

    def __str__(self) -> str:
        """String representation of the node."""
        return f"{self.get_type()}: {self.semantical_name} at {self.path}"

    def __repr__(self) -> str:
        """Detailed string representation of the node."""
        return f"{self.__class__.__name__}(path='{self.path}', semantical_name='{self.semantical_name}')"

    @classmethod
    def from_dict(cls, data: dict[str, Any], parent_path: str) -> SchemaNode | None:
        """
        Create a SchemaNode instance from a dictionary.

        Args:
            data: Dictionary containing node data
            parent_path: Path to the parent directory

        Returns:
            The created node or None if the data is invalid
        """
        from katachi.schema.importer import SchemaError, parse_node

        try:
            return parse_node(data, parent_path)
        except SchemaError:
            return None


def normalize_extension(extension: str) -> str:
    """Normalize an extension so that it always starts with a dot (``jpg`` -> ``.jpg``)."""
    extension = extension.strip()
    return extension if extension.startswith(".") else f".{extension}"


class SchemaFile(SchemaNode):
    """
    Represents a file in the schema.
    """

    def __init__(
        self,
        path: str,
        semantical_name: str,
        extension: str | Sequence[str] | None = "",
        description: str | None = None,
        pattern_validation: str | Pattern | None = None,
        metadata: dict[str, Any] | None = None,
        permissions: str | None = None,
        owner: str | None = None,
        required: bool = False,
        min_count: int | None = None,
        max_count: int | None = None,
        min_size: int | None = None,
        max_size: int | None = None,
        severity: str = "error",
        name_case: str | None = None,
    ):
        """
        Initialize a schema file node.

        Args:
            path: Path to this file
            semantical_name: The semantic name of this file in the schema
            extension: The file extension, or a list of accepted extensions
            description: Optional description of the file
            pattern_validation: Optional regex pattern the file name (without extension) must fully match
            metadata: Optional metadata for custom validations
            permissions: Optional Unix-style permissions string (e.g., "0640")
            owner: Optional expected owner of the file
            required: Whether at least one matching file must exist
            min_count: Minimum number of matching files in the parent directory
            max_count: Maximum number of matching files in the parent directory
            min_size: Minimum file size in bytes
            max_size: Maximum file size in bytes
        """
        super().__init__(
            path,
            semantical_name,
            description,
            pattern_validation,
            metadata,
            permissions,
            owner,
            required,
            min_count,
            max_count,
            severity,
            name_case,
        )
        raw_extensions = ([extension] if extension else []) if isinstance(extension, str) else list(extension or [])
        # Longest first, so that ".tar.gz" wins over ".gz"
        declared = list(dict.fromkeys(normalize_extension(e) for e in raw_extensions if e))
        #: Accepted extensions, longest first (so ".tar.gz" wins over ".gz"), otherwise in declared order
        self.extensions: tuple[str, ...] = tuple(sorted(declared, key=lambda e: (-len(e), declared.index(e))))
        #: Accepted extensions in the order they were declared (used in messages)
        self.declared_extensions: tuple[str, ...] = tuple(declared)
        self.min_size: int | None = min_size
        self.max_size: int | None = max_size
        self._fast_check: tuple[bool, Pattern | None] | None = None

    def _get_fast_check(self) -> tuple[bool, Pattern | None]:
        if self._fast_check is None:
            if not self.has_exact_prefilter:
                self._fast_check = (False, None)
            elif self.pattern_validation is None and not self.extensions:
                self._fast_check = (True, None)
            else:
                stem = self.pattern_validation.pattern if self.pattern_validation else ".*"
                exts = "|".join(re_escape(e) for e in self.extensions)
                try:
                    self._fast_check = (True, re_compile(f"(?:{stem})(?:{exts})" if exts else f"(?:{stem})"))
                except re_error:
                    # e.g. patterns with global inline flags, which can't be embedded; use accepts_name()
                    self._fast_check = (False, None)
        return self._fast_check

    @property
    def name_regex(self) -> Pattern | None:
        """
        A single regex fully matching valid file names (pattern + extension), used as a fast path.

        None when every name is accepted (or when :attr:`has_fast_name_check` is false).
        """
        return self._get_fast_check()[1]

    @property
    def has_fast_name_check(self) -> bool:
        """Whether :attr:`name_regex` exactly decides name validity."""
        return self._get_fast_check()[0]

    def accepts_name(self, name: str) -> bool:
        """Whether a file name satisfies the pattern and extension constraints."""
        for ext in self.extensions or ("",):
            if ext and not (name.endswith(ext) and len(name) > len(ext)):
                continue
            stem = name[: -len(ext)] if ext else name
            if self.name_matches(stem):
                return True
        return False

    @property
    def extension(self) -> str:
        """The (first) expected extension, kept for backwards compatibility."""
        return self.extensions[0] if len(self.extensions) == 1 else ", ".join(self.declared_extensions)

    def get_type(self) -> str:
        return "file"

    def split_name(self, name: str) -> tuple[str, str] | None:
        """
        Split a file name into ``(stem, extension)`` according to the declared extensions.

        Returns:
            The split name, or None when the name has none of the declared extensions.
            When no extension is declared, the whole name is the stem.
        """
        if not self.extensions:
            return name, ""
        for ext in self.extensions:
            if name.endswith(ext) and len(name) > len(ext):
                return name[: -len(ext)], ext
        return None

    def describe_constraints(self) -> str:
        pattern = self.pattern_source or "*"
        if not self.extensions:
            return pattern
        exts = self.extensions[0] if len(self.extensions) == 1 else "{" + ",".join(self.declared_extensions) + "}"
        return f"{pattern}{exts}"

    def __repr__(self) -> str:
        """Detailed string representation of the file node."""
        return f"{self.__class__.__name__}(path='{self.path}', semantical_name='{self.semantical_name}', extension='{self.extension}')"


class SchemaDirectory(SchemaNode):
    """
    Represents a directory in the schema.
    Can contain children nodes (files, other directories or predicates).
    """

    def __init__(
        self,
        path: str,
        semantical_name: str,
        description: str | None = None,
        pattern_validation: str | Pattern | None = None,
        metadata: dict[str, Any] | None = None,
        permissions: str | None = None,
        owner: str | None = None,
        required: bool = False,
        min_count: int | None = None,
        max_count: int | None = None,
        ignore: Sequence[str] | None = None,
        allow_extra: bool = False,
        severity: str = "error",
        name_case: str | None = None,
    ):
        """
        Initialize a schema directory node.

        Args:
            path: Path to this directory
            semantical_name: The semantic name of this directory in the schema
            description: Optional description of the directory
            pattern_validation: Optional regex pattern the directory name must fully match
            metadata: Optional metadata for custom validations
            permissions: Optional Unix-style permissions string (e.g., "0750")
            owner: Optional expected owner of the directory
            required: Whether at least one matching directory must exist
            min_count: Minimum number of matching directories in the parent directory
            max_count: Maximum number of matching directories in the parent directory
            ignore: Glob patterns of entry names that are skipped inside this directory
            allow_extra: Whether entries that match no child are allowed (instead of reported)
        """
        super().__init__(
            path,
            semantical_name,
            description,
            pattern_validation,
            metadata,
            permissions,
            owner,
            required,
            min_count,
            max_count,
            severity,
            name_case,
        )
        self.children: list[SchemaNode] = []
        self.ignore: list[str] = list(ignore or [])
        self.allow_extra: bool = allow_extra

    def get_type(self) -> str:
        return "directory"

    def add_child(self, child: SchemaNode) -> None:
        """
        Add a child node to this directory.

        Args:
            child: The child node (file, directory or predicate) to add
        """
        self.children.append(child)

    @property
    def structural_children(self) -> list[SchemaNode]:
        """Children describing files and directories (i.e. everything except predicates)."""
        return [c for c in self.children if not isinstance(c, SchemaPredicateNode)]

    @property
    def predicates(self) -> list[SchemaPredicateNode]:
        """Predicate children of this directory."""
        return [c for c in self.children if isinstance(c, SchemaPredicateNode)]

    def is_ignored(self, name: str) -> bool:
        """Check whether an entry name matches one of this directory's ignore globs."""
        return any(fnmatchcase(name, pattern) for pattern in self.ignore)

    def get_child_by_name(self, name: str) -> SchemaNode | None:
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

    def iter_nodes(self) -> Iterator[SchemaNode]:
        yield self
        for child in self.children:
            yield from child.iter_nodes()

    def __repr__(self) -> str:
        """Detailed string representation of the directory node."""
        return f"{self.__class__.__name__}(path='{self.path}', semantical_name='{self.semantical_name}', children={len(self.children)})"


class SchemaPredicateNode(SchemaNode):
    """
    Represents a predicate node in the schema.
    Used for validating relationships between other schema nodes.

    A predicate is evaluated once for every directory instance matched by the
    schema directory it is declared in, and only sees elements inside that instance.
    """

    def __init__(
        self,
        path: str,
        semantical_name: str,
        predicate_type: str,
        elements: list[str],
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
        permissions: str | None = None,
        owner: str | None = None,
        options: dict[str, Any] | None = None,
        severity: str = "error",
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
            permissions: Unused, kept for backwards compatibility
            owner: Unused, kept for backwards compatibility
            options: Predicate specific options
            severity: Severity of the violations this predicate reports
        """
        super().__init__(path, semantical_name, description, None, metadata, permissions, owner, severity=severity)
        self.predicate_type: str = predicate_type
        self.elements: list[str] = elements
        self.options: dict[str, Any] = options or {}

    def get_type(self) -> str:
        return "predicate"

    def __repr__(self) -> str:
        """Detailed string representation of the predicate node."""
        return f"{self.__class__.__name__}(path='{self.path}', semantical_name='{self.semantical_name}', predicate_type='{self.predicate_type}')"
