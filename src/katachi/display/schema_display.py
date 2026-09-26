from __future__ import annotations

from rich.markup import escape
from rich.tree import Tree

from katachi.schema.schema_node import SchemaDirectory, SchemaFile, SchemaNode, SchemaPredicateNode


def _cardinality(node: SchemaNode) -> str:
    minimum, maximum = node.effective_min_count, node.max_count
    if minimum == 0 and maximum is None:
        return ""
    upper = "*" if maximum is None else str(maximum)
    return f"[{minimum}..{upper}]" if str(minimum) != upper else f"[{minimum}]"


def _label(node: SchemaNode) -> str:
    if isinstance(node, SchemaPredicateNode):
        call = f"{node.predicate_type}({', '.join(node.elements)})"
        label = f"🔗 [bold magenta]{escape(node.semantical_name)}[/] [magenta]{escape(call)}[/]"
    else:
        icon, style = ("📁", "green") if isinstance(node, SchemaDirectory) else ("📄", "yellow")
        label = f"{icon} [bold {style}]{escape(node.semantical_name)}[/] [cyan]{escape(node.describe_constraints())}[/]"
        extras = [_cardinality(node)]
        if node.name_case:
            extras.append(node.name_case)
        if isinstance(node, SchemaFile) and (node.min_size is not None or node.max_size is not None):
            extras.append(f"size {node.min_size or 0}..{node.max_size if node.max_size is not None else '*'}")
        if node.permissions:
            extras.append(f"mode {node.permissions}")
        if node.owner:
            extras.append(f"owner {node.owner}")
        if isinstance(node, SchemaDirectory):
            if node.ignore:
                extras.append(f"ignore {', '.join(node.ignore)}")
            if node.allow_extra:
                extras.append("allow extra")
            if not node.structural_children:
                extras.append("any content")
        extras = [e for e in extras if e]
        if extras:
            label += f" [dim]{escape(' · '.join(extras))}[/]"
    if node.severity != "error":
        label += f" [yellow]({node.severity})[/]"
    if node.description:
        label += f"\n[italic dim]{escape(node.description)}[/]"
    return label


def create_schema_tree(schema: SchemaNode) -> Tree:
    """
    Create a compact rich tree visualization of a schema.

    Every line shows the node's semantical name, the name pattern + extension it accepts,
    its cardinality (``[1..*]``) and other constraints.

    Args:
        schema: The root schema node

    Returns:
        A rich Tree object representing the schema structure
    """
    tree = Tree(_label(schema))
    _add_children(schema, tree)
    return tree


def _add_children(node: SchemaNode, tree: Tree) -> None:
    if isinstance(node, SchemaDirectory):
        for child in node.children:
            _add_children(child, tree.add(_label(child)))
