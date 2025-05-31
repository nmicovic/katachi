from typing import Any, Optional

from fsspec import AbstractFileSystem

from katachi.schema.actions import ActionRegistry, ActionResult, ActionTiming, process_node
from katachi.schema.actions import NodeContext as ActionNodeContext
from katachi.schema.schema_node import SchemaDirectory, SchemaFile, SchemaNode, SchemaPredicateNode
from katachi.utils.logger import logger
from katachi.validation.core import ValidationReport, ValidationResult, ValidatorRegistry
from katachi.validation.registry import NodeRegistry


class SchemaValidator:
    """Validator for schema nodes against filesystem paths."""

    @staticmethod
    def validate_schema(
        schema: SchemaNode,
        target_path: str,
        fs: AbstractFileSystem,
        execute_actions: bool = False,
        parent_contexts: Optional[list[ActionNodeContext]] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> ValidationReport:
        """
        Validate a target path against a schema node recursively.

        Args:
            schema: Schema node to validate against
            target_path: Path to validate
            fs: Filesystem to use for validation
            execute_actions: Whether to execute registered actions
            parent_contexts: List of parent (node, path) tuples for context
            context: Additional context data

        Returns:
            ValidationReport with all validation results
        """
        # Create a registry to collect validated nodes
        registry = NodeRegistry()

        # Perform structural validation and collect nodes
        logger.debug(f"Validating schema at path: {target_path} against schema: {schema.semantical_name}")
        report = SchemaValidator._validate_structure(
            schema, target_path, fs, registry, execute_actions, parent_contexts, context
        )

        # If structural validation failed, return early
        if not report.is_valid():
            return report

        # Perform predicate evaluation using the registry
        logger.debug(f"Evaluating predicates for schema: {schema.semantical_name} at path: {target_path}")
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
        target_path: str,
        fs: AbstractFileSystem,
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
            fs: Filesystem to use for validation
            registry: Registry to collect validated nodes
            execute_actions: Whether to execute registered actions
            parent_contexts: List of parent (node, path) tuples for context
            context: Additional context data

        Returns:
            ValidationReport with structural validation results
        """
        logger.debug(f"Validating structure for schema: {schema.semantical_name} at path: {target_path}")
        # Initialize parent_contexts and context if needed
        parent_contexts = parent_contexts or []
        context = context or {}

        # Create a report to collect validation results
        report = ValidationReport()

        # Run standard validation for this node
        node_report = SchemaValidator.validate_node(schema, target_path, fs)
        logger.debug(f"Validating node: {schema.semantical_name} at path: {target_path}")
        report.add_results(node_report.results)

        # Run any custom validators
        logger.debug(f"Running custom validators for node: {schema.semantical_name} at path: {target_path}")
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
        if isinstance(schema, SchemaDirectory) and fs.isdir(target_path):
            child_paths = fs.ls(target_path)

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
                        child, child_path, fs, registry, execute_actions, parent_contexts, context
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
        target_path: str,
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
        def traverse_for_predicates(node: SchemaNode, path: str) -> None:
            if isinstance(node, SchemaPredicateNode):
                # Evaluate this predicate
                predicate_report = SchemaValidator.validate_predicate(node, path, registry)
                report.add_results(predicate_report.results)

            # Recursively check children for predicates
            if isinstance(node, SchemaDirectory):
                for child in node.children:
                    # Use the node's path to build the child path
                    child_path = (
                        f"{path}/{child.semantical_name}" if not isinstance(child, SchemaPredicateNode) else path
                    )
                    traverse_for_predicates(child, child_path)

        # Start traversal from root
        traverse_for_predicates(schema, target_path)

        return report

    @staticmethod
    def validate_node(node: SchemaNode, path: str, fs: AbstractFileSystem) -> ValidationReport:
        """
        Validate a path against a schema node.

        Args:
            node: Schema node to validate against
            path: Path to validate
            fs: Filesystem to use for validation

        Returns:
            ValidationReport with results
        """
        if isinstance(node, SchemaFile):
            return SchemaValidator.validate_file(node, path, fs)
        elif isinstance(node, SchemaDirectory):
            return SchemaValidator.validate_directory(node, path, fs)
        elif isinstance(node, SchemaPredicateNode):
            # Skip predicates during node validation, they're handled separately
            return ValidationReport()
        else:
            logger.debug(f"Creating report for unknown schema node type: {type(node).__name__} at path: {path}")
            report = ValidationReport()
            report.add_result(
                ValidationResult(
                    is_valid=False,
                    node_origin=node.semantical_name,
                    message=f"Unknown schema node type: {type(node).__name__}",
                    path=path,
                    validator_name="schema_type",
                )
            )
            return report

    @staticmethod
    def validate_file(node: SchemaFile, path: str, fs: AbstractFileSystem) -> ValidationReport:
        """
        Validate a file against a schema file node.

        Args:
            node: Schema file node to validate against
            path: Path to validate
            fs: Filesystem to use for validation

        Returns:
            ValidationReport with results
        """
        report = ValidationReport()

        # Check if path exists and is a file
        if not fs.isfile(path):
            report.add_result(
                ValidationResult(
                    is_valid=False,
                    node_origin=node.semantical_name,
                    message=f"Path does not exist or is not a file: {path}",
                    path=path,
                    validator_name="file_exists",
                )
            )
            return report

        # Check file extension
        if node.extension and not path.endswith(node.extension):
            report.add_result(
                ValidationResult(
                    is_valid=False,
                    node_origin=node.semantical_name,
                    message=f"File extension mismatch: expected {node.extension}, got {path.split('.')[-1]}",
                    path=path,
                    validator_name="file_extension",
                )
            )

        # Check pattern validation if specified
        if node.pattern_validation:
            filename = path.split("/")[-1]
            if not node.pattern_validation.match(filename):
                report.add_result(
                    ValidationResult(
                        is_valid=False,
                        node_origin=node.semantical_name,
                        message=f"Filename does not match pattern: {node.pattern_validation.pattern}",
                        path=path,
                        validator_name="file_pattern",
                    )
                )

        return report

    @staticmethod
    def validate_directory(node: SchemaDirectory, path: str, fs: AbstractFileSystem) -> ValidationReport:
        """
        Validate a directory against a schema directory node.

        Args:
            node: Schema directory node to validate against
            path: Path to validate
            fs: Filesystem to use for validation

        Returns:
            ValidationReport with results
        """
        report = ValidationReport()

        # Check if path exists and is a directory
        if not fs.isdir(path):
            report.add_result(
                ValidationResult(
                    is_valid=False,
                    node_origin=node.semantical_name,
                    message=f"Path does not exist or is not a directory: {path}",
                    path=path,
                    validator_name="directory_exists",
                )
            )
            return report

        # Check pattern validation if specified
        if node.pattern_validation:
            dirname = path.split("/")[-1]
            if not node.pattern_validation.match(dirname):
                report.add_result(
                    ValidationResult(
                        is_valid=False,
                        node_origin=node.semantical_name,
                        message=f"Directory name does not match pattern: {node.pattern_validation.pattern}",
                        path=path,
                        validator_name="directory_pattern",
                    )
                )

        return report

    @staticmethod
    def validate_predicate(
        predicate_node: SchemaPredicateNode,
        path: str,
        registry: NodeRegistry,
    ) -> ValidationReport:
        """
        Validate a predicate node against the registry of validated nodes.

        Args:
            predicate_node: Predicate node to validate
            path: Path being validated
            registry: Registry of validated nodes

        Returns:
            ValidationReport with results
        """
        report = ValidationReport()

        # Get all contexts for the elements this predicate operates on
        element_contexts = []
        for element_name in predicate_node.elements:
            contexts = registry.get_contexts_by_name(element_name)
            if not contexts:
                report.add_result(
                    ValidationResult(
                        is_valid=False,
                        node_origin=predicate_node.semantical_name,
                        message=f"Required element '{element_name}' not found in validated nodes",
                        path=path,
                        validator_name="predicate_element",
                    )
                )
                return report
            element_contexts.append(contexts)

        # TODO: Implement actual predicate validation logic
        # For now, just return a placeholder result
        report.add_result(
            ValidationResult(
                is_valid=True,
                node_origin=predicate_node.semantical_name,
                message=f"Predicate '{predicate_node.predicate_type}' validation not implemented",
                path=path,
                validator_name="predicate",
            )
        )

        return report
