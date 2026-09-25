"""
Validation engine.

Validation happens in three phases:

1. **Structure** - the directory tree is matched against the schema. Every entry of a
   directory must match one of the schema children (trying them in order and
   backtracking when a candidate fails deeper down), and every child must be matched the
   required number of times (``required`` / ``min_count`` / ``max_count``).
2. **Predicates** - relationships between matched entries (e.g. paired files) are checked,
   scoped to the directory instance the predicate is declared in.
3. **Actions** - registered callbacks run for matched entries.

Only the matches that were finally chosen are registered, so predicates and actions never
see entries from discarded alternatives.
"""

from __future__ import annotations

import gc
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from fnmatch import fnmatchcase
from re import Pattern
from typing import Any

from fsspec import AbstractFileSystem

from katachi.schema.actions import ActionRegistry, ActionResult, ActionTiming
from katachi.schema.actions import NodeContext as ActionNodeContext
from katachi.schema.schema_node import SchemaDirectory, SchemaFile, SchemaNode, SchemaPredicateNode
from katachi.utils.logger import logger
from katachi.validation.core import ValidationReport, ValidationResult, ValidatorRegistry
from katachi.validation.predicates import PredicateRegistry
from katachi.validation.registry import NodeContext, NodeRegistry
from katachi.validation.snapshot import Entry, FsSnapshot, is_local

DEFAULT_REMOTE_WORKERS = 16

Parents = tuple[tuple[SchemaNode, str], ...]


Scope = dict[str, str]

#: A committed match: (node, path, parents, captures)
_Binding = tuple[SchemaNode, str, Parents, Scope]


class _Match:
    __slots__ = ("bindings", "issues", "local_failed", "ok")

    def __init__(
        self,
        ok: bool,
        issues: list[ValidationResult] | None = None,
        bindings: list[_Binding] | None = None,
        local_failed: bool = False,
    ):
        self.ok = ok
        self.issues = issues if issues is not None else []
        self.bindings = bindings if bindings is not None else []
        self.local_failed = local_failed


def _issue(
    node: SchemaNode, path: str, validator: str, message: str, severity: str = "error", **context: Any
) -> ValidationResult:
    return ValidationResult(
        is_valid=False,
        message=message,
        path=path,
        validator_name=validator,
        node_origin=node.semantical_name,
        context=context or None,
        severity=severity,
    )


def _has_errors(issues: list[ValidationResult]) -> bool:
    return any(i.severity == "error" for i in issues)


def _kind(node: SchemaNode) -> str:
    return "directory" if isinstance(node, SchemaDirectory) else "file"


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"  # pragma: no cover


def _owner_name(uid: int) -> str | None:
    try:
        import pwd
    except ImportError:  # pragma: no cover - not available on Windows
        return None
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return None


def _needs_metadata(node: SchemaNode) -> bool:
    if node.permissions is not None or node.owner is not None:
        return True
    return isinstance(node, SchemaFile) and (node.min_size is not None or node.max_size is not None)


class _ChildPlan:
    """Precomputed matching strategy for one schema child."""

    __slots__ = ("exact", "kind", "leaf", "node", "regex")

    def __init__(self, node: SchemaNode, has_custom_validators: bool):
        self.node = node
        self.kind = _kind(node)
        self.regex: Pattern | None
        if isinstance(node, SchemaFile):
            #: whether ``kind`` + ``regex`` exactly decide if the name/type part of the checks pass
            self.exact = node.has_fast_name_check
            self.regex = node.name_regex
        else:
            self.exact = node.has_exact_prefilter
            self.regex = node.pattern_validation
        is_leaf = not (isinstance(node, SchemaDirectory) and node.structural_children)
        #: whether a prefilter hit is a complete match (nothing else to check)
        self.leaf = self.exact and is_leaf and not _needs_metadata(node) and not has_custom_validators


class _Matcher:
    """Matches a filesystem snapshot against a schema tree."""

    def __init__(self, snapshot: FsSnapshot, ignore: Sequence[str] = ()):
        self.snapshot = snapshot
        self.ignore = list(ignore)
        self.entries_checked = 0
        self._warned_unsupported: set[str] = set()
        self._has_custom_validators = bool(ValidatorRegistry.names())
        self._plans: dict[int, list[_ChildPlan]] = {}

    # -- local checks ---------------------------------------------------------------

    def local_issues(
        self, node: SchemaNode, entry: Entry, scope: Scope | None = None
    ) -> tuple[list[ValidationResult], Scope | None]:
        """
        Checks that only look at the entry itself (type, name, extension, size, permissions, owner).

        Returns:
            The issues, and the named groups captured by the node's pattern
        """
        if isinstance(node, SchemaFile):
            issues, captures = self._file_issues(node, entry, scope)
        elif isinstance(node, SchemaDirectory):
            issues, captures = self._directory_issues(node, entry, scope)
        else:
            return [_issue(node, entry.path, "schema_type", f"Unknown schema node type: {type(node).__name__}")], None
        if issues:
            return issues, None
        return self._metadata_issues(node, entry), captures

    def _name_issues(
        self, node: SchemaNode, entry: Entry, name: str, scope: Scope | None, validator: str, label: str
    ) -> tuple[list[ValidationResult], Scope | None]:
        captures: Scope | None = None
        pattern = node.resolve_pattern(scope)
        if pattern is not None:
            m = pattern.fullmatch(name)
            if m is None:
                return [
                    _issue(
                        node,
                        entry.path,
                        validator,
                        f"{label} does not match pattern: {pattern.pattern} (got '{name}')",
                    )
                ], None
            if pattern.groupindex:
                captures = {k: v for k, v in m.groupdict().items() if v is not None}
        if node.name_case_regex is not None and node.name_case_regex.fullmatch(name) is None:
            return [_issue(node, entry.path, "name_case", f"{label} '{name}' is not {node.name_case}")], None
        return [], captures

    def _file_issues(
        self, node: SchemaFile, entry: Entry, scope: Scope | None
    ) -> tuple[list[ValidationResult], Scope | None]:
        if not entry.is_file:
            return [
                _issue(node, entry.path, "file_exists", f"Expected a file but '{entry.name}' is a {entry.type}")
            ], None
        issues: list[ValidationResult] = []
        captures: Scope | None = None
        stems = [entry.name[: -len(e)] for e in node.extensions if entry.name.endswith(e) and len(entry.name) > len(e)]
        if node.extensions and not stems:
            actual = f".{entry.name.rsplit('.', 1)[-1]}" if "." in entry.name else "no extension"
            expected = " or ".join(node.declared_extensions)
            issues.append(
                _issue(
                    node, entry.path, "file_extension", f"File extension mismatch: expected {expected}, got {actual}"
                )
            )
            stems = [entry.name.rsplit(".", 1)[0] if "." in entry.name else entry.name]
        elif not node.extensions:
            stems = [entry.name]
        name_issues: list[ValidationResult] = []
        for stem in stems:
            name_issues, captures = self._name_issues(node, entry, stem, scope, "file_pattern", "Filename")
            if not name_issues:
                break
        issues.extend(name_issues)
        if (node.min_size is not None or node.max_size is not None) and entry.size is not None:
            if node.min_size is not None and entry.size < node.min_size:
                issues.append(
                    _issue(
                        node,
                        entry.path,
                        "file_size",
                        f"File is too small: {_format_size(entry.size)} < minimum {_format_size(node.min_size)}",
                    )
                )
            if node.max_size is not None and entry.size > node.max_size:
                issues.append(
                    _issue(
                        node,
                        entry.path,
                        "file_size",
                        f"File is too large: {_format_size(entry.size)} > maximum {_format_size(node.max_size)}",
                    )
                )
        return issues, captures

    def _directory_issues(
        self, node: SchemaDirectory, entry: Entry, scope: Scope | None
    ) -> tuple[list[ValidationResult], Scope | None]:
        if not entry.is_dir:
            return [
                _issue(
                    node, entry.path, "directory_exists", f"Expected a directory but '{entry.name}' is a {entry.type}"
                )
            ], None
        return self._name_issues(node, entry, entry.name, scope, "directory_pattern", "Directory name")

    def _warn_unsupported(self, what: str) -> None:
        if what not in self._warned_unsupported:
            self._warned_unsupported.add(what)
            logger.warning(f"The filesystem does not report {what}; '{what}' checks are skipped")

    def _metadata_issues(self, node: SchemaNode, entry: Entry) -> list[ValidationResult]:
        issues = []
        expected_mode = node.expected_mode
        if expected_mode is not None:
            if entry.mode is None:
                self._warn_unsupported("permissions")
            else:
                actual = entry.mode & 0o7777
                if actual != expected_mode:
                    issues.append(
                        _issue(
                            node,
                            entry.path,
                            "permissions",
                            f"Expected permissions {expected_mode:04o}, got {actual:04o}",
                        )
                    )
        if node.owner is not None:
            if entry.uid is None:
                self._warn_unsupported("owner")
            else:
                owner_name = _owner_name(entry.uid)
                if node.owner not in (owner_name, str(entry.uid)):
                    shown = f"{owner_name} (uid {entry.uid})" if owner_name else f"uid {entry.uid}"
                    issues.append(_issue(node, entry.path, "owner", f"Expected owner {node.owner}, got {shown}"))
        return issues

    # -- matching -------------------------------------------------------------------

    def match(self, node: SchemaNode, entry: Entry, parents: Parents, scope: Scope | None = None) -> _Match:
        """Match an entry (and, for directories, its whole subtree) against a node."""
        scope = scope if scope is not None else {}
        issues, captures = self.local_issues(node, entry, scope)
        if issues:
            return _Match(False, issues, local_failed=True)
        if self._has_custom_validators:
            custom = [r for r in ValidatorRegistry.run_validators(node, entry.path) if not r.is_valid]
            if _has_errors(custom):
                return _Match(False, custom)
            issues = custom
        if captures:
            scope = {**scope, **captures}

        result = _Match(True, issues, [(node, entry.path, parents, scope)])
        if isinstance(node, SchemaDirectory) and node.structural_children:
            self._match_children(node, entry, (*parents, (node, entry.path)), scope, result)
            result.ok = not _has_errors(result.issues)
        return result

    def _plan(self, node: SchemaDirectory) -> list[_ChildPlan]:
        plan = self._plans.get(id(node))
        if plan is None:
            plan = [_ChildPlan(c, self._has_custom_validators) for c in node.structural_children]
            self._plans[id(node)] = plan
        return plan

    def _is_ignored(self, node: SchemaDirectory, name: str) -> bool:
        return node.is_ignored(name) or any(fnmatchcase(name, pattern) for pattern in self.ignore)

    def _match_children(
        self, node: SchemaDirectory, entry: Entry, parents: Parents, scope: Scope, result: _Match
    ) -> None:
        try:
            child_entries = self.snapshot.listdir(entry.path)
        except OSError as e:
            result.issues.append(_issue(node, entry.path, "directory_listing", f"Cannot list directory: {e}"))
            return

        plan = self._plan(node)
        counts = [0] * len(plan)
        check_ignore = bool(node.ignore or self.ignore)
        bindings = result.bindings
        for child_entry in child_entries:
            name = child_entry.name
            if check_ignore and self._is_ignored(node, name):
                continue
            self.entries_checked += 1
            attempts: list[tuple[int, _Match]] = []
            for index, step in enumerate(plan):
                if step.exact:
                    # Exact prefilter on type + name: skip nodes that can't possibly match
                    if child_entry.type != step.kind:
                        continue
                    if step.regex is not None:
                        m = step.regex.fullmatch(name)
                        if m is None:
                            continue
                        if step.leaf:
                            captures = m.groupdict() if step.regex.groupindex else None
                            child_scope = (
                                {**scope, **{k: v for k, v in captures.items() if v is not None}} if captures else scope
                            )
                            bindings.append((step.node, child_entry.path, parents, child_scope))
                            counts[index] += 1
                            break
                    elif step.leaf:
                        bindings.append((step.node, child_entry.path, parents, scope))
                        counts[index] += 1
                        break
                match = self.match(step.node, child_entry, parents, scope)
                if match.ok:
                    counts[index] += 1
                    bindings.extend(match.bindings)
                    result.issues.extend(match.issues)
                    break
                if not match.local_failed:
                    attempts.append((index, match))
            else:
                if attempts:
                    # The entry is there (its name matched) but broken deeper down: report the deeper
                    # problem and still count it, so the parent doesn't also claim it is missing
                    index, best = min(attempts, key=lambda a: len(a[1].issues))
                    counts[index] += 1
                    result.issues.extend(best.issues)
                elif not node.allow_extra:
                    result.issues.extend(self._explain_unmatched(child_entry, node, scope))

        for index, step in enumerate(plan):
            result.issues.extend(self._count_issues(entry, step.node, counts[index]))

    def _explain_unmatched(self, entry: Entry, parent: SchemaDirectory, scope: Scope) -> list[ValidationResult]:
        """Explain why an entry matched none of the children of its directory."""
        children = parent.structural_children
        local = [self.local_issues(child, entry, scope)[0] for child in children]
        hint = self._case_hint(entry, children, scope)
        suffix = f" ({hint})" if hint else ""
        # Only one possible node: its specific errors are the most helpful
        if len(children) == 1:
            issues = local[0]
            if suffix and issues:
                issues[0].message += suffix
            return issues
        expected = ", ".join(f"{c.semantical_name} ({c.describe_constraints()})" for c in children)
        reasons = {c.semantical_name: [i.message for i in issues] for c, issues in zip(children, local, strict=False)}
        kind = "directory" if entry.is_dir else "file" if entry.is_file else entry.type
        message = f"Unexpected {kind} '{entry.name}': does not match any of {expected}{suffix}"
        return [_issue(parent, entry.path, "unexpected_entry", message, reasons=reasons)]

    def _case_hint(self, entry: Entry, children: list[SchemaNode], scope: Scope) -> str | None:
        """Suggest a fix when an entry would match if only the letter case was different."""
        for variant in (entry.name.lower(), entry.name.upper()):
            if variant == entry.name:
                continue
            probe = Entry(entry.path, variant, entry.type)
            for child in children:
                if not self.local_issues(child, probe, scope)[0]:
                    return f"did you mean '{variant}' for {child.semantical_name}? names are case-sensitive"
        if "." in entry.name:
            stem, ext = entry.name.rsplit(".", 1)
            for variant in (f"{stem}.{ext.lower()}", f"{stem}.{ext.upper()}"):
                if variant == entry.name:
                    continue
                probe = Entry(entry.path, variant, entry.type)
                for child in children:
                    if not self.local_issues(child, probe, scope)[0]:
                        return f"did you mean '{variant}' for {child.semantical_name}? extensions are case-sensitive"
        return None

    def _count_issues(self, entry: Entry, child: SchemaNode, count: int) -> list[ValidationResult]:
        minimum, maximum = child.effective_min_count, child.max_count
        label = f"{_kind(child)} '{child.semantical_name}' ({child.describe_constraints()})"
        if count < minimum:
            if count == 0 and minimum == 1:
                message = f"Missing required {label} in '{entry.name}'"
            else:
                message = f"Expected at least {minimum}x {label} in '{entry.name}', found {count}"
            return [_issue(child, entry.path, "min_count", message, child.severity, expected=minimum, found=count)]
        if maximum is not None and count > maximum:
            message = f"Expected at most {maximum}x {label} in '{entry.name}', found {count}"
            return [_issue(child, entry.path, "max_count", message, child.severity, expected=maximum, found=count)]
        return []


@contextmanager
def _gc_paused() -> Iterator[None]:
    """
    Pause the cyclic garbage collector.

    Validation allocates millions of small, acyclic, long-lived objects; the collector
    repeatedly rescanning them costs ~45% of the run time on a 1M file tree.
    """
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if was_enabled:
            gc.enable()


class SchemaValidator:
    """Validator for schema nodes against filesystem paths."""

    @staticmethod
    def validate_schema(
        schema: SchemaNode,
        target_path: str,
        fs: AbstractFileSystem | None = None,
        execute_actions: bool = False,
        parent_contexts: list[ActionNodeContext] | None = None,
        context: dict[str, Any] | None = None,
        ignore: Sequence[str] = (),
        workers: int | None = None,
    ) -> ValidationReport:
        """
        Validate a target path against a schema node recursively.

        Args:
            schema: Schema node to validate against
            target_path: Path to validate
            fs: Filesystem to use for validation (local filesystem by default)
            execute_actions: Whether to execute registered actions
            parent_contexts: List of parent (node, path) tuples for context
            context: Additional context data passed to actions
            ignore: Glob patterns of entry names to skip everywhere (e.g. ``.DS_Store``)
            workers: Number of concurrent directory listings used to prefetch remote
                filesystems (defaults to 1 for local and 16 for remote filesystems)

        Returns:
            ValidationReport with all validation results
        """
        with _gc_paused():
            return SchemaValidator._validate(
                schema, target_path, fs, execute_actions, parent_contexts, context, ignore, workers
            )

    @staticmethod
    def _validate(
        schema: SchemaNode,
        target_path: str,
        fs: AbstractFileSystem | None,
        execute_actions: bool,
        parent_contexts: list[ActionNodeContext] | None,
        context: dict[str, Any] | None,
        ignore: Sequence[str],
        workers: int | None,
    ) -> ValidationReport:
        if fs is None:
            from fsspec.implementations.local import LocalFileSystem

            fs = LocalFileSystem()
        report = ValidationReport()
        snapshot = FsSnapshot(fs)
        matcher = _Matcher(snapshot, ignore)

        logger.debug(f"Validating {target_path} against schema {schema.semantical_name}")
        root = snapshot.info(target_path)
        if root is None:
            report.root_path = target_path
            report.add_result(
                _issue(schema, target_path, f"{_kind(schema)}_exists", f"Path does not exist: {target_path}")
            )
            return report
        report.root_path = root.path

        if workers is None:
            workers = 1 if is_local(fs) else DEFAULT_REMOTE_WORKERS
        if isinstance(schema, SchemaDirectory) and root.is_dir:
            snapshot.prefetch(schema, root, workers)

        # Phase 1: structure
        matcher.entries_checked = 1
        match = matcher.match(schema, root, tuple(parent_contexts or ()))
        report.add_results(match.issues)
        report.stats.entries_checked = matcher.entries_checked
        report.stats.directories_listed = snapshot.directories_listed

        registry = NodeRegistry()
        matches = report.stats.matches
        for node, path, parents, captures in match.bindings:
            registry.add_context(NodeContext(node, path, parents=parents, captures=captures))
            matches[node.semantical_name] += 1
            if isinstance(node, SchemaDirectory):
                registry.register_processed_dir(path)
        report.context["registry"] = registry

        action_results: list[ActionResult] = []
        if execute_actions:
            action_results.extend(
                ActionRegistry.run_for_contexts(registry.iter_contexts(), context, ActionTiming.DURING_VALIDATION)
            )
            report.context["action_results"] = action_results

        if not report.is_valid():
            if any(isinstance(n, SchemaPredicateNode) for n in schema.iter_nodes()):
                report.context["predicates_skipped"] = True
            return report

        # Phase 2: predicates
        predicate_report = SchemaValidator._evaluate_predicates(schema, target_path, registry)
        report.add_results(predicate_report.results)
        if not predicate_report.is_valid():
            return report

        # Phase 3: after-validation actions
        if execute_actions:
            action_results.extend(SchemaValidator._execute_after_validation_actions(registry, context))
        return report

    @staticmethod
    def _execute_after_validation_actions(
        registry: NodeRegistry, context: dict[str, Any] | None = None
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
    def _evaluate_predicates(schema: SchemaNode, target_path: str, registry: NodeRegistry) -> ValidationReport:
        """
        Evaluate every predicate once per directory instance of the directory declaring it.

        Args:
            schema: Root schema node
            target_path: Root path
            registry: Registry of validated nodes

        Returns:
            ValidationReport with predicate evaluation results
        """
        report = ValidationReport()
        owners = [n for n in schema.iter_nodes() if isinstance(n, SchemaDirectory) and n.predicates]
        if not owners:
            return report

        # Bucket every matched entry under each predicate-owning ancestor directory instance:
        # buckets[(id(owner), owner_path)][semantical_name] -> contexts. O(entries * depth).
        owner_ids = {id(o) for o in owners}
        element_names = {e for o in owners for p in o.predicates for e in p.elements}
        buckets: dict[tuple[int, str], dict[str, list[NodeContext]]] = {}
        for ctx in registry.iter_contexts():
            if ctx.node.semantical_name not in element_names:
                continue
            for parent_node, parent_path in ctx.parents:
                if id(parent_node) in owner_ids:
                    buckets.setdefault((id(parent_node), parent_path), {}).setdefault(
                        ctx.node.semantical_name, []
                    ).append(ctx)

        for owner in owners:
            for instance in registry.get_contexts_by_node(owner):
                bucket = buckets.get((id(owner), instance.path), {})
                for predicate in owner.predicates:
                    report.add_results(
                        SchemaValidator.validate_predicate(predicate, instance.path, registry, bucket).results
                    )
        return report

    @staticmethod
    def validate_predicate(
        predicate_node: SchemaPredicateNode,
        path: str,
        registry: NodeRegistry,
        elements: dict[str, list[NodeContext]] | None = None,
    ) -> ValidationReport:
        """
        Validate a predicate node for one directory instance.

        Args:
            predicate_node: Predicate node to validate
            path: Path of the directory instance the predicate is evaluated in
            registry: Registry of validated nodes
            elements: Matched contexts inside the directory instance, keyed by semantical name.
                When omitted, all matched contexts in the registry are used.

        Returns:
            ValidationReport with results
        """
        report = ValidationReport()
        func = PredicateRegistry.get(predicate_node.predicate_type)
        if func is None:
            report.add_result(
                _issue(
                    predicate_node,
                    path,
                    "predicate",
                    f"Unknown predicate type '{predicate_node.predicate_type}'. "
                    f"Available: {', '.join(PredicateRegistry.names())}",
                )
            )
            return report

        if elements is None:
            elements = {name: registry.get_contexts_by_name(name) for name in predicate_node.elements}
        selected = {name: list(elements.get(name, [])) for name in predicate_node.elements}
        try:
            results = func(predicate_node, path, selected)
            for result in results:
                if not result.is_valid:
                    result.severity = predicate_node.severity
            report.add_results(results)
        except Exception as e:
            report.add_result(
                _issue(predicate_node, path, predicate_node.predicate_type, f"Predicate failed with an error: {e!s}")
            )
        return report
