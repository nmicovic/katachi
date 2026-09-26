"""Structural validation semantics."""

from __future__ import annotations

import os
import sys

import fsspec
import pytest

from katachi.schema.importer import parse_schema
from katachi.validation.core import ValidationResult, ValidatorRegistry
from katachi.validation.validators import SchemaValidator
from tests.conftest import messages, rules, run_validation

IMAGES = """
semantical_name: root
type: directory
children:
  - semantical_name: image
    type: file
    pattern_name: "img\\\\d+"
    extension: .jpg
"""


def test_valid_tree(tree):
    report = run_validation(IMAGES, tree("img1.jpg", "img22.jpg"))
    assert report.is_valid()
    assert report.stats.matches["image"] == 2
    assert report.stats.entries_checked == 3


def test_pattern_must_match_whole_name(tree):
    # Prefix matches used to be accepted (re.match): img1_backup.jpg matched img\d+
    report = run_validation(IMAGES, tree("img1.jpg", "img1_backup.jpg"))
    assert rules(report) == ["file_pattern"]
    assert "got 'img1_backup'" in messages(report)[0]


def test_extension_is_normalized_and_exact(tree):
    schema = IMAGES.replace("extension: .jpg", "extension: jpg")
    assert run_validation(schema, tree("img1.jpg")).is_valid()
    report = run_validation(schema, tree("img2.xjpg"))
    assert messages(report) == ["File extension mismatch: expected .jpg, got .xjpg"]


def test_multiple_and_compound_extensions(tree):
    schema = """
    type: directory
    children:
      - semantical_name: archive
        type: file
        pattern_name: "part\\\\d+"
        extension: [.tar.gz, .zip]
    """
    assert run_validation(schema, tree("part1.tar.gz", "part2.zip")).is_valid()
    assert rules(run_validation(schema, tree("part3.gz"))) == ["file_extension"]


def test_file_without_declared_extension_matches_whole_name(tree):
    schema = """
    type: directory
    children:
      - {semantical_name: license, type: file, pattern_name: LICENSE}
    """
    assert run_validation(schema, tree("LICENSE")).is_valid()
    assert not run_validation(schema, tree("LICENSE.txt")).is_valid()


def test_required_child_is_reported_when_missing(tree):
    schema = (
        IMAGES
        + """
  - semantical_name: meta
    type: file
    pattern_name: meta
    extension: .json
    required: true
"""
    )
    report = run_validation(schema, tree("img1.jpg"))
    assert rules(report) == ["min_count"]
    assert messages(report) == ["Missing required file 'meta' (meta.json) in 'root'"]
    assert report.failures[0].context == {"expected": 1, "found": 0}


def test_optional_children_may_be_absent(tree):
    assert run_validation(IMAGES, tree()).is_valid()


@pytest.mark.parametrize(
    ("count", "valid", "rule"),
    [(1, False, "min_count"), (2, True, None), (3, True, None), (4, False, "max_count")],
)
def test_min_and_max_count(tree, count, valid, rule):
    schema = IMAGES + "    min_count: 2\n    max_count: 3\n"
    report = run_validation(schema, tree(*[f"img{i}.jpg" for i in range(count)]))
    assert report.is_valid() is valid
    if rule:
        assert rules(report) == [rule]


def test_counts_are_per_directory_instance(tree):
    schema = """
    type: directory
    children:
      - semantical_name: day
        type: directory
        pattern_name: "day\\\\d"
        children:
          - {semantical_name: image, type: file, extension: .jpg, required: true}
    """
    report = run_validation(schema, tree("day1/a.jpg", "day2/"))
    assert rules(report) == ["min_count"]
    assert report.failures[0].path.endswith("day2")


def test_unexpected_entry_lists_candidates(tree):
    schema = (
        IMAGES
        + """
  - semantical_name: meta
    type: file
    pattern_name: meta
    extension: .json
"""
    )
    report = run_validation(schema, tree("img1.jpg", "notes.txt"))
    assert rules(report) == ["unexpected_entry"]
    message = messages(report)[0]
    assert "Unexpected file 'notes.txt'" in message
    assert "image (img\\d+.jpg)" in message
    assert "meta (meta.json)" in message
    assert set(report.failures[0].context["reasons"]) == {"image", "meta"}


def test_case_mismatch_hint(tree):
    schema = IMAGES + "  - {semantical_name: readme, type: file, pattern_name: README, extension: .md}\n"
    report = run_validation(schema, tree("img1.JPG"))
    assert "did you mean 'img1.jpg' for image?" in messages(report)[0]


def test_type_mismatch(tree):
    report = run_validation(IMAGES, tree("img1.jpg/"))
    assert messages(report) == ["Expected a file but 'img1.jpg' is a directory"]


def test_directory_without_children_accepts_any_content(tree):
    schema = """
    type: directory
    children:
      - {semantical_name: blobs, type: directory, pattern_name: blobs}
    """
    assert run_validation(schema, tree("blobs/a/b/c.bin", "blobs/x")).is_valid()


def test_allow_extra(tree):
    schema = IMAGES + "allow_extra: true\n"
    assert run_validation(schema, tree("img1.jpg", "notes.txt", "misc/")).is_valid()


def test_allow_extra_still_reports_entries_that_fail_deeper(tree):
    schema = """
    type: directory
    allow_extra: true
    children:
      - semantical_name: day
        type: directory
        pattern_name: "day\\\\d"
        children:
          - {semantical_name: image, type: file, extension: .jpg}
    """
    report = run_validation(schema, tree("day1/a.png", "random.txt"))
    assert rules(report) == ["file_extension"]


def test_ignore_globs_in_schema_and_globally(tree):
    root = tree("img1.jpg", ".DS_Store", "Thumbs.db")
    assert run_validation(IMAGES + "ignore: ['.*', Thumbs.db]\n", root).is_valid()
    assert run_validation(IMAGES, root, ignore=[".*", "Thumbs.db"]).is_valid()
    assert not run_validation(IMAGES, root).is_valid()


def test_ambiguous_siblings_backtrack(tree):
    schema = """
    type: directory
    children:
      - semantical_name: jpg_dir
        type: directory
        pattern_name: "data\\\\d"
        children: [{semantical_name: jpg, type: file, extension: .jpg}]
      - semantical_name: png_dir
        type: directory
        pattern_name: "data\\\\d"
        children: [{semantical_name: png, type: file, extension: .png}]
    """
    report = run_validation(schema, tree("data1/a.jpg", "data2/b.png"))
    assert report.is_valid()
    # Only the chosen alternatives are registered
    registry = report.context["registry"]
    assert [c.name for c in registry.get_contexts_by_name("jpg_dir")] == ["data1"]
    assert [c.name for c in registry.get_contexts_by_name("png_dir")] == ["data2"]
    assert report.stats.matches == {"root": 1, "jpg_dir": 1, "png_dir": 1, "jpg": 1, "png": 1}


def test_deep_failure_is_reported_instead_of_generic_mismatch(tree):
    schema = """
    type: directory
    children:
      - semantical_name: day
        type: directory
        pattern_name: "day\\\\d"
        children: [{semantical_name: image, type: file, extension: .jpg}]
      - {semantical_name: readme, type: file, pattern_name: README, extension: .md}
    """
    report = run_validation(schema, tree("day1/a.png", "README.md"))
    assert messages(report) == ["File extension mismatch: expected .jpg, got .png"]
    assert report.failures[0].path.endswith("day1/a.png")


def test_broken_required_entry_is_not_also_reported_missing(tree):
    schema = """
    type: directory
    children:
      - semantical_name: images
        type: directory
        pattern_name: images
        required: true
        children: [{semantical_name: image, type: file, extension: .jpg}]
    """
    report = run_validation(schema, tree("images/a.png"))
    assert rules(report) == ["file_extension"]


def test_root_pattern_and_missing_root(tree, tmp_path):
    schema = "type: directory\npattern_name: dataset\n"
    report = run_validation(schema, tree())
    assert messages(report) == ["Directory name does not match pattern: dataset (got 'root')"]
    missing = run_validation(schema, tmp_path / "nope")
    assert rules(missing) == ["directory_exists"]
    assert messages(missing)[0].startswith("Path does not exist")


def test_file_size(tree):
    schema = IMAGES + "    min_size: 2\n    max_size: 4\n"
    assert run_validation(schema, tree("img1.jpg", content=b"abc")).is_valid()
    too_small = run_validation(schema, tree("img1.jpg", content=b"a"))
    assert messages(too_small) == ["File is too small: 1 B < minimum 2 B"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_permissions_and_owner(tree):
    root = tree("img1.jpg")
    os.chmod(root / "img1.jpg", 0o640)
    schema = IMAGES + '    permissions: "0640"\n'
    assert run_validation(schema, root).is_valid()
    report = run_validation(schema.replace("0640", "0600"), root)
    assert messages(report) == ["Expected permissions 0600, got 0640"]

    uid = os.stat(root / "img1.jpg").st_uid
    assert run_validation(IMAGES + f'    owner: "{uid}"\n', root).is_valid()
    report = run_validation(IMAGES + "    owner: definitely-not-a-user\n", root)
    assert rules(report) == ["owner"]


@pytest.mark.parametrize(
    ("case", "good", "bad"),
    [
        ("snake_case", "my_file_2", "MyFile"),
        ("kebab-case", "my-file", "my_file"),
        ("camelCase", "myFile", "MyFile"),
        ("PascalCase", "MyFile", "myFile"),
        ("SCREAMING_SNAKE_CASE", "MY_FILE", "My_File"),
    ],
)
def test_name_case(tree, case, good, bad):
    schema = f"""
    type: directory
    children:
      - {{semantical_name: doc, type: file, extension: .md, name_case: {case}}}
    """
    assert run_validation(schema, tree(f"{good}.md")).is_valid()
    report = run_validation(schema, tree(f"{bad}.md"))
    assert rules(report) == ["name_case"]


def test_captures_are_reused_by_descendants(tree):
    schema = """
    type: directory
    children:
      - semantical_name: scene
        type: directory
        pattern_name: "(?P<scene>scene_\\\\d+)"
        children:
          - semantical_name: frame
            type: file
            pattern_name: "{scene}_cam\\\\d"
            extension: .jpg
    """
    report = run_validation(schema, tree("scene_1/scene_1_cam0.jpg", "scene_2/scene_2_cam1.jpg"))
    assert report.is_valid()
    frames = report.context["registry"].get_contexts_by_name("frame")
    assert sorted(c.captures["scene"] for c in frames) == ["scene_1", "scene_2"]

    report = run_validation(schema, tree("scene_3/scene_1_cam0.jpg"))
    assert messages(report) == ["Filename does not match pattern: scene_3_cam\\d (got 'scene_1_cam0')"]


def test_captured_values_are_escaped(tree):
    schema = """
    type: directory
    children:
      - semantical_name: version
        type: directory
        pattern_name: "(?P<v>v\\\\d\\\\.\\\\d)"
        children:
          - {semantical_name: notes, type: file, pattern_name: "notes_{v}", extension: .txt}
    """
    assert run_validation(schema, tree("v1.2/notes_v1.2.txt")).is_valid()
    assert not run_validation(schema, tree("v1.2/notes_v1x2.txt")).is_valid()


def test_warning_severity_does_not_fail(tree):
    schema = (
        IMAGES
        + """
  - semantical_name: readme
    type: file
    pattern_name: README
    extension: .md
    required: true
    severity: warning
"""
    )
    report = run_validation(schema, tree("img1.jpg"))
    assert report.is_valid()
    assert [w.validator_name for w in report.warnings] == ["min_count"]
    assert report.failures == []


def test_warnings_inside_matched_subtrees_are_kept(tree):
    schema = """
    type: directory
    children:
      - semantical_name: day
        type: directory
        pattern_name: "day\\\\d"
        children:
          - {semantical_name: log, type: file, extension: .log, required: true, severity: warning}
    """
    report = run_validation(schema, tree("day1/"))
    assert report.is_valid()
    assert len(report.warnings) == 1


def test_custom_validator_participates_in_matching(tree):
    @ValidatorRegistry.register("no_tmp")
    def no_tmp(node, path):
        if node.semantical_name == "image" and "tmp" in path.rsplit("/", 1)[-1]:
            return [ValidationResult(False, "temporary image", path, "no_tmp", node.semantical_name)]
        return []

    schema = IMAGES.replace('"img\\\\d+"', '"img\\\\w+"')
    report = run_validation(schema, tree("img1.jpg", "imgtmp.jpg"))
    assert messages(report) == ["temporary image"]


def test_custom_validator_exception_is_reported(tree):
    ValidatorRegistry.register("broken", lambda node, path: 1 / 0)
    report = run_validation(IMAGES, tree("img1.jpg"))
    assert "Validator broken failed: division by zero" in messages(report)


def test_memory_filesystem():
    fs = fsspec.filesystem("memory")
    fs.pipe({"/ds/img1.jpg": b"", "/ds/img2.jpg": b"", "/ds/bad.png": b""})
    import yaml

    schema = parse_schema(yaml.safe_load(IMAGES), "/ds")
    report = SchemaValidator.validate_schema(schema, "/ds", fs)
    # bad.png has both a wrong name and a wrong extension
    assert rules(report) == ["file_extension", "file_pattern"]
    assert {f.path for f in report.failures} == {"/ds/bad.png"}


def test_every_directory_is_listed_once():
    fs = fsspec.filesystem("memory")
    fs.pipe({f"/big/d{d}/img{i}.jpg": b"" for d in range(5) for i in range(20)})
    calls: list[str] = []
    original_ls = fs.ls

    def counting_ls(path, detail=True, **kwargs):
        calls.append(path)
        return original_ls(path, detail=detail, **kwargs)

    fs.ls = counting_ls
    schema = parse_schema({
        "type": "directory",
        "children": [
            # Two ambiguous alternatives: the second is tried for every directory
            {
                "semantical_name": "png_dir",
                "type": "directory",
                "pattern_name": r"d\d",
                "children": [{"semantical_name": "png", "type": "file", "extension": ".png"}],
            },
            {
                "semantical_name": "jpg_dir",
                "type": "directory",
                "pattern_name": r"d\d",
                "children": [{"semantical_name": "jpg", "type": "file", "extension": ".jpg"}],
            },
        ],
    })
    report = SchemaValidator.validate_schema(schema, "/big", fs, workers=4)
    assert report.is_valid()
    assert sorted(calls) == sorted(set(calls))
    assert len(calls) == 6


def test_report_serialization(tree):
    report = run_validation(IMAGES, tree("img1.jpg", "img2.png"))
    data = report.to_dict()
    assert data["valid"] is False
    assert data["failure_count"] == 1
    assert data["results"][0]["validator_name"] == "file_extension"
    assert data["stats"]["matches"] == {"root": 1, "image": 1}


# --- Regression tests from the code review -------------------------------------------------


@pytest.mark.parametrize("pattern", [r"img\d+$", r"(?!.*\.txt).+", r"^img\d+"])
def test_anchored_and_lookaround_patterns_match(tree, pattern):
    """The fast path must agree with the full checks (patterns are matched against the stem)."""
    schema = {
        "type": "directory",
        "children": [
            {"semantical_name": "img", "type": "file", "pattern_name": pattern, "extension": "jpg", "required": True}
        ],
    }
    report = run_validation(schema, tree("img1.jpg"))
    assert report.is_valid(), messages(report)
    assert report.stats.matches["img"] == 1


def test_extension_only_name_is_rejected_consistently(tree):
    schema = {"type": "directory", "children": [{"semantical_name": "t", "type": "file", "extension": "txt"}]}
    with_metadata = {
        "type": "directory",
        "children": [{"semantical_name": "t", "type": "file", "extension": "txt", "min_size": 0}],
    }
    for s in (schema, with_metadata):
        assert rules(run_validation(s, tree(".txt"))) == ["file_extension"]


def test_every_unmatched_entry_is_reported(tree):
    schema = {
        "type": "directory",
        "children": [
            {"semantical_name": "a", "type": "file", "extension": ".jpg"},
            {"semantical_name": "b", "type": "file", "extension": ".png"},
        ],
    }
    report = run_validation(schema, tree("x.gif"))
    assert rules(report) == ["unexpected_entry"]


def test_counts_rebalance_catch_all_before_specific(tree):
    schema = """
    type: directory
    children:
      - {semantical_name: any_csv, type: file, extension: .csv}
      - {semantical_name: summary, type: file, pattern_name: summary, extension: .csv, required: true}
    """
    report = run_validation(schema, tree("data.csv", "summary.csv"))
    assert report.is_valid(), messages(report)
    registry = report.context["registry"]
    assert [c.name for c in registry.get_contexts_by_name("summary")] == ["summary.csv"]
    assert [c.name for c in registry.get_contexts_by_name("any_csv")] == ["data.csv"]


def test_counts_rebalance_respects_max_count(tree):
    schema = """
    type: directory
    children:
      - {semantical_name: first, type: file, extension: .txt, max_count: 1}
      - {semantical_name: rest, type: file, extension: .txt}
    """
    report = run_validation(schema, tree("a.txt", "b.txt", "c.txt"))
    assert report.is_valid(), messages(report)
    assert report.stats.matches == {"root": 1, "first": 1, "rest": 2}


def test_rebalance_never_breaks_the_donor_minimum(tree):
    schema = """
    type: directory
    children:
      - {semantical_name: any_csv, type: file, extension: .csv, required: true}
      - {semantical_name: summary, type: file, pattern_name: summary, extension: .csv, required: true}
    """
    # Only one csv: it can't satisfy both, so exactly one count problem is reported
    report = run_validation(schema, tree("summary.csv"))
    assert rules(report) == ["min_count"]


def test_rebalance_with_directories(tree):
    schema = """
    type: directory
    children:
      - semantical_name: any_dir
        type: directory
        children: [{semantical_name: f, type: file}]
      - semantical_name: special
        type: directory
        pattern_name: special
        required: true
        children: [{semantical_name: g, type: file}]
    """
    report = run_validation(schema, tree("x/1", "special/2"))
    assert report.is_valid(), messages(report)
    registry = report.context["registry"]
    assert [c.name for c in registry.get_contexts_by_name("g")] == ["2"]
    assert [c.name for c in registry.get_contexts_by_name("f")] == ["1"]


def test_optional_capture_group_substitutes_empty_string(tree):
    schema = r"""
    type: directory
    children:
      - semantical_name: run
        type: directory
        pattern_name: '(?:(?P<p>\d+)_)?run'
        children:
          - {semantical_name: data, type: file, pattern_name: "{p}data"}
    """
    assert run_validation(schema, tree("run/data")).is_valid()
    assert run_validation(schema, tree("7_run/7data")).is_valid()
    assert not run_validation(schema, tree("7_run/data")).is_valid()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_permissions_special_bits(tree):
    root = tree("shared/")
    os.chmod(root / "shared", 0o2775)  # noqa: S103
    schema = {
        "type": "directory",
        "children": [{"semantical_name": "shared", "type": "directory", "permissions": "0775"}],
    }
    assert run_validation(schema, root).is_valid()  # permission bits only
    schema["children"][0]["permissions"] = "2775"
    assert run_validation(schema, root).is_valid()
    schema["children"][0]["permissions"] = "4775"
    assert messages(run_validation(schema, root)) == ["Expected permissions 4775, got 2775"]


def test_schema_parse_regressions():
    import yaml as _yaml

    from katachi.schema.importer import SchemaError

    with pytest.raises(SchemaError, match="'pattern_name' must be a string"):
        parse_schema(_yaml.safe_load("type: directory\npattern_name: 0123"))
    with pytest.raises(SchemaError, match="invalid regular expression in option 'key_pattern'"):
        parse_schema({
            "type": "directory",
            "children": [
                {"semantical_name": "a", "type": "file"},
                {
                    "semantical_name": "p",
                    "type": "predicate",
                    "predicate_type": "pair_comparison",
                    "elements": ["a"],
                    "options": {"key_pattern": "(["},
                },
            ],
        })
    with pytest.raises(SchemaError, match="contains a path separator"):
        parse_schema({"type": "directory", "ignore": ["build/"]})
    # A child may share its parent's semantical name and still be a predicate element
    parse_schema({
        "semantical_name": "a",
        "type": "directory",
        "children": [
            {"semantical_name": "a", "type": "file", "extension": ".txt"},
            {"semantical_name": "p", "type": "predicate", "predicate_type": "count_match", "elements": ["a"]},
        ],
    })


def test_hidden_file_extension_message(tree):
    schema = {
        "type": "directory",
        "children": [{"semantical_name": "a", "type": "file", "pattern_name": "a", "extension": ".txt"}],
    }
    report = run_validation(schema, tree(".DS_Store"))
    assert messages(report)[0] == "File extension mismatch: expected .txt, got no extension"
    assert "got '.DS_Store'" in messages(report)[1]
