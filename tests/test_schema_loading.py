"""Schema parsing: helpful errors, normalization, JSON Schema."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

import jsonschema
import pytest
import yaml

from katachi.schema.importer import ALLOWED_KEYS, SchemaError, load_schema_file, load_yaml, parse_schema
from katachi.schema.json_schema import PROPERTIES, build_json_schema
from katachi.schema.schema_node import SchemaDirectory, SchemaFile, SchemaNode
from katachi.utils.fs_utils import get_filesystem

REPO = Path(__file__).parent.parent
FIXTURE_SCHEMAS = sorted((REPO / "tests").glob("schema*/*/schema.yaml"))
TEMPLATES = sorted(p.name for p in resources.files("katachi.templates").iterdir() if p.name.endswith(".yaml"))


def error_of(doc: str) -> SchemaError:
    with pytest.raises(SchemaError) as info:
        parse_schema(yaml.safe_load(doc))
    return info.value


@pytest.mark.parametrize(
    ("doc", "expected"),
    [
        ("type: directory\nchildren:\n  - {semantical_name: a, type: fille}", "invalid node type 'fille'"),
        ("type: directory\nchildren:\n  - {semantical_name: a, type: fille}", "did you mean 'file'?"),
        (
            "type: directory\nchildren:\n  - {semantical_name: a, type: file, patern_name: x}",
            "unknown key 'patern_name' for a file node (did you mean 'pattern_name'?)",
        ),
        ("type: directory\nchildren:\n  - {type: file}", "missing required key 'semantical_name'"),
        ("semantical_name: x", "missing required key 'type'"),
        ("type: directory\npattern_name: '[a-'", "invalid regular expression"),
        ("type: directory\npermissions: 0750", "quote the value"),
        ("type: directory\npermissions: '999'", "octal string"),
        ("type: directory\nrequired: 'yes'", "'required' must be true or false"),
        ("type: directory\nmin_count: -1", "non-negative integer"),
        ("type: directory\nmin_count: 3\nmax_count: 1", "greater than 'max_count'"),
        ("type: directory\nchildren: {a: 1}", "'children' must be a list"),
        ("type: directory\nseverity: fatal", "invalid severity 'fatal'"),
        ("type: directory\nname_case: snake", "did you mean 'snake_case'?"),
        (
            "type: directory\nchildren:\n  - {semantical_name: p, type: predicate, predicate_type: pair_comparison}",
            "non-empty 'elements' list",
        ),
        (
            "type: directory\nchildren:\n"
            "  - {semantical_name: image, type: file}\n"
            "  - {semantical_name: p, type: predicate, predicate_type: pair_comparison, elements: [imagee]}",
            "unknown element 'imagee' (did you mean 'image'?)",
        ),
        (
            "type: directory\nchildren:\n  - {semantical_name: f, type: file, pattern_name: '{scene}_x'}",
            "no parent pattern captures a group named 'scene'",
        ),
        ("[1, 2]", "expected a mapping"),
    ],
)
def test_schema_errors(doc, expected):
    assert expected in str(error_of(doc))


def test_error_location_names_the_node_path():
    doc = """
    semantical_name: dataset
    type: directory
    children:
      - semantical_name: day
        type: directory
        children:
          - {semantical_name: image, type: file, extention: .jpg}
    """
    error = error_of(doc)
    assert error.location == "dataset > day > image"
    assert str(error).startswith("dataset > day > image: unknown key 'extention'")


def test_file_errors(tmp_path):
    with pytest.raises(SchemaError, match="not found"):
        load_schema_file(str(tmp_path / "missing.yaml"))
    (tmp_path / "empty.yaml").write_text("  \n")
    with pytest.raises(SchemaError, match="empty"):
        load_schema_file(str(tmp_path / "empty.yaml"))
    (tmp_path / "bad.yaml").write_text("type: [directory\n")
    with pytest.raises(SchemaError, match="invalid YAML"):
        load_schema_file(str(tmp_path / "bad.yaml"))
    # The legacy API logs and returns None instead of raising
    fs, path = get_filesystem(str(tmp_path / "bad.yaml"))
    assert load_yaml(path, str(tmp_path), fs, fs) is None


def test_parsed_nodes_are_normalized():
    schema = parse_schema(
        yaml.safe_load(
            """
            type: directory
            ignore: .DS_Store
            children:
              - {semantical_name: a, type: file, extension: jpg, required: true}
              - {semantical_name: b, type: file, extension: [png, .tar.gz, .gz]}
            """
        ),
        "/data",
    )
    assert isinstance(schema, SchemaDirectory)
    assert schema.semantical_name == "root"
    assert schema.ignore == [".DS_Store"]
    a, b = schema.children
    assert isinstance(a, SchemaFile) and isinstance(b, SchemaFile)
    assert a.extensions == (".jpg",)
    assert a.effective_min_count == 1
    assert a.path == "/data/a"
    assert b.extensions[0] == ".tar.gz"  # longest first
    assert b.split_name("x.tar.gz") == ("x", ".tar.gz")


def test_from_dict_backwards_compatible():
    node = SchemaNode.from_dict({"semantical_name": "x", "type": "file", "extension": "txt"}, "/p")
    assert isinstance(node, SchemaFile)
    assert node.extension == ".txt"
    assert SchemaNode.from_dict({"type": "bogus", "semantical_name": "x"}, "/p") is None


@pytest.mark.parametrize("path", FIXTURE_SCHEMAS, ids=lambda p: p.parent.name)
def test_fixture_schemas_load(path):
    load_schema_file(str(path))


def test_json_schema_covers_every_key():
    for keys in ALLOWED_KEYS.values():
        assert keys <= set(PROPERTIES)


def test_committed_json_schema_is_up_to_date():
    committed = json.loads((REPO / "katachi.schema.json").read_text())
    assert committed == build_json_schema(), "run: uv run katachi json-schema > katachi.schema.json"


@pytest.mark.parametrize("path", FIXTURE_SCHEMAS, ids=lambda p: p.parent.name)
def test_fixture_schemas_match_json_schema(path):
    jsonschema.validate(yaml.safe_load(path.read_text()), build_json_schema())


@pytest.mark.parametrize("name", TEMPLATES)
def test_templates_are_valid(name):
    text = resources.files("katachi.templates").joinpath(name).read_text()
    assert text.startswith("# yaml-language-server: $schema=")
    jsonschema.validate(yaml.safe_load(text), build_json_schema())
    parse_schema(yaml.safe_load(text))


def test_json_schema_rejects_typos():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {"type": "directory", "children": [{"semantical_name": "a", "type": "file", "extention": ".jpg"}]},
            build_json_schema(),
        )


def test_yaml_alias_bomb_is_rejected_quickly(tmp_path):
    import time

    lines = ["a0: &a0 {semantical_name: x, type: file}"]
    for i in range(1, 25):
        lines.append(f"a{i}: &a{i} {{semantical_name: d{i}, type: directory, children: [*a{i - 1}, *a{i - 1}]}}")
    lines.append("schema: *a24")
    data = yaml.safe_load("\n".join(lines))["schema"]
    start = time.perf_counter()
    with pytest.raises(SchemaError, match="more than 100000 nodes"):
        parse_schema(data)
    assert time.perf_counter() - start < 5


def test_yaml_anchors_can_reuse_subtrees():
    doc = """
    type: directory
    children:
      - &split
        semantical_name: train
        type: directory
        pattern_name: train
        children: [{semantical_name: image, type: file, extension: .jpg}]
      - <<: *split
        semantical_name: val
        pattern_name: val
    """
    schema = parse_schema(yaml.safe_load(doc))
    assert [c.semantical_name for c in schema.children] == ["train", "val"]


@pytest.mark.parametrize("key", ["description", "pattern_name", "ignore", "semantical_name"])
def test_alias_bombs_in_values_fail_fast(key):
    import time

    lines = ["metadata:", "  a0: &a0 [x, x]"]
    lines += [f"  a{i}: &a{i} [*a{i - 1}, *a{i - 1}]" for i in range(1, 40)]
    lines += ["type: directory", f"{key}: *a39"]
    data = yaml.safe_load("\n".join(lines))
    start = time.perf_counter()
    with pytest.raises(SchemaError) as info:
        parse_schema(data)
    assert time.perf_counter() - start < 2
    assert len(str(info.value)) < 400


def test_recursive_and_deep_schemas_are_schema_errors():
    with pytest.raises(SchemaError, match="recursive YAML alias"):
        parse_schema(yaml.safe_load("&n {type: directory, semantical_name: x, children: [*n]}"))
    deep: dict = {"type": "file", "semantical_name": "leaf"}
    for i in range(1500):
        deep = {"type": "directory", "semantical_name": f"d{i}", "children": [deep]}
    with pytest.raises(SchemaError, match="nested deeper than 200 levels"):
        parse_schema(deep)
