# lightspeed.trex.recent_projects.core

Maintains the persisted list of recent RTX Remix projects and validates the USD layers needed to display project
details.

## Responsibilities

- Load, validate, update, and save recent-project entries.
- Read project metadata and report invalid root or non-capture sublayers.
- Cache validation details with filesystem fingerprints for the project root and every checked non-capture sublayer.
- Locate project thumbnails.

## Non-Responsibilities

- Render the recent-project list or decide when a caller-owned validation batch is persisted.
- Validate capture sublayers, which are intentionally excluded from recent-project detail validation and fingerprints.
- Open a selected project into the application workspace.

## Architecture

`RecentProjectsCore` owns the recent-project JSON file, list operations, USD validation, thumbnail lookup, and cache
mutation. Saves write a same-directory temporary file and atomically replace the recent-project JSON, preserving the
previous file when replacement fails. Each recent-project entry may contain a `validation` mapping with this schema:

```text
validation:
  schema: 2
  inputs: {game, capture}
  fingerprints: {layer_path: {exists, is_file, size, mtime_ns}}
  details: {project detail fields}
```

A cache hit requires an explicitly successful validation result (`Invalid: []`), matching game/capture inputs, and
matching fingerprints for every checked path. Invalid, missing, or malformed results are not cached, so the next request
retries validation. Changes to recent metadata, the root, or any checked non-capture sublayer invalidate cached details.

When `get_path_detail()` loads recent data itself, it immediately persists a successful cache miss. When a caller
supplies a shared recent-data mapping, the method mutates that mapping without saving it; the caller owns batching and
persistence.
