"""
Predicates validate relationships between entries, e.g. "every image has a label".

A predicate declared inside a schema directory is evaluated once for every directory
instance matched by that schema directory, and only sees the elements found (at any
depth) inside that instance. Declare a predicate at the root to compare elements across
the whole tree, or deeper to compare them per sub-directory.

Custom predicates can be registered with :func:`register_predicate`::

    @register_predicate("same_count")
    def same_count(predicate, dir_path, elements):
        ...
        return [ValidationResult(...)]
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import ClassVar

from katachi.schema.schema_node import SchemaFile, SchemaPredicateNode
from katachi.validation.core import ValidationResult
from katachi.validation.registry import NodeContext

#: A predicate receives the predicate node, the path of the directory instance it is
#: evaluated in, and the matched contexts of each element (keyed by semantical name).
PredicateFunc = Callable[[SchemaPredicateNode, str, dict[str, list[NodeContext]]], list[ValidationResult]]


class PredicateRegistry:
    """Registry of predicate implementations, keyed by ``predicate_type``."""

    _predicates: ClassVar[dict[str, PredicateFunc]] = {}

    @classmethod
    def register(cls, predicate_type: str, func: PredicateFunc | None = None) -> Callable:
        """Register a predicate implementation, as a decorator or directly."""

        def decorator(f: PredicateFunc) -> PredicateFunc:
            cls._predicates[predicate_type] = f
            return f

        if func is not None:
            return decorator(func)
        return decorator

    @classmethod
    def get(cls, predicate_type: str) -> PredicateFunc | None:
        return cls._predicates.get(predicate_type)

    @classmethod
    def names(cls) -> list[str]:
        return sorted(cls._predicates)

    @classmethod
    def unregister(cls, predicate_type: str) -> None:
        cls._predicates.pop(predicate_type, None)


register_predicate = PredicateRegistry.register


def _result(
    predicate: SchemaPredicateNode, is_valid: bool, message: str, path: str, context: dict | None = None
) -> ValidationResult:
    return ValidationResult(
        is_valid=is_valid,
        message=message,
        path=path,
        validator_name=predicate.predicate_type,
        node_origin=predicate.semantical_name,
        context=context,
    )


def _stem(context: NodeContext) -> str:
    name = context.name
    node = context.node
    if isinstance(node, SchemaFile) and node.extensions:
        for ext in node.extensions:
            if name.endswith(ext):
                return name[: -len(ext)]
    if "." in name:
        return name.rsplit(".", 1)[0]
    return name


_KEY_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def element_key(predicate: SchemaPredicateNode, context: NodeContext) -> str | None:
    """
    Compute the key used to pair up elements.

    - By default the key is the entry name without the extension declared in the schema
      (``img1.jpg`` -> ``img1``).
    - ``key_pattern`` option: the key is extracted from the entry name with a regular expression:
      the named group ``key`` if present, otherwise the first group, otherwise the whole match.
    - ``key`` option: a template combining ``{stem}``, ``{name}`` and values captured by named
      groups of the entry's (or its ancestors') patterns, e.g. ``"{split}/{stem}"``.
    """
    key_pattern = predicate.options.get("key_pattern")
    if key_pattern:
        match = re.search(key_pattern, context.name)
        if not match:
            return None
        if "key" in match.re.groupindex:
            return match.group("key")
        return match.group(1) if match.re.groups else match.group(0)
    template = predicate.options.get("key")
    if template:
        values = {**context.captures, "stem": _stem(context), "name": context.name}
        missing = False

        def substitute(m: re.Match) -> str:
            nonlocal missing
            if m.group(1) not in values:
                missing = True
                return ""
            return values[m.group(1)]

        key = _KEY_PLACEHOLDER.sub(substitute, str(template))
        return None if missing else key
    return _stem(context)


@register_predicate("pair_comparison")
def pair_comparison(
    predicate: SchemaPredicateNode, dir_path: str, elements: dict[str, list[NodeContext]]
) -> list[ValidationResult]:
    """
    Every element must have a counterpart with the same key in every other element.

    Example: ``img1.jpg`` (image) must have ``img1.json`` (metadata) and vice versa.
    Options: ``key_pattern`` (see :func:`element_key`).
    """
    keys: dict[str, dict[str, NodeContext]] = {}
    results: list[ValidationResult] = []
    for element, contexts in elements.items():
        keyed: dict[str, NodeContext] = {}
        for ctx in contexts:
            key = element_key(predicate, ctx)
            if key is None:
                results.append(
                    _result(
                        predicate,
                        False,
                        f"Could not extract a pairing key from '{ctx.name}' ({element}); check the predicate options",
                        ctx.path,
                    )
                )
                continue
            keyed.setdefault(key, ctx)
        keys[element] = keyed

    all_keys = sorted(set().union(*(k.keys() for k in keys.values())))
    for key in all_keys:
        present = [e for e in predicate.elements if key in keys.get(e, {})]
        missing = [e for e in predicate.elements if key not in keys.get(e, {})]
        if not missing:
            continue
        example = keys[present[0]][key]
        results.append(
            _result(
                predicate,
                False,
                f"'{example.name}' ({present[0]}) has no matching {', '.join(missing)} (key '{key}')",
                example.path,
                {"key": key, "missing": missing},
            )
        )

    if not results:
        results.append(
            _result(
                predicate,
                True,
                f"All {len(all_keys)} {'/'.join(predicate.elements)} groups are complete",
                dir_path,
            )
        )
    return results


@register_predicate("count_match")
def count_match(
    predicate: SchemaPredicateNode, dir_path: str, elements: dict[str, list[NodeContext]]
) -> list[ValidationResult]:
    """All elements must occur the same number of times."""
    counts = {element: len(elements.get(element, [])) for element in predicate.elements}
    if len(set(counts.values())) <= 1:
        return [_result(predicate, True, f"All elements occur {next(iter(counts.values()), 0)} times", dir_path)]
    detail = ", ".join(f"{name}={count}" for name, count in counts.items())
    return [_result(predicate, False, f"Element counts differ: {detail}", dir_path, {"counts": counts})]


@register_predicate("unique_keys")
def unique_keys(
    predicate: SchemaPredicateNode, dir_path: str, elements: dict[str, list[NodeContext]]
) -> list[ValidationResult]:
    """
    No two entries (across all listed elements) may share the same key.

    Useful to catch e.g. ``img1.jpg`` and ``img1.png`` living next to each other, or the
    same sample id appearing in two splits. Options: ``key_pattern``.
    """
    seen: dict[str, NodeContext] = {}
    results: list[ValidationResult] = []
    for element in predicate.elements:
        for ctx in elements.get(element, []):
            key = element_key(predicate, ctx)
            if key is None:
                continue
            if key in seen:
                results.append(
                    _result(
                        predicate,
                        False,
                        f"Duplicate key '{key}': '{ctx.name}' conflicts with '{seen[key].path}'",
                        ctx.path,
                        {"key": key},
                    )
                )
            else:
                seen[key] = ctx
    if not results:
        results.append(_result(predicate, True, f"All {len(seen)} keys are unique", dir_path))
    return results
