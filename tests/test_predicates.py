"""Predicates: relationships between matched entries."""

from __future__ import annotations

from importlib import resources

from katachi.validation.core import ValidationResult
from katachi.validation.predicates import register_predicate
from tests.conftest import messages, rules, run_validation

PAIRS = """
type: directory
children:
  - {semantical_name: image, type: file, pattern_name: "img\\\\d+", extension: .jpg}
  - {semantical_name: meta, type: file, pattern_name: "img\\\\d+", extension: .json}
  - semantical_name: pairs
    type: predicate
    predicate_type: pair_comparison
    elements: [image, meta]
"""


def test_pairs_complete(tree):
    report = run_validation(PAIRS, tree("img1.jpg", "img1.json", "img2.jpg", "img2.json"))
    assert report.is_valid()
    passed = [r for r in report.results if r.is_valid]
    assert passed[0].message == "All 2 image/meta groups are complete"


def test_missing_counterparts_are_reported_both_ways(tree):
    report = run_validation(PAIRS, tree("img1.jpg", "img1.json", "img2.jpg", "img3.json"))
    assert sorted(messages(report)) == [
        "'img2.jpg' (image) has no matching meta (key 'img2')",
        "'img3.json' (meta) has no matching image (key 'img3')",
    ]
    assert {r.path.rsplit("/", 1)[-1] for r in report.failures} == {"img2.jpg", "img3.json"}


def test_predicates_are_scoped_to_each_directory_instance(tree):
    schema = """
    type: directory
    children:
      - semantical_name: day
        type: directory
        pattern_name: "day\\\\d"
        children:
          - {semantical_name: image, type: file, extension: .jpg}
          - {semantical_name: meta, type: file, extension: .json}
          - {semantical_name: pairs, type: predicate, predicate_type: pair_comparison, elements: [image, meta]}
    """
    # a.jpg in day1 must not be paired with a.json in day2
    report = run_validation(schema, tree("day1/a.jpg", "day2/a.json"))
    assert len(report.failures) == 2
    assert {f.path.split("/")[-2] for f in report.failures} == {"day1", "day2"}
    assert run_validation(schema, tree("day1/a.jpg", "day1/a.json", "day2/b.jpg", "day2/b.json")).is_valid()


def test_predicate_at_root_pairs_across_subdirectories(tree):
    schema = """
    type: directory
    children:
      - semantical_name: images
        type: directory
        pattern_name: images
        children: [{semantical_name: image, type: file, extension: .jpg}]
      - semantical_name: labels
        type: directory
        pattern_name: labels
        children: [{semantical_name: label, type: file, extension: .txt}]
      - {semantical_name: labeled, type: predicate, predicate_type: pair_comparison, elements: [image, label]}
    """
    assert run_validation(schema, tree("images/a.jpg", "labels/a.txt")).is_valid()
    report = run_validation(schema, tree("images/a.jpg", "images/b.jpg", "labels/a.txt"))
    assert messages(report) == ["'b.jpg' (image) has no matching label (key 'b')"]


def test_key_template_with_captures_yolo_template(tree):
    schema = resources.files("katachi.templates").joinpath("yolo.yaml").read_text()
    good = tree("data.yaml", "images/train/a.jpg", "labels/train/a.txt", "images/val/b.png", "labels/val/b.txt")
    assert run_validation(schema, good).is_valid()


def test_key_template_detects_cross_split_mismatch(tree):
    schema = resources.files("katachi.templates").joinpath("yolo.yaml").read_text()
    # Same stem, different splits: must not count as a pair
    report = run_validation(schema, tree("data.yaml", "images/train/a.jpg", "labels/val/a.txt"))
    assert sorted(messages(report)) == [
        "'a.jpg' (image) has no matching label (key 'train/a')",
        "'a.txt' (label) has no matching image (key 'val/a')",
    ]


def test_key_pattern_option(tree):
    schema = """
    type: directory
    children:
      - {semantical_name: raw, type: file, pattern_name: "raw_\\\\d+", extension: .csv}
      - {semantical_name: clean, type: file, pattern_name: "clean_\\\\d+", extension: .csv}
      - semantical_name: pairs
        type: predicate
        predicate_type: pair_comparison
        elements: [raw, clean]
        options: {key_pattern: "_(?P<key>\\\\d+)"}
    """
    assert run_validation(schema, tree("raw_1.csv", "clean_1.csv")).is_valid()
    assert rules(run_validation(schema, tree("raw_1.csv", "clean_2.csv"))) == ["pair_comparison"] * 2


def test_count_match(tree):
    schema = PAIRS.replace("pair_comparison", "count_match")
    assert run_validation(schema, tree("img1.jpg", "img2.json")).is_valid()
    report = run_validation(schema, tree("img1.jpg", "img2.jpg", "img2.json"))
    assert messages(report) == ["Element counts differ: image=2, meta=1"]


def test_unique_keys(tree):
    schema = """
    type: directory
    children:
      - {semantical_name: image, type: file, extension: [.jpg, .png]}
      - {semantical_name: unique, type: predicate, predicate_type: unique_keys, elements: [image]}
    """
    assert run_validation(schema, tree("a.jpg", "b.png")).is_valid()
    report = run_validation(schema, tree("a.jpg", "a.png"))
    assert rules(report) == ["unique_keys"]
    assert "Duplicate key 'a'" in messages(report)[0]


def test_predicate_severity(tree):
    schema = PAIRS + "    severity: warning\n"
    report = run_validation(schema, tree("img1.jpg"))
    assert report.is_valid()
    assert len(report.warnings) == 1


def test_predicates_are_skipped_when_structure_is_invalid(tree):
    report = run_validation(PAIRS, tree("img1.jpg", "junk.txt"))
    assert rules(report) == ["unexpected_entry"]
    assert report.predicates_skipped
    assert not run_validation(PAIRS, tree("img1.jpg", "img1.json")).predicates_skipped


def test_unknown_predicate_type(tree):
    report = run_validation(PAIRS.replace("pair_comparison", "nope"), tree("img1.jpg", "img1.json"))
    assert "Unknown predicate type 'nope'" in messages(report)[0]
    assert "pair_comparison" in messages(report)[0]


def test_custom_predicate(tree):
    seen = {}

    @register_predicate("at_least_two")
    def at_least_two(predicate, dir_path, elements):
        seen.update({k: [c.name for c in v] for k, v in elements.items()})
        ok = len(elements["image"]) >= 2
        return [ValidationResult(ok, "need two images", dir_path, "at_least_two", predicate.semantical_name)]

    schema = PAIRS.replace("pair_comparison", "at_least_two")
    assert not run_validation(schema, tree("img1.jpg")).is_valid()
    assert seen == {"image": ["img1.jpg"], "meta": []}


def test_crashing_predicate_is_reported(tree):
    register_predicate("boom", lambda predicate, dir_path, elements: 1 / 0)
    report = run_validation(PAIRS.replace("pair_comparison", "boom"), tree("img1.jpg"))
    assert messages(report) == ["Predicate failed with an error: division by zero"]
