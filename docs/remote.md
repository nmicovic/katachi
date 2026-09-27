# Remote storage

Katachi reads directories through [fsspec](https://filesystem-spec.readthedocs.io), so the schema
and the target can be any fsspec URL. Install the implementation for your storage:

| Storage | URL | Install |
|---------|-----|---------|
| Amazon S3 (and S3-compatible: MinIO, R2, Ceph, ...) | `s3://bucket/prefix` | `pip install katachi s3fs` |
| Azure Blob Storage / Data Lake | `abfs://container/prefix` | `pip install "katachi[azure]"` |
| Google Cloud Storage | `gs://bucket/prefix` | `pip install katachi gcsfs` |
| Anything else fsspec supports (HTTP, SFTP, zip archives, ...) | e.g. `zip::s3://bucket/data.zip` | the matching fsspec package |

```bash
katachi validate katachi.yaml s3://my-bucket/datasets/2025
katachi validate s3://my-bucket/schemas/katachi.yaml s3://my-bucket/datasets/2025   # schema in the bucket too
katachi infer s3://my-bucket/datasets/2025 -o katachi.yaml
```

```python
import katachi

report = katachi.validate("katachi.yaml", "gs://my-bucket/datasets/2025")
```

## Credentials

Credentials come from the storage library's usual configuration; Katachi never logs them.

- **S3**: the standard AWS configuration (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`, `AWS_PROFILE`,
  instance roles, ...). For S3-compatible services set `AWS_ENDPOINT_URL`.
- **Azure**: `AZURE_STORAGE_CONNECTION_STRING`, or `AZURE_STORAGE_ACCOUNT_NAME` (or
  `AZURE_STORAGE_ACCOUNT`) with `AZURE_STORAGE_SAS_TOKEN` or `AZURE_STORAGE_ACCOUNT_KEY`. With only an
  account name, authentication is left to adlfs (see its documentation for anonymous and Azure
  identity access).
- **GCS**: Application Default Credentials (`GOOGLE_APPLICATION_CREDENTIALS`, `gcloud auth`, ...).

## How object stores differ from disks

- **Directories are key prefixes.** An empty directory can't exist on S3/GCS/Azure Blob (without
  hierarchical namespace), so a `required` directory needs at least one object inside it.
- **No POSIX metadata.** `permissions` and `owner` checks are skipped with a warning.
- **Fast, concurrent listings.** Each directory is listed once, and up to 16 listings run in
  parallel (`--workers N` to change it). Validation never downloads file contents; sizes come
  from the listings.
- **Always fresh.** Listings are re-read on every validation, even though the storage libraries
  cache them on shared filesystem instances.

Remote support is tested against a local S3 API ([moto](https://github.com/getmoto/moto)) in CI.
