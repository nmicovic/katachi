# Security Policy

## Supported versions

Security fixes are released for the latest minor version of Katachi.

## Reporting a vulnerability

Please report vulnerabilities privately through
[GitHub security advisories](https://github.com/nmicovic/katachi/security/advisories/new)
rather than public issues. You can expect an initial answer within a week.

## Security model

- **Schemas are data.** They are parsed with `yaml.safe_load` and never execute code. Patterns
  are regular expressions evaluated with Python's `re` module; as with any regex engine, a
  pathological pattern can be slow, so treat schemas from untrusted sources like any other
  configuration you run.
- **Plugins are code.** Actions, validators and predicates are only loaded when explicitly
  passed with `--plugin` (or imported by your own Python code). Only load plugins you trust.
- **Katachi only reads.** Validation lists directories and reads metadata; it never modifies,
  moves or deletes files. Actions you register may, since they are your code.
- **Credentials** for remote filesystems are read from the environment by the underlying fsspec
  implementations (e.g. `AZURE_STORAGE_*` for `abfs://`) and are never logged or included in reports.
