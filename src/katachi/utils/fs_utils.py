"""Resolving paths/URLs to fsspec filesystems."""

from __future__ import annotations

import os

import fsspec
from fsspec import AbstractFileSystem
from fsspec.core import url_to_fs

AZURE_CREDENTIALS_ERROR = (
    "Azure Blob Storage credentials not found in environment variables. Set AZURE_STORAGE_ACCOUNT_NAME "
    "(or AZURE_STORAGE_ACCOUNT) together with AZURE_STORAGE_SAS_TOKEN or AZURE_STORAGE_ACCOUNT_KEY, "
    "or set AZURE_STORAGE_CONNECTION_STRING."
)
UNSUPPORTED_PROTOCOL_ERROR = "Unsupported filesystem protocol: {}"

#: Extra to install for protocols whose fsspec implementation lives in an optional package
PROTOCOL_EXTRAS = {
    "abfs": "katachi[azure]",
    "az": "katachi[azure]",
    "abfss": "katachi[azure]",
    "s3": "s3fs",
    "s3a": "s3fs",
    "gs": "gcsfs",
    "gcs": "gcsfs",
}


def _azure_options() -> dict[str, str]:
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if connection_string:
        return {"connection_string": connection_string}
    account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME") or os.getenv("AZURE_STORAGE_ACCOUNT")
    if not account_name:
        raise ValueError(AZURE_CREDENTIALS_ERROR)
    options = {"account_name": account_name}
    sas_token = os.getenv("AZURE_STORAGE_SAS_TOKEN")
    account_key = os.getenv("AZURE_STORAGE_ACCOUNT_KEY") or os.getenv("AZURE_STORAGE_ACCESS_KEY")
    if sas_token:
        options["sas_token"] = sas_token
    elif account_key:
        options["account_key"] = account_key
    # Without a key or token adlfs falls back to anonymous / DefaultAzureCredential authentication
    return options


def get_filesystem(path: str) -> tuple[AbstractFileSystem, str]:
    """
    Get the appropriate filesystem based on the path prefix.
    If no prefix is provided, return the local filesystem.

    Any fsspec URL works (``memory://``, ``s3://``, ``gs://``, ``zip::s3://...``, ...) as long as
    the implementing package is installed. For ``abfs://`` credentials are read from the
    ``AZURE_STORAGE_*`` environment variables.

    Args:
        path: Path to the file/directory, can include fsspec prefix (e.g., 'abfs://')

    Returns:
        Tuple of (filesystem, path_without_prefix)

    Raises:
        ValueError: For unknown protocols, missing optional packages or missing credentials
    """
    if "://" not in path:
        # Local filesystem
        return fsspec.filesystem("file"), path

    protocol = path.split("://", 1)[0].split("::")[-1]
    options: dict[str, str] = {}
    if protocol in ("abfs", "az", "abfss"):
        options = _azure_options()
    try:
        fs, path_without_prefix = url_to_fs(path, **options)
    except ValueError as e:
        raise ValueError(UNSUPPORTED_PROTOCOL_ERROR.format(protocol)) from e
    except ImportError as e:
        extra = PROTOCOL_EXTRAS.get(protocol)
        hint = f" Install it with: pip install {extra}" if extra else ""
        raise ValueError(f"Support for '{protocol}://' paths is not installed ({e}).{hint}") from e
    return fs, path_without_prefix
