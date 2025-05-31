import os

import fsspec
from fsspec import AbstractFileSystem

AZURE_CREDENTIALS_ERROR = "Azure Blob Storage credentials not found in environment variables. Please set AZURE_STORAGE_ACCOUNT_NAME and AZURE_STORAGE_SAS_TOKEN."
UNSUPPORTED_PROTOCOL_ERROR = "Unsupported filesystem protocol: {}"


def get_filesystem(path: str) -> tuple[AbstractFileSystem, str]:
    """
    Get the appropriate filesystem based on the path prefix.
    If no prefix is provided, return the local filesystem.

    Args:
        path: Path to the file/directory, can include fsspec prefix (e.g., 'abfs://')

    Returns:
        Tuple of (filesystem, path_without_prefix)
    """
    if "://" in path:
        protocol, path_without_prefix = path.split("://", 1)

        if protocol == "abfs":
            # Get Azure credentials from environment variables
            account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
            sas_token = os.getenv("AZURE_STORAGE_SAS_TOKEN")

            if not account_name or not sas_token:
                raise ValueError(AZURE_CREDENTIALS_ERROR)
            fs = fsspec.filesystem("abfs", account_name=account_name, sas_token=sas_token)
            return fs, path_without_prefix
        else:
            raise ValueError(UNSUPPORTED_PROTOCOL_ERROR.format(protocol))

    # Local filesystem
    return fsspec.filesystem("file"), path
