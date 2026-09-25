# Schema reference

A Katachi schema is a YAML (or JSON) document describing a directory tree top-down. Each node
is a **directory**, a **file** or a **predicate** (a relationship between other nodes).

Add this first line to get completion and inline documentation in VS Code (YAML extension),
JetBrains IDEs and Neovim:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/nmicovic/katachi/main/katachi.schema.json
```

## How matching works

Validation runs in phases:

1. **Structure.** Every entry of a directory must match one of the directory's `children`,
   tried in order. When a candidate matches by name but fails deeper down, the next candidate
   is tried (backtracking), so ambiguous siblings are fine. Afterwards every child must have been
   matched the required number of times (`required`, `min_count`, `max_count`).
2. **Predicates.** Once the structure is valid, relationships such as *every image has a label*
   are checked.
3. **Actions.** Optional Python callbacks run for matched entries (see [Extending](extending.md)).

Anything a directory contains that matches none of its children is an error, unless it is
ignored (`ignore`) or allowed (`allow_extra`). A directory without `children` accepts any
content.

## Common keys

| Key | Applies to | Description |
|-----|-----------|-------------|
| `type` | all | `directory`, `file` or `predicate` (required) |
| `semantical_name` | all | Name of the node in the schema, used by predicates, actions and reports. Required except on the root. |
| `description` | all | Free text, shown by `katachi describe` |
| `metadata` | all | Free-form mapping available to custom validators and actions |
| `severity` | all | `error` (default), `warning` or `info`: severity of *count* and *predicate* violations for this node. Only errors fail validation (use `--strict` to fail on warnings too). |
| `pattern_name` | file, directory | Regular expression that must match the **whole** name. For files it is matched against the name *without* the extension. |
| `name_case` | file, directory | Naming convention: `snake_case`, `kebab-case`, `camelCase`, `PascalCase`, `SCREAMING_SNAKE_CASE`, `lowercase`, `UPPERCASE` |
| `required` | file, directory | At least one matching entry must exist in every instance of the parent (same as `min_count: 1`) |
| `min_count` / `max_count` | file, directory | Number of matching entries allowed in every instance of the parent. `max_count: 0` forbids an entry. |
| `permissions` | file, directory | Quoted octal permissions, e.g. `"0640"` (skipped on filesystems that don't report modes) |
| `owner` | file, directory | Expected owner, user name or numeric uid |

## Files

| Key | Description |
|-----|-------------|
| `extension` | Accepted extension or list of extensions: `.jpg`, `jpg`, `[.jpg, .png]`, `.tar.gz`. Extensions are case-sensitive. |
| `min_size` / `max_size` | File size bounds in bytes |

```yaml
- semantical_name: scan
  type: file
  pattern_name: "sub-\\d{3}_T1w"
  extension: [.nii, .nii.gz]
  min_size: 1024
```

## Directories

| Key | Description |
|-----|-------------|
| `children` | List of nodes describing the directory's entries |
| `ignore` | Glob(s) of entry names to skip, e.g. `[".*", "__pycache__"]` |
| `allow_extra` | Allow entries that match no child instead of reporting them |

## Captures: reusing parts of names

Named groups in a pattern capture part of a name. Descendants can require the captured value
with `{name}` placeholders (the value is regex-escaped), and actions and predicates receive the
captured values.

```yaml
- semantical_name: scene
  type: directory
  pattern_name: "(?P<scene>scene_\\d+)"
  children:
    - semantical_name: frame
      type: file
      pattern_name: "{scene}_cam\\d"       # scene_7/scene_7_cam0.jpg is valid, scene_7/scene_8_cam0.jpg is not
      extension: .jpg
```

Using a placeholder that no ancestor captures is a schema error.

## Predicates

Predicates are declared inside a directory, next to the nodes they relate. They are evaluated
**once per instance** of that directory and only see the entries found inside that instance, at
any depth. Declare a predicate at the root to relate entries across the whole tree, or deeper to
relate them per sub-directory.

| Key | Description |
|-----|-------------|
| `predicate_type` | `pair_comparison`, `count_match`, `unique_keys` or a [custom predicate](extending.md#custom-predicates) |
| `elements` | Semantical names of the nodes the predicate relates (must be declared in the same directory, at any depth) |
| `options` | Predicate options (see below) |

### Built-in predicates

**`pair_comparison`**: every entry of each element must have a counterpart with the same *key* in
every other element (`img1.jpg` ⟷ `img1.json`). Both directions are reported.

**`count_match`**: all elements occur the same number of times.

**`unique_keys`**: no two entries of the listed elements share a key (e.g. `a.jpg` next to `a.png`).

### Keys

By default the key of an entry is its name without the extension declared in the schema. Options
change that:

- `key`: a template combining `{stem}`, `{name}` and captured values, e.g. `"{split}/{stem}"`
- `key_pattern`: a regex extracting the key from the name: the named group `key`, the first
  group, or the whole match

Pairing images and labels that live in parallel trees, per split (YOLO layout):

```yaml
semantical_name: yolo_dataset
type: directory
children:
  - semantical_name: images
    type: directory
    pattern_name: images
    children:
      - semantical_name: image_split
        type: directory
        pattern_name: "(?P<split>train|val|test)"
        children:
          - {semantical_name: image, type: file, extension: [.jpg, .png]}
  - semantical_name: labels
    type: directory
    pattern_name: labels
    children:
      - semantical_name: label_split
        type: directory
        pattern_name: "(?P<split>train|val|test)"
        children:
          - {semantical_name: label, type: file, extension: .txt}
  - semantical_name: every_image_is_labeled
    type: predicate
    predicate_type: pair_comparison
    elements: [image, label]
    options:
      key: "{split}/{stem}"      # images/train/1.jpg pairs with labels/train/1.txt, not labels/val/1.txt
```

## Rules reported

Every problem has a rule name (`validator_name` in JSON output), useful to filter output:

| Rule | Meaning |
|------|---------|
| `file_exists` / `directory_exists` | Wrong entry type, or the root path doesn't exist |
| `file_extension` | Extension not accepted |
| `file_pattern` / `directory_pattern` | Name doesn't match `pattern_name` |
| `name_case` | Name doesn't follow `name_case` |
| `file_size` | Outside `min_size` / `max_size` |
| `permissions` / `owner` | Metadata mismatch |
| `unexpected_entry` | Entry matches none of the children of its directory |
| `min_count` / `max_count` | Too few / too many entries matched a node |
| `directory_listing` | A directory could not be read |
| `pair_comparison`, `count_match`, `unique_keys`, ... | Predicate violations |
| `predicate` | Unknown predicate type |

## Schema errors

Schemas are checked strictly before validation starts, with the location of the problem:

```text
dataset > day > image: unknown key 'extention' for a file node (did you mean 'extension'?)
```
