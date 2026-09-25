"""End-to-end CLI tests: exit codes, output formats, plugins, templates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from katachi.cli import TEMPLATES, app

runner = CliRunner()
FIXTURES = Path("tests/schema_tests")
FAILING = Path("tests/schema_falling_tests")


def invoke(*args: str):
    return runner.invoke(app, [str(a) for a in args])


@pytest.mark.parametrize(
    ("schema", "target"),
    [
        ("test_sanity/schema.yaml", "test_sanity/dataset"),
        ("test_depth_1/schema.yaml", "test_depth_1/dataset"),
        ("test_paired_files/schema.yaml", "test_paired_files/data"),
        ("test_depth_2/schema.yaml", "test_depth_2/dataset_root"),
        ("test_ambiguous_dirs/schema.yaml", "test_ambiguous_dirs/root"),
    ],
)
def test_valid_fixtures_exit_zero(schema, target):
    result = invoke("validate", FIXTURES / schema, FIXTURES / target)
    assert result.exit_code == 0, result.output
    assert "✓ Valid" in result.output


def test_invalid_tree_exits_one():
    result = invoke("validate", FAILING / "simple_missing_image/schema.yaml", FAILING / "simple_missing_image/data")
    assert result.exit_code == 1
    assert "File extension mismatch" in result.output
    assert "✗ Invalid: 1 error" in result.output


def test_schema_error_exits_two(tmp_path):
    bad = tmp_path / "schema.yaml"
    bad.write_text("type: directory\nchildren:\n  - {semantical_name: a, type: fille}\n")
    result = invoke("validate", bad, tmp_path)
    assert result.exit_code == 2
    assert "did you mean 'file'" in result.output
    assert invoke("describe", bad).exit_code == 2
    assert invoke("validate", tmp_path / "missing.yaml", tmp_path).exit_code == 2


def test_bad_arguments_exit_two():
    schema, target = FIXTURES / "test_sanity/schema.yaml", FIXTURES / "test_sanity/dataset"
    assert invoke("validate", schema, target, "--format", "xml").exit_code == 2
    assert invoke("validate", schema, target, "--context", "{nope").exit_code == 2
    assert invoke("validate", schema, target, "--context", "[1]").exit_code == 2
    assert invoke("validate", schema, target, "--plugin", "does/not/exist.py").exit_code == 2
    assert invoke("validate", schema, "nosuchproto://x").exit_code == 2


def test_json_output():
    result = invoke(
        "validate", FAILING / "simple_wrong_name_image/schema.yaml", FAILING / "simple_wrong_name_image/data", "-f", "json"
    )
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["valid"] is False
    assert data["failure_count"] == 1
    [problem] = data["results"]
    assert problem["validator_name"] == "file_pattern"
    assert problem["relative_path"] == "wrong_name.jpg"
    assert data["stats"]["entries_checked"] == 2


def test_github_and_text_output():
    args = (FAILING / "simple_missing_image/schema.yaml", FAILING / "simple_missing_image/data")
    github = invoke("validate", *args, "--format", "github")
    assert github.output.startswith("::error file=tests/schema_falling_tests/simple_missing_image/data/meta.json")
    assert "title=katachi file_extension::File extension mismatch" in github.output
    text = invoke("validate", *args, "--format", "text")
    assert text.output.splitlines()[0] == "meta.json: error [file_extension] File extension mismatch: expected .jpg, got .json"


def test_strict_turns_warnings_into_failures(tmp_path):
    schema = tmp_path / "schema.yaml"
    schema.write_text(
        "type: directory\nchildren:\n"
        "  - {semantical_name: readme, type: file, pattern_name: README, extension: .md, required: true, severity: warning}\n"
    )
    data = tmp_path / "data"
    data.mkdir()
    assert invoke("validate", schema, data).exit_code == 0
    assert invoke("validate", schema, data, "--strict").exit_code == 1


def test_report_length_clips_output(tmp_path):
    schema = tmp_path / "schema.yaml"
    schema.write_text("type: directory\nchildren:\n  - {semantical_name: a, type: file, extension: .jpg}\n")
    data = tmp_path / "data"
    data.mkdir()
    for i in range(12):
        (data / f"f{i}.png").touch()
    result = invoke("validate", schema, data, "--report-length", "5")
    assert "7 more problem(s) not shown" in result.output


def test_ignore_option(tmp_path):
    schema = tmp_path / "schema.yaml"
    schema.write_text("type: directory\nchildren:\n  - {semantical_name: a, type: file, extension: .jpg}\n")
    data = tmp_path / "data"
    data.mkdir()
    (data / "a.jpg").touch()
    (data / ".DS_Store").touch()
    assert invoke("validate", schema, data).exit_code == 1
    assert invoke("validate", schema, data, "--ignore", ".*").exit_code == 0


def test_plugin_actions_are_executed(tmp_path):
    plugin = tmp_path / "my_actions.py"
    out = tmp_path / "seen.txt"
    plugin.write_text(
        "from katachi import register_action\n"
        "@register_action('image_item')\n"
        "def record(node, path, parents, context):\n"
        f"    open({str(out)!r}, 'a').write(context['tag'] + ':' + path.rsplit('/', 1)[-1] + '\\n')\n"
    )
    result = invoke(
        "validate",
        FIXTURES / "test_sanity/schema.yaml",
        FIXTURES / "test_sanity/dataset",
        "--plugin",
        plugin,
        "--execute-actions",
        "--context",
        '{"tag": "x"}',
        "--detail-report",
    )
    assert result.exit_code == 0, result.output
    assert sorted(out.read_text().split()) == ["x:img1.jpg", "x:img2.jpg", "x:img3.jpg"]
    assert "Actions" in result.output


def test_failing_action_exits_one(tmp_path):
    plugin = tmp_path / "boom.py"
    plugin.write_text(
        "from katachi import register_action\nregister_action('image_item', lambda *a: 1 / 0)\n"
    )
    result = invoke(
        "validate", FIXTURES / "test_sanity/schema.yaml", FIXTURES / "test_sanity/dataset", "-p", plugin,
        "--execute-actions",
    )
    assert result.exit_code == 1


def test_check_schema(tmp_path):
    bad = tmp_path / "bad.katachi.yaml"
    bad.write_text("type: directory\nchildren: [{semantical_name: a, type: file, extention: .jpg}]\n")
    good = FIXTURES / "test_sanity/schema.yaml"
    assert invoke("check-schema", good).exit_code == 0
    result = invoke("check-schema", good, bad)
    assert result.exit_code == 1
    assert "did you mean 'extension'" in result.output


def test_verbose_flag():
    assert invoke("-v", "describe", FIXTURES / "test_sanity/schema.yaml").exit_code == 0


def test_describe():
    result = invoke("describe", FIXTURES / "test_paired_files/schema.yaml")
    assert result.exit_code == 0
    assert "image img\\d+.jpg" in result.output
    assert "pair_comparison(image, metadata)" in result.output


def test_infer_then_validate(tmp_path):
    out = tmp_path / "inferred.yaml"
    target = FIXTURES / "test_depth_2/dataset_root"
    assert invoke("infer", target, "-o", out).exit_code == 0
    assert invoke("validate", out, target).exit_code == 0
    assert invoke("infer", tmp_path / "missing").exit_code == 2


@pytest.mark.parametrize("template", TEMPLATES)
def test_init_templates(tmp_path, template):
    out = tmp_path / f"{template}.yaml"
    result = invoke("init", "--template", template, "--output", out)
    assert result.exit_code == 0, result.output
    assert invoke("describe", out).exit_code == 0
    # Refuses to overwrite without --force
    assert invoke("init", "--template", template, "--output", out).exit_code == 2
    assert invoke("init", "--template", template, "--output", out, "--force").exit_code == 0


def test_init_list_and_unknown():
    result = invoke("init", "--list")
    assert result.output.split() == list(TEMPLATES)
    assert invoke("init", "--template", "nope").exit_code == 2


def test_json_schema_command():
    result = invoke("json-schema")
    assert json.loads(result.output)["title"] == "Katachi schema"


def test_version():
    result = invoke("--version")
    assert result.exit_code == 0
    assert result.output.startswith("katachi ")


def test_yolo_template_end_to_end(tmp_path):
    schema = tmp_path / "katachi.yaml"
    invoke("init", "-t", "yolo", "-o", schema)
    data = tmp_path / "ds"
    for p in ["data.yaml", "images/train/1.jpg", "labels/train/1.txt", "images/val/2.jpg", "images/val/3.JPG"]:
        (data / p).parent.mkdir(parents=True, exist_ok=True)
        (data / p).touch()

    # Structure first: exactly one precise error (no cascading "missing images/" noise)
    result = invoke("validate", schema, data, "-f", "json")
    assert result.exit_code == 1
    [problem] = [r for r in json.loads(result.output)["results"] if not r["is_valid"]]
    assert problem["relative_path"] == "images/val/3.JPG"
    assert "did you mean '3.jpg' for image?" in problem["message"]

    # Then the pairing predicate: images/val/2.jpg has no labels/val/2.txt
    (data / "images/val/3.JPG").unlink()
    result = invoke("validate", schema, data, "-f", "text")
    assert result.exit_code == 1
    assert result.output.splitlines()[0] == (
        "images/val/2.jpg: error [pair_comparison] '2.jpg' (image) has no matching label (key 'val/2')"
    )
