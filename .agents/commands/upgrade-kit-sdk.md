# upgrade-kit-sdk

Repo-specific notes for upgrading this repo to a new Omniverse Kit SDK version.

## Upstream First

Check [NVIDIA-Omniverse/kit-app-template](https://github.com/NVIDIA-Omniverse/kit-app-template) first for Kit-team
upgrade guidance. Use this file only for Lightspeed-specific memory.

## Ground Truth

Do not infer versions from the Kit major number alone. Read them from build outputs and package metadata:

| What | Source |
|---|---|
| Current Kit SDK package | `deps/kit-sdk.packman.xml` |
| Bundled Python and USD versions | `_build/${platform}/release/kit/dev/all-deps.packman.xml` |
| Kit SDK package dependencies | `_build/${platform}/release/kit/dev/deps/` |
| Repo tool versions | Kit SDK `repo-deps.packman.xml` and `kit-app-template` tooling files |
| Registry-visible extension versions | `build.bat -u` output from the intended registry context |

## Gotchas

### Workflow Memory

- Bump `deps/kit-sdk.packman.xml`, then let `build.bat -u` expose the next failure layer.
- Python ABI changes touch `deps/target-deps.packman.xml`, `pyproject.toml`, `.ruff.toml`, pip constraints, and
  extension `[package.target]` filters.
- Rerun `build.bat -u` after rebases, lock edits, or registry/VPN changes. For public review, do the final refresh off
  VPN on a public network.
- Keep the upgrade plan current with decisions, CI evidence, and deferred follow-ups.

### Extension Version Locks

Extension registry versions are independent of Kit SDK versions. Search both `source/apps/*.kit` and
`source/extensions/*/apps/*.kit`. `source/apps/exts.deps.generated.kit` is generated; resolve enough to continue, then
rerun `build.bat -u`.

### Python ABI Filters

Stale `python = ["cpXXX"]` filters make extensions disappear from dependency resolution without a useful mismatch line.

### Repo Tool Cascades

If a repo tool reports a minimum requirement for another tool, update the declared tool versions together.

### Precache Environments

`Couldn't find environment for app version: X.Y.Z` means `repo.toml` is missing a
`[[repo_kit_pull_extensions.environment]]` entry for that app version.

### USD Headers In Python-Only Builds

Some Kit SDK builds bundle USD internally without publishing headers to `_build/target-deps/usd/`. If premake crashes
while comparing a nil USD version, check `_build/target-deps/usd/release/include/pxr/pxr.h`. For Python-only repos, a
generated `_build` stub header with the bundled USD version can unblock premake.

### Compatibility Warnings

`Built using kit version X, current Y, considered compatible` usually comes from registry extensions. Treat as a
warning unless CI or runtime behavior proves otherwise.

### Test Log Noise

Kit upgrades can reclassify runtime output. Keep stdout exclusions narrow and evidence-based. Known benign example:

```text
*[omni.kit.scene_view.opengl] No UsdRender.Product was found at *
```

### Windows Rebase Encoding

If an automated interactive rebase fails on a valid todo command, check for a UTF-8 BOM in the todo file.

### Generated Line-Ending Noise

Builds can touch generated `.kit` files without semantic diffs. If `git status` shows modified files but diff commands
show no content change, treat it as worktree noise and keep real lock-file changes separate.

### uv Cache State

If repo tools fail while initializing the default user-profile uv cache, rerun with a workspace-local cache such as
`UV_CACHE_DIR=<repo>/_tmp/uv-cache`.

## Validation Notes

- Rebuild before tests that depend on generated apps or extension locks.
- Start with focused extension tests and unit suites before broad E2E jobs.
- Use CI logs to identify the first real failure in each job; repeated warning blocks are often secondary noise.
- Smoke the full app after dependency and viewport-related changes, especially stage loading, selection,
  manipulators, material properties, and layer panels.
- Keep commits reviewable: one upgrade concern per commit, with tests when practical.
