"""Top-level API, filesystem helpers, plugins and display helpers."""

from __future__ import annotations

import os
import sys

import fsspec
import pytest
from rich.console import Console

import katachi
from katachi.display.report_display import create_detailed_report_tree, relative_path, summary_line
from katachi.utils import fs_utils
from katachi.utils.fs_utils import get_filesystem
from katachi.utils.plugins import PluginError, load_plugin
from katachi.validation.snapshot import Entry, FsSnapshot

SCHEMA = {
    "semantical_name": "root",
    "type": "directory",
    "children": [{"semantical_name": "image", "type": "file", "extension": ".jpg", "required": True}],
}


def test_validate_accepts_dict_path_and_node(tree, tmp_path):
    root = tree("a.jpg")
    assert katachi.validate(SCHEMA, str(root)).is_valid()

    schema_file = tmp_path / "schema.yaml"
    schema_file.write_text("type: directory\nchildren: [{semantical_name: image, type: file, extension: .png}]\n")
    report = katachi.validate(str(schema_file), str(root))
    assert [f.validator_name for f in report.failures] == ["file_extension"]

    node = katachi.load_schema(str(schema_file))
    assert isinstance(node, katachi.SchemaDirectory)
    assert not katachi.validate(node, str(root)).is_valid()

    with pytest.raises(katachi.SchemaError):
        katachi.validate({"type": "nope"}, str(root))


def test_validate_fsspec_url():
    fs = fsspec.filesystem("memory")
    fs.pipe({"/api/x.jpg": b""})
    assert katachi.validate(SCHEMA, "memory://api").is_valid()


def test_get_filesystem_local_and_url():
    fs, path = get_filesystem("some/local/dir")
    assert path == "some/local/dir"
    assert "file" in fs.protocol
    fs, path = get_filesystem("memory://bucket/data")
    assert path == "/bucket/data"


def test_get_filesystem_unknown_protocol():
    with pytest.raises(ValueError, match="Unsupported filesystem protocol: nosuch"):
        get_filesystem("nosuch://x")


def test_get_filesystem_missing_optional_package(monkeypatch):
    def raise_import_error(path, **kwargs):
        raise ImportError("No module named 's3fs'")

    monkeypatch.setattr(fs_utils, "url_to_fs", raise_import_error)
    with pytest.raises(ValueError, match="pip install s3fs"):
        get_filesystem("s3://bucket/x")


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"AZURE_STORAGE_CONNECTION_STRING": "cs"}, {"connection_string": "cs"}),
        (
            {"AZURE_STORAGE_ACCOUNT_NAME": "acc", "AZURE_STORAGE_SAS_TOKEN": "sas"},
            {"account_name": "acc", "sas_token": "sas"},
        ),
        (
            {"AZURE_STORAGE_ACCOUNT": "acc", "AZURE_STORAGE_ACCESS_KEY": "key"},
            {"account_name": "acc", "account_key": "key"},
        ),
        ({"AZURE_STORAGE_ACCOUNT_NAME": "acc"}, {"account_name": "acc"}),
    ],
)
def test_azure_credentials_from_environment(monkeypatch, env, expected):
    for key in list(os.environ):
        if key.startswith("AZURE_STORAGE"):
            monkeypatch.delenv(key)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    seen = {}

    def fake_url_to_fs(path, **kwargs):
        seen.update(kwargs)
        return fsspec.filesystem("memory"), "/container"

    monkeypatch.setattr(fs_utils, "url_to_fs", fake_url_to_fs)
    get_filesystem("abfs://container")
    assert seen == expected


def test_azure_without_credentials(monkeypatch):
    for key in list(os.environ):
        if key.startswith("AZURE_STORAGE"):
            monkeypatch.delenv(key)
    with pytest.raises(ValueError, match="AZURE_STORAGE_ACCOUNT_NAME"):
        get_filesystem("abfs://container/path")


def test_plugin_by_module_name(tmp_path, monkeypatch):
    (tmp_path / "my_katachi_plugin.py").write_text("LOADED = True\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    assert load_plugin("my_katachi_plugin").LOADED
    with pytest.raises(PluginError, match="ModuleNotFoundError"):
        load_plugin("no_such_katachi_plugin")


def test_plugin_file_that_raises(tmp_path):
    plugin = tmp_path / "broken.py"
    plugin.write_text("raise RuntimeError('nope')\n")
    with pytest.raises(PluginError, match="RuntimeError: nope"):
        load_plugin(str(plugin))


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="needs POSIX permissions as non-root")
def test_unreadable_directory_is_reported(tree):
    root = tree("locked/a.jpg")
    os.chmod(root / "locked", 0)
    try:
        report = katachi.validate(
            {
                "type": "directory",
                "children": [
                    {
                        "semantical_name": "locked",
                        "type": "directory",
                        "children": [{"semantical_name": "img", "type": "file"}],
                    }
                ],
            },
            str(root),
        )
    finally:
        os.chmod(root / "locked", 0o700)
    assert [f.validator_name for f in report.failures] == ["directory_listing"]


def test_snapshot_skips_self_in_listing_and_caches():
    class SelfListingFS(fsspec.implementations.memory.MemoryFileSystem):
        calls = 0

        def ls(self, path, detail=True, **kwargs):
            SelfListingFS.calls += 1
            return [{"name": path, "type": "directory", "size": 0}, *super().ls(path, detail=True, **kwargs)]

    fs = SelfListingFS()
    fs.pipe({"/s/a.txt": b"x"})
    snapshot = FsSnapshot(fs)
    entries = snapshot.listdir("/s")
    assert [e.name for e in entries] == ["a.txt"]
    assert entries[0].size == 1
    snapshot.listdir("/s")
    assert SelfListingFS.calls == 1


def test_entry_repr_and_lazy_stat(tmp_path):
    (tmp_path / "f.bin").write_bytes(b"12345")
    [entry] = FsSnapshot(fsspec.filesystem("file")).listdir(str(tmp_path))
    assert repr(entry).startswith("Entry(")
    assert entry.size == 5
    assert entry.is_file and not entry.is_dir
    assert Entry("/x", "x", "other").size is None


def test_display_helpers(tree):
    root = tree("a.jpg", "b.png")
    report = katachi.validate(SCHEMA, str(root))
    assert relative_path(str(root / "a.jpg"), report.root_path) == "a.jpg"
    assert relative_path(report.root_path, report.root_path) == "."
    assert relative_path("/elsewhere/x", report.root_path) == "/elsewhere/x"
    assert summary_line(report, 1.5).startswith("✗ Invalid: 1 error · 3 entries checked in 1.50s")
    console = Console(record=True, width=120)
    console.print(create_detailed_report_tree(report))
    assert "b.png" in console.export_text()


def test_relative_path_normalizes_windows_separators(monkeypatch):
    from katachi.display import report_display

    monkeypatch.setattr(report_display.os, "sep", "\\")
    assert relative_path("C:\\data\\root\\a.jpg", "C:/data/root") == "a.jpg"
    assert relative_path("C:/data/root", "C:\\data\\root\\") == "."


def test_importing_katachi_does_not_touch_application_logging():
    import subprocess

    code = (
        "from loguru import logger\n"
        "import io\n"
        "sink = io.StringIO()\n"
        "logger.add(sink)\n"
        "import katachi, katachi.cli\n"
        "logger.info('app message')\n"
        "assert 'app message' in sink.getvalue(), 'application handlers must survive importing katachi'\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)  # noqa: S603 - fixed code, own interpreter


def test_version_attribute():
    from importlib import metadata

    assert katachi.__version__ == metadata.version("katachi")
