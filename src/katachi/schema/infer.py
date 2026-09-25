"""
Infer a schema from an existing directory tree (``katachi infer``).

Sibling entries are grouped by a generalized name: runs of digits become ``\\d{n}`` (or ``\\d+``
when the length varies), everything else is kept literally. Directories in the same group are
merged, so the children of ``2025-01-01/`` and ``2025-01-02/`` are described once. Entries that
occur in every instance of their parent become ``required``, and file groups that share the same
names with different extensions (``img1.jpg`` + ``img1.json``) get a ``pair_comparison`` predicate.

The inferred schema is a starting point: it always validates the tree it was inferred from, and
is meant to be reviewed and tightened by hand.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import yaml
from fsspec import AbstractFileSystem

from katachi.validation.snapshot import Entry, FsSnapshot

#: Multi-part extensions that should be kept together
COMPOUND_EXTENSIONS = (".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst", ".nii.gz", ".json.gz", ".csv.gz", ".jsonl.gz")

_DIGITS = re.compile(r"\d+")


def split_extension(name: str) -> tuple[str, str]:
    """Split ``name`` into ``(stem, extension)``; hidden-file dots are not extensions."""
    lowered = name.lower()
    for ext in COMPOUND_EXTENSIONS:
        if lowered.endswith(ext) and len(name) > len(ext):
            return name[: -len(ext)], name[-len(ext) :]
    dot = name.rfind(".")
    if dot <= 0:
        return name, ""
    return name[:dot], name[dot:]


def _shape(stem: str) -> tuple[str, ...]:
    """Split a name into literal parts and digit runs: ``img_01`` -> ``("img_", "#")``."""
    parts: list[str] = []
    last = 0
    for m in _DIGITS.finditer(stem):
        parts.append(stem[last : m.start()])
        parts.append("#")
        last = m.end()
    parts.append(stem[last:])
    return tuple(parts)


def _pattern_for(stems: Sequence[str]) -> str:
    """Build a regex matching all stems that share the same shape."""
    if len(set(stems)) == 1 and len(stems) == 1:
        return re.escape(stems[0])
    shape = _shape(stems[0])
    digit_runs = [[m.group(0) for m in _DIGITS.finditer(s)] for s in stems]
    pattern = []
    run_index = 0
    for part in shape:
        if part == "#":
            lengths = {len(runs[run_index]) for runs in digit_runs}
            # Fixed width runs (zero padded ids, dates) keep their width; others may grow (img9 -> img10)
            width = lengths.pop() if len(lengths) == 1 else 1
            pattern.append(f"\\d{{{width}}}" if width > 1 else "\\d+")
            run_index += 1
        else:
            pattern.append(re.escape(part))
    return "".join(pattern)


def _semantic_name(stems: Sequence[str], ext: str, is_dir: bool) -> str:
    base = stems[0] if len(stems) == 1 else "_".join(p for p in _shape(stems[0]) if p != "#")
    name = re.sub(r"[^0-9a-zA-Z]+", "_", base).strip("_").lower() or f"numbered_{'dir' if is_dir else 'file'}"
    if ext and not is_dir:
        name = f"{name}_{ext.lstrip('.').replace('.', '_').lower()}"
    if name[0].isdigit():
        name = f"{'dir' if is_dir else 'file'}_{name}"
    return name


@dataclass
class _Group:
    is_dir: bool
    ext: str
    shape: tuple[str, ...]
    entries: list[Entry] = field(default_factory=list)
    parents: set[str] = field(default_factory=set)


class _Inferrer:
    def __init__(self, snapshot: FsSnapshot, max_depth: int, include_hidden: bool):
        self.snapshot = snapshot
        self.max_depth = max_depth
        self.include_hidden = include_hidden
        self.used_names: set[str] = set()
        self.hidden_seen = False

    def unique(self, name: str) -> str:
        candidate, i = name, 2
        while candidate in self.used_names:
            candidate = f"{name}_{i}"
            i += 1
        self.used_names.add(candidate)
        return candidate

    def children_of(self, dirs: Sequence[Entry], depth: int) -> list[dict[str, Any]]:
        groups: dict[tuple[bool, str, tuple[str, ...]], _Group] = {}
        for directory in dirs:
            try:
                entries = self.snapshot.listdir(directory.path)
            except OSError:
                continue
            for entry in entries:
                if entry.name.startswith(".") and not self.include_hidden:
                    self.hidden_seen = True
                    continue
                if entry.is_dir:
                    stem, ext = entry.name, ""
                elif entry.is_file:
                    stem, ext = split_extension(entry.name)
                else:
                    continue
                key = (entry.is_dir, ext, _shape(stem))
                group = groups.setdefault(key, _Group(entry.is_dir, ext, key[2]))
                group.entries.append(entry)
                group.parents.add(directory.path)

        # Literal (single name) groups first: they're more specific than patterns
        ordered = sorted(
            groups.values(),
            key=lambda g: (len({e.name for e in g.entries}) > 1, not g.is_dir, "".join(g.shape), g.ext),
        )
        nodes: list[dict[str, Any]] = []
        file_nodes: list[tuple[_Group, dict[str, Any], str]] = []
        for group in ordered:
            names = sorted({e.name for e in group.entries})
            stems = [n if group.is_dir else split_extension(n)[0] for n in names]
            pattern = _pattern_for(stems)
            node: dict[str, Any] = {
                "semantical_name": self.unique(_semantic_name(stems, group.ext, group.is_dir)),
                "type": "directory" if group.is_dir else "file",
                "pattern_name": pattern,
            }
            if not group.is_dir and group.ext:
                node["extension"] = group.ext
            if len(group.parents) == len(dirs):
                node["required"] = True
            if group.is_dir:
                if depth < self.max_depth:
                    children = self.children_of(group.entries, depth + 1)
                    if children:
                        node["children"] = children
            else:
                file_nodes.append((group, node, pattern))
            nodes.append(node)

        nodes.extend(self._pair_predicates(file_nodes))
        return nodes

    def _pair_predicates(self, file_nodes: list[tuple[_Group, dict[str, Any], str]]) -> list[dict[str, Any]]:
        """Group file nodes with the same stems but different extensions into pair predicates."""
        by_stems: dict[frozenset[str], list[dict[str, Any]]] = {}
        for group, node, _pattern in file_nodes:
            stems = frozenset(f"{e.path.rsplit('/', 1)[0]}/{split_extension(e.name)[0]}" for e in group.entries)
            if len(stems) > 1:
                by_stems.setdefault(stems, []).append(node)
        predicates = []
        for members in by_stems.values():
            if len(members) < 2:
                continue
            names = [m["semantical_name"] for m in members]
            predicates.append({
                "semantical_name": self.unique(f"{'_'.join(names)}_pairs"),
                "type": "predicate",
                "predicate_type": "pair_comparison",
                "description": f"Every {' / '.join(names)} entry has a counterpart with the same name",
                "elements": names,
            })
        return predicates


def infer_schema(
    fs: AbstractFileSystem, path: str, max_depth: int = 16, include_hidden: bool = False
) -> dict[str, Any]:
    """
    Infer a schema document (a dict ready to be dumped as YAML) from a directory.

    Args:
        fs: Filesystem containing the directory
        path: Directory to infer the schema from
        max_depth: Maximum depth to descend
        include_hidden: Also describe entries starting with ``.`` (otherwise they are ignored)

    Raises:
        FileNotFoundError: If the path does not exist or is not a directory
    """
    snapshot = FsSnapshot(fs)
    root = snapshot.info(path)
    if root is None or not root.is_dir:
        raise FileNotFoundError(f"Not a directory: {path}")
    inferrer = _Inferrer(snapshot, max_depth, include_hidden)
    inferrer.used_names.add("root")
    children = inferrer.children_of([root], 1)
    schema: dict[str, Any] = {
        "semantical_name": re.sub(r"[^0-9a-zA-Z]+", "_", root.name).strip("_").lower() or "root",
        "type": "directory",
        "description": f"Inferred from {root.name}",
    }
    if inferrer.hidden_seen:
        schema["ignore"] = [".*"]
    if children:
        schema["children"] = children
    return schema


def dump_schema(schema: dict[str, Any]) -> str:
    """Dump a schema document as YAML, with a modeline enabling editor completion."""
    body = yaml.safe_dump(schema, sort_keys=False, allow_unicode=True, width=120)
    return f"# yaml-language-server: $schema={JSON_SCHEMA_URL}\n{body}"


JSON_SCHEMA_URL = "https://raw.githubusercontent.com/nmicovic/katachi/main/katachi.schema.json"
