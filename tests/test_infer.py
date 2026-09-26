"""Schema inference: an inferred schema must always validate the tree it was inferred from."""

from __future__ import annotations

import contextlib
from pathlib import Path

import fsspec
import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from katachi.schema.importer import parse_schema
from katachi.schema.infer import dump_schema, infer_schema, split_extension
from katachi.validation.validators import SchemaValidator
from tests.conftest import make_tree


def infer_and_validate(root: Path):
    fs = fsspec.filesystem("file")
    document = infer_schema(fs, str(root))
    schema = parse_schema(yaml.safe_load(dump_schema(document)), str(root))
    return document, SchemaValidator.validate_schema(schema, str(root), fs)


def test_split_extension():
    assert split_extension("a.jpg") == ("a", ".jpg")
    assert split_extension("scan.nii.gz") == ("scan", ".nii.gz")
    assert split_extension("archive.tar.gz") == ("archive", ".tar.gz")
    assert split_extension("Makefile") == ("Makefile", "")
    assert split_extension(".bashrc") == (".bashrc", "")


def test_infers_patterns_required_and_pairs(tmp_path):
    root = make_tree(
        tmp_path / "ds",
        [
            "README.md",
            ".DS_Store",
            "2025-01-01/img_001.jpg",
            "2025-01-01/img_001.json",
            "2025-01-02/img_002.jpg",
            "2025-01-02/img_002.json",
            "2025-01-02/notes.txt",
        ],
    )
    document, report = infer_and_validate(root)
    assert report.is_valid(), [r.message for r in report.failures]
    assert document["ignore"] == [".*"]
    readme, day = document["children"]
    assert readme == {
        "semantical_name": "readme_md",
        "type": "file",
        "pattern_name": "README",
        "extension": ".md",
        "required": True,
    }
    assert day["pattern_name"] == r"\d{4}\-\d{2}\-\d{2}"
    kinds = {c["semantical_name"]: c for c in day["children"]}
    assert kinds["img_jpg"]["pattern_name"] == r"img_\d{3}"
    assert kinds["img_jpg"]["required"] is True
    assert "required" not in kinds["notes_txt"]  # only present in one of the two days
    [pairs] = [c for c in day["children"] if c["type"] == "predicate"]
    assert pairs["elements"] == ["img_jpg", "img_json"]


def test_inferred_schema_is_strict_enough(tmp_path):
    root = make_tree(tmp_path / "ds", ["a/img1.jpg", "a/img2.jpg", "b/img3.jpg"])
    document, _ = infer_and_validate(root)
    make_tree(root, ["a/unexpected.csv"])
    schema = parse_schema(document, str(root))
    report = SchemaValidator.validate_schema(schema, str(root), fsspec.filesystem("file"))
    assert not report.is_valid()


# Names portable to Linux, macOS and Windows, including regex metacharacters, brackets, spaces,
# unicode, hidden entries and digit runs (to exercise pattern generalization)
NAME = st.from_regex(r"\.?[a-zé+()\[\]-]{1,3}( ?[a-z0-9_]{0,3})?[0-9]{0,3}", fullmatch=True).filter(
    lambda n: n not in (".", "..") and not n.endswith((" ", "."))
)
EXT = st.sampled_from(["", ".jpg", ".json", ".txt", ".tar.gz", ".JPG"])
PATHS = st.lists(
    st.tuples(st.lists(NAME, min_size=0, max_size=3), NAME, EXT).map(lambda t: "/".join([*t[0], f"{t[1]}{t[2]}"])),
    min_size=1,
    max_size=25,
)


def _is_consistent(paths: list[str]) -> bool:
    """Reject trees where a path is both a file and a directory, or that collide on case-insensitive filesystems."""
    files = set(paths)
    dirs = {"/".join(p.split("/")[:i]) for p in paths for i in range(1, p.count("/") + 1)}
    everything = files | dirs
    return not (files & dirs) and len({p.lower() for p in everything}) == len(everything)


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(paths=PATHS.filter(_is_consistent))
def test_inferred_schema_always_validates_its_source(tmp_path_factory, paths):
    root = make_tree(tmp_path_factory.mktemp("prop") / "root", paths)
    _, report = infer_and_validate(root)
    assert report.is_valid(), (paths, [r.message for r in report.failures])


def test_nested_hidden_and_special_entries(tmp_path):
    import os

    root = make_tree(tmp_path / "a", ["sub/x.txt", "sub/.DS_Store", "a1", "a2", "a1.txt", "a2.txt"])
    with contextlib.suppress(OSError, NotImplementedError):  # symlinks may be unavailable (Windows)
        os.symlink(tmp_path / "missing", root / "sub" / "dangling[1]")
    document, report = infer_and_validate(root)
    assert report.is_valid(), [r.message for r in report.failures]
    [sub] = [c for c in document["children"] if c["semantical_name"] == "sub"]
    assert ".*" in sub["ignore"]
