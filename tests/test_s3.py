"""
Integration tests against a real S3 API (a local moto server), through the same ``s3://`` URLs users pass.

Object stores differ from local disks: directories are only key prefixes (an empty directory can't
exist), listings return keys, and there are no POSIX permissions or owners.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator

import pytest
import yaml

moto_server = pytest.importorskip("moto.server")
s3fs = pytest.importorskip("s3fs")

import katachi  # noqa: E402
from katachi.schema.infer import dump_schema, infer_schema  # noqa: E402
from katachi.utils.fs_utils import get_filesystem  # noqa: E402
from tests.test_cli import invoke  # noqa: E402

BUCKET = "katachi-test"

SCHEMA = {
    "semantical_name": "dataset",
    "type": "directory",
    "children": [
        {"semantical_name": "readme", "type": "file", "pattern_name": "README", "extension": ".md", "required": True},
        {
            "semantical_name": "day",
            "type": "directory",
            "pattern_name": r"(?P<day>\d{4}-\d{2}-\d{2})",
            "min_count": 1,
            "children": [
                {"semantical_name": "image", "type": "file", "pattern_name": r"img_\d+", "extension": ".jpg"},
                {"semantical_name": "label", "type": "file", "pattern_name": r"img_\d+", "extension": ".json"},
                {
                    "semantical_name": "pairs",
                    "type": "predicate",
                    "predicate_type": "pair_comparison",
                    "elements": ["image", "label"],
                },
            ],
        },
    ],
}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def s3_endpoint() -> Iterator[str]:
    port = _free_port()
    server = moto_server.ThreadedMotoServer(ip_address="127.0.0.1", port=port, verbose=False)
    server.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.stop()


@pytest.fixture
def s3(s3_endpoint: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[s3fs.S3FileSystem]:
    """An empty bucket; configured through the standard AWS environment variables, like a user would."""
    for key, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_ENDPOINT_URL": s3_endpoint,
    }.items():
        monkeypatch.setenv(key, value)
    s3fs.S3FileSystem.clear_instance_cache()
    fs = s3fs.S3FileSystem(client_kwargs={"endpoint_url": s3_endpoint})
    if fs.exists(BUCKET):
        fs.rm(BUCKET, recursive=True)
    fs.mkdir(BUCKET)
    yield fs
    fs.rm(BUCKET, recursive=True)
    s3fs.S3FileSystem.clear_instance_cache()


def put(fs: s3fs.S3FileSystem, *keys: str) -> None:
    fs.pipe({f"{BUCKET}/{key}": b"x" for key in keys})


def test_get_filesystem_resolves_s3_urls(s3):
    fs, path = get_filesystem(f"s3://{BUCKET}/data")
    assert "s3" in fs.protocol
    assert path == f"{BUCKET}/data"


def test_valid_tree_on_s3(s3):
    put(
        s3,
        "data/README.md",
        "data/2025-01-01/img_1.jpg",
        "data/2025-01-01/img_1.json",
        "data/2025-01-02/img_2.jpg",
        "data/2025-01-02/img_2.json",
    )
    report = katachi.validate(SCHEMA, f"s3://{BUCKET}/data")
    assert report.is_valid(), [r.message for r in report.failures]
    assert report.stats.matches == {"dataset": 1, "readme": 1, "day": 2, "image": 2, "label": 2}
    captures = sorted(c.captures["day"] for c in report.context["registry"].get_contexts_by_name("image"))
    assert captures == ["2025-01-01", "2025-01-02"]


def test_problems_are_reported_with_s3_paths(s3):
    put(s3, "data/README.md", "data/2025-01-01/img_1.jpg", "data/2025-01-01/img_2.png")
    report = katachi.validate(SCHEMA, f"s3://{BUCKET}/data")
    assert [(r.validator_name, r.path) for r in report.failures] == [
        ("unexpected_entry", f"{BUCKET}/data/2025-01-01/img_2.png")
    ]
    # Fix the structure: now the missing label is reported by the predicate
    s3.rm(f"{BUCKET}/data/2025-01-01/img_2.png")
    report = katachi.validate(SCHEMA, f"s3://{BUCKET}/data")
    assert [r.message for r in report.failures] == ["'img_1.jpg' (image) has no matching label (key 'img_1')"]


def test_directories_are_prefixes(s3):
    """An empty "directory" doesn't exist on S3, so a required directory needs at least one object in it."""
    put(s3, "data/README.md")
    report = katachi.validate(SCHEMA, f"s3://{BUCKET}/data")
    assert [r.validator_name for r in report.failures] == ["min_count"]
    missing = katachi.validate(SCHEMA, f"s3://{BUCKET}/nothing-here")
    assert [r.validator_name for r in missing.failures] == ["directory_exists"]


def test_permissions_are_skipped_on_object_stores(s3):
    put(s3, "data/README.md", "data/2025-01-01/img_1.jpg", "data/2025-01-01/img_1.json")
    schema = {**SCHEMA, "permissions": "0755"}
    report = katachi.validate(schema, f"s3://{BUCKET}/data")
    assert report.is_valid()


def test_infer_from_s3_validates_the_same_tree(s3):
    put(
        s3,
        "data/README.md",
        *[f"data/2025-01-0{d}/img_{i}.{ext}" for d in (1, 2) for i in (1, 2) for ext in ("jpg", "json")],
    )
    fs, path = get_filesystem(f"s3://{BUCKET}/data")
    document = infer_schema(fs, path)
    assert any(c.get("predicate_type") == "pair_comparison" for c in document["children"][1]["children"])
    report = katachi.validate(katachi.parse_schema(yaml.safe_load(dump_schema(document))), f"s3://{BUCKET}/data")
    assert report.is_valid(), [r.message for r in report.failures]


def test_repeated_validations_see_new_objects(s3):
    """s3fs caches listings on shared instances: every validation must read fresh listings."""
    put(s3, "data/README.md", "data/2025-01-01/img_1.jpg", "data/2025-01-01/img_1.json")
    assert katachi.validate(SCHEMA, f"s3://{BUCKET}/data").is_valid()
    put(s3, "data/2025-01-01/img_2.jpg")
    assert not katachi.validate(SCHEMA, f"s3://{BUCKET}/data").is_valid()
    s3.rm(f"{BUCKET}/data/2025-01-01/img_2.jpg")
    assert katachi.validate(SCHEMA, f"s3://{BUCKET}/data").is_valid()


def test_cli_against_s3(s3, tmp_path):
    put(s3, "data/README.md", "data/2025-01-01/img_1.jpg", "data/2025-01-01/img_1.json")
    schema_file = tmp_path / "katachi.yaml"
    schema_file.write_text(yaml.safe_dump(SCHEMA))
    assert invoke("validate", schema_file, f"s3://{BUCKET}/data").exit_code == 0
    # The schema itself can live in the bucket too
    s3.put(str(schema_file), f"{BUCKET}/schemas/katachi.yaml")
    assert invoke("validate", f"s3://{BUCKET}/schemas/katachi.yaml", f"s3://{BUCKET}/data").exit_code == 0
    put(s3, "data/stray.txt")
    result = invoke("validate", schema_file, f"s3://{BUCKET}/data", "--format", "text")
    assert result.exit_code == 1
    assert "stray.txt: error [unexpected_entry]" in result.output
