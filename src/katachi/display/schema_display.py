from rich.tree import Tree

from katachi.schema.schema_node import SchemaNode


def create_schema_tree(schema: SchemaNode) -> Tree:
    """
    Create a rich tree visualization of a schema.

    Args:
        schema: The root schema node

    Returns:
        A rich Tree object representing the schema structure
    """
    tree = Tree(f"[bold green]{schema.semantical_name}[/] [dim]({schema.get_type()})[/]")
    _add_node_to_tree(schema, tree)
    return tree


def _add_node_to_tree(node: SchemaNode, tree: Tree) -> None:
    """
    Recursively add schema nodes to the tree.

    Args:
        node: The schema node to add
        tree: The tree or branch to add the node to
    """
    # Add details about this node
    _add_node_details(node, tree)

    # If it's a directory, add its children
    if hasattr(node, "children") and node.children:
        children_branch = tree.add("[bold blue]Children[/]")
        for child in node.children:
            # Create a child branch with type-specific styling
            if child.get_type() == "directory":
                icon = "📁"
                style = "green"
            elif child.get_type() == "file":
                icon = "📄"
                style = "yellow"
            elif child.get_type() == "predicate":
                icon = "🔗"
                style = "magenta"
            else:
                icon = "❓"
                style = "white"

            child_branch = children_branch.add(
                f"{icon} [bold {style}]{child.semantical_name}[/] [dim]({child.get_type()})[/]"
            )
            _add_node_to_tree(child, child_branch)


def _add_node_details(node: SchemaNode, tree: Tree) -> None:
    """
    Add details about a schema node to the tree.

    Args:
        node: The schema node to describe
        tree: The tree branch to add details to
    """
    details_branch = tree.add("[bold cyan]Details[/]")

    # Add description if available
    if node.description:
        details_branch.add(f"[italic]Description:[/] {node.description}")

    # Add pattern validation if present
    if node.pattern_validation:
        details_branch.add(f"[yellow]Pattern:[/] {node.pattern_validation.pattern}")

    # Add type-specific details
    if node.get_type() == "file" and hasattr(node, "extension"):
        extension = node.extension
        if extension:
            ext = extension if extension.startswith(".") else f".{extension}"
            details_branch.add(f"[blue]Extension:[/] {ext}")

    # Add predicate-specific details
    if node.get_type() == "predicate" and hasattr(node, "predicate_type"):
        predicate_type = node.predicate_type
        elements = getattr(node, "elements", [])
        details_branch.add(f"[magenta]Predicate Type:[/] {predicate_type}")
        if elements:
            elements_str = ", ".join(elements)
            details_branch.add(f"[magenta]Elements:[/] {elements_str}")

    # Add any custom metadata
    if node.metadata and len(node.metadata) > 0:
        metadata_branch = details_branch.add("[bold]Metadata[/]")
        for key, value in node.metadata.items():
            metadata_branch.add(f"[dim]{key}:[/] {value}")
