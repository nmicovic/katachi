from pathlib import Path
from typing import Any, Optional

from katachi.schema.actions import ActionRegistry, ActionResult, ActionTiming, process_node
from katachi.schema.actions import NodeContext as ActionNodeContext
from katachi.schema.schema_node import SchemaDirectory, SchemaFile, SchemaNode, SchemaPredicateNode
from katachi.validation.core import ValidationReport, ValidationResult, ValidatorRegistry
from katachi.validation.registry import NodeRegistry


class SchemaValidator:
    """Validator for schema nodes against filesystem paths."""

    @staticmethod
    def validate_schema(
        schema: SchemaNode,
        target_path: Path,
        execute_actions: bool = False,
        parent_contexts: Optional[list[ActionNodeContext]] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> ValidationReport:
        """
        Validate a target path against a schema node recursively.

        Args:
            schema: Schema node to validate against
            target_path: Path to validate
            execute_actions: Whether to execute registered actions
            parent_contexts: List of parent (node, path) tuples for context
            context: Additional context data

        Returns:
            ValidationReport with all validation results
        """
        # Create a registry to collect validated nodes
        registry = NodeRegistry()

        # Perform structural validation and collect nodes
        report = SchemaValidator._validate_structure(
            schema, target_path, registry, execute_actions, parent_contexts, context
        )

        # If structural validation failed, return early
        if not report.is_valid():
            return report

        # Perform predicate evaluation using the registry
        predicate_report = SchemaValidator._evaluate_predicates(schema, target_path, registry)
        report.add_results(predicate_report.results)

        # If predicate validation failed, return early
        if not predicate_report.is_valid():
            return report

        # Execute after-validation actions if requested
        if execute_actions:
            action_results = SchemaValidator._execute_after_validation_actions(registry, context)
            # Attach action results to the report's context
            if action_results:
                report.context["action_results"] = action_results

        return report

    @staticmethod
    def _execute_after_validation_actions(
        registry: NodeRegistry, context: Optional[dict[str, Any]] = None
    ) -> list[ActionResult]:
        """
        Execute all registered actions that should run after validation.

        Args:
            registry: Registry of validated nodes
            context: Additional context data

        Returns:
            List of action results
        """
        return ActionRegistry.execute_actions(registry=registry, context=context, timing=ActionTiming.AFTER_VALIDATION)

    @staticmethod
    def _validate_structure(
        schema: SchemaNode,
        target_path: Path,
        registry: NodeRegistry,
        execute_actions: bool = False,
        parent_contexts: Optional[list[ActionNodeContext]] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> ValidationReport:
        """
        Validate the structure of a target path against a schema node.

        Args:
            schema: Schema node to validate against
            target_path: Path to validate
            registry: Registry to collect validated nodes
            execute_actions: Whether to execute registered actions
            parent_contexts: List of parent (node, path) tuples for context
            context: Additional context data

        Returns:
            ValidationReport with structural validation results
        """
        # Initialize parent_contexts and context if needed
        parent_contexts = parent_contexts or []
        context = context or {}

        # Create a report to collect validation results
        report = ValidationReport()

        # Run standard validation for this node
        node_report = SchemaValidator.validate_node(schema, target_path)
        report.add_results(node_report.results)

        # Run any custom validators
        custom_results = ValidatorRegistry.run_validators(schema, target_path)
        report.add_results(custom_results)

        # Early return if basic validation fails
        if not node_report.is_valid():
            return report

        # Node passed validation - register it
        parent_paths = [p for _, p in parent_contexts]
        registry.register_node(schema, target_path, parent_paths)

        # Execute actions if enabled and using legacy DURING_VALIDATION timing
        if execute_actions:
            process_node(schema, target_path, parent_contexts, context)

        # For directories, validate children
        if isinstance(schema, SchemaDirectory) and target_path.is_dir():
            child_paths = list(target_path.iterdir())

            # Add current node to parent contexts before processing children
            parent_contexts.append((schema, target_path))

            for child_path in child_paths:
                child_valid = False
                child_reports = []

                for child in schema.children:
                    # Skip predicate nodes during structure validation
                    if isinstance(child, SchemaPredicateNode):
                        continue

                    child_report = SchemaValidator._validate_structure(
                        child, child_path, registry, execute_actions, parent_contexts, context
                    )

                    child_reports.append(child_report)

                    if child_report.is_valid():
                        child_valid = True
                        report.add_results(child_report.results)
                        break

                if not child_valid:
                    for child_report in child_reports:
                        report.add_results(child_report.results)

            # Remove current node from parent contexts after processing all children
            parent_contexts.pop()

            # Register this directory as fully processed
            registry.register_processed_dir(target_path)

        return report

    @staticmethod
    def _evaluate_predicates(
        schema: SchemaNode,
        target_path: Path,
        registry: NodeRegistry,
    ) -> ValidationReport:
        """
        Evaluate predicates using the registry of validated nodes.

        Args:
            schema: Root schema node
            target_path: Root path
            registry: Registry of validated nodes

        Returns:
            ValidationReport with predicate evaluation results
        """
        report = ValidationReport()

        # Find and evaluate all predicate nodes
        def traverse_for_predicates(node: SchemaNode, path: Path) -> None:
            if isinstance(node, SchemaPredicateNode):
                # Evaluate this predicate
                predicate_report = SchemaValidator.validate_predicate(node, path, registry)
                report.add_results(predicate_report.results)

            # Recursively check children for predicates
            if isinstance(node, SchemaDirectory):
                for child in node.children:
                    # Use the node's path to build the child path
                    child_path = path / child.semantical_name if not isinstance(child, SchemaPredicateNode) else path
                    traverse_for_predicates(child, child_path)

        # Start traversal from the root schema
        traverse_for_predicates(schema, target_path)

        return report

    @staticmethod
    def validate_node(node: SchemaNode, path: Path) -> ValidationReport:
        """
        Validate a path against a schema node.

        Args:
            node: Schema node to validate against
            path: Path to validate

        Returns:
            ValidationReport with results
        """
        if isinstance(node, SchemaFile):
            return SchemaValidator.validate_file(node, path)
        elif isinstance(node, SchemaDirectory):
            return SchemaValidator.validate_directory(node, path)
        elif isinstance(node, SchemaPredicateNode):
            # Skip predicates during node validation, they're handled separately
            return ValidationReport()
        else:
            report = ValidationReport()
            report.add_result(
                ValidationResult(
                    is_valid=False,
                    message=f"Unknown schema node type: {type(node).__name__}",
                    path=path,
                    validator_name="schema_type",
                )
            )
            return report

    @staticmethod
    def validate_file(file_node: SchemaFile, path: Path) -> ValidationReport:
        """Validate a path against a file schema."""
        report = ValidationReport()
        context = {"node_name": file_node.semantical_name}

        # Check if it's a file
        is_file = path.is_file()
        report.add_result(
            ValidationResult(
                is_valid=is_file,
                message="" if is_file else f"Expected a file at {path}",
                path=path,
                validator_name="is_file",
                context=context,
            )
        )

        # If not a file, stop further validations
        if not is_file:
            return report

        # Check extension
        if file_node.extension:
            ext = file_node.extension if file_node.extension.startswith(".") else f".{file_node.extension}"
            has_ext = path.suffix == ext
            report.add_result(
                ValidationResult(
                    is_valid=has_ext,
                    message="" if has_ext else f'Expected extension "{ext}", got "{path.suffix}"',
                    path=path,
                    validator_name="extension",
                    context=context,
                )
            )

        # Check pattern
        if file_node.pattern_validation:
            matches_pattern = file_node.pattern_validation.fullmatch(path.stem) is not None
            report.add_result(
                ValidationResult(
                    is_valid=matches_pattern,
                    message=""
                    if matches_pattern
                    else f'{path.name} doesn\'t match pattern "{file_node.pattern_validation.pattern}"',
                    path=path,
                    validator_name="pattern",
                    context=context,
                )
            )

        return report

    @staticmethod
    def validate_directory(dir_node: SchemaDirectory, path: Path) -> ValidationReport:
        """Validate a path against a directory schema."""
        report = ValidationReport()
        context = {"node_name": dir_node.semantical_name}

        # Check if it's a directory
        is_dir = path.is_dir()
        report.add_result(
            ValidationResult(
                is_valid=is_dir,
                message="" if is_dir else f"Expected a directory at {path}",
                path=path,
                validator_name="is_directory",
                context=context,
            )
        )

        # If not a directory, stop further validations
        if not is_dir:
            return report

        # Check pattern
        if dir_node.pattern_validation:
            matches_pattern = dir_node.pattern_validation.fullmatch(path.name) is not None
            report.add_result(
                ValidationResult(
                    is_valid=matches_pattern,
                    message=""
                    if matches_pattern
                    else f'{path.name} doesn\'t match pattern "{dir_node.pattern_validation.pattern}"',
                    path=path,
                    validator_name="pattern",
                    context=context,
                )
            )

        return report

    @staticmethod
    def validate_predicate(
        predicate_node: SchemaPredicateNode,
        path: Path,
        registry: NodeRegistry,
    ) -> ValidationReport:
        """
        Validate a predicate rule.

        Args:
            predicate_node: The predicate node to validate
            path: Path to the parent directory containing the elements
            registry: Registry of validated nodes

        Returns:
            ValidationReport with results
        """
        report = ValidationReport()

        if predicate_node.predicate_type == "pair_comparison":
            # Get elements to compare
            if len(predicate_node.elements) < 2:
                report.add_result(
                    ValidationResult(
                        is_valid=False,
                        message=f"Pair comparison predicate needs at least 2 elements, got {len(predicate_node.elements)}",
                        path=path,
                        validator_name=predicate_node.semantical_name,
                    )
                )
                return report

            # Get base names from the first element type
            first_element = predicate_node.elements[0]
            first_paths = registry.get_paths_by_name(first_element)

            # Filter to only include paths under the current directory
            first_paths = [p for p in first_paths if path in p.parents or path == p.parent]

            if not first_paths:
                # No valid paths for first element, nothing to check
                return report

            base_names: set[str] = set()
            for p in first_paths:
                base_names.add(p.stem)

            # Check if other element types have matching base names
            for element_name in predicate_node.elements[1:]:
                element_paths = registry.get_paths_by_name(element_name)

                # Filter to only include paths under the current directory
                element_paths = [p for p in element_paths if path in p.parents or path == p.parent]

                element_stems = {p.stem for p in element_paths}

                # Find mismatches
                missing_pairs = base_names - element_stems
                if missing_pairs:
                    missing_list = ", ".join(sorted(missing_pairs))
                    report.add_result(
                        ValidationResult(
                            is_valid=False,
                            message=f"Missing paired {element_name} files for: {missing_list}",
                            path=path,
                            validator_name=f"pair_comparison_{predicate_node.semantical_name}",
                        )
                    )

        else:
            # Unsupported predicate type
            report.add_result(
                ValidationResult(
                    is_valid=False,
                    message=f"Unsupported predicate type: {predicate_node.predicate_type}",
                    path=path,
                    validator_name="predicate_validation",
                )
            )

        return report
