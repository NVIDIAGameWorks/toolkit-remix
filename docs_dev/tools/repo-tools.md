# Repo Tools

All root-level scripts, utilities, and CLI launchers. Most root scripts are thin wrappers around `repo.bat` (which
dispatches to `tools/repoman/repoman.py`).

---

## Root Scripts

| Tool                  | Description                                                                                         | Args                                                                 |
|-----------------------|-----------------------------------------------------------------------------------------------------|----------------------------------------------------------------------|
| `build.bat`           | Incremental build. Output: `_build/windows-x86_64/release/`                                         | `-c` clean only, `-x` clean + rebuild, `-r -u` update deps to latest |
| `format_code.bat`     | Auto-format Python (ruff). Use `--check` to verify without modifying files (exits non-zero if dirty) | `--check` dry-run only                                               |
| `lint_code.bat`       | Lint Python with ruff                                                                               | `all` — run all checks with auto-fix                                 |
| `build_docs.bat`      | Build Sphinx documentation. Output: `_build/docs/`                                                  | *(none)*                                                             |
| `install_hooks.bat`   | Install pre-commit (format on commit) and pre-push (lint on push) git hooks                         | `-f` force reinstall over legacy hooks                               |
| `uninstall_hooks.bat` | Remove git hooks                                                                                    | `-c` also remove `.venv/`                                            |
| `create_venv.bat`     | Create Python venv at `.venv/` using packman's Python. Called automatically by `install_hooks.bat`. | *(none)*                                                             |

> Linux/Mac equivalents: replace `.bat` with `.sh`.
>
> Skip hooks temporarily: `git commit --no-verify` / `git push --no-verify`. Run hooks manually:
`pre-commit run --all-files`.

**Lint caveat:** `lint_code.bat all` auto-fixes issues and may report "0 errors" in the `repo_lint` summary even when
unfixable errors remain. Always check the full ruff output for lines like `Found X errors (Y fixed, Z remaining)` —
the summary line alone is not reliable.

---

## Common Issues

### Kit cannot initialize Python after worktree cleanup

If Kit or extension tests crash during startup with `failed to get the Python codec of the filesystem encoding`, the
shared packman Python install is likely broken. This can happen after cleaning up git worktrees because the default
cleanup path can remove files from the shared packman package cache.

To recover:

1. Find the packman cache from `PM_PACKAGES_ROOT` (defaults to `C:/packman-repo`).
2. Delete that packman cache directory.
3. Rebuild from the repo root with:

   ```powershell
   .\build.bat -x
   ```

The rebuild redownloads a valid Kit/Python package set.

---

## Run

| Tool                                   | Description                                                            |
|----------------------------------------|------------------------------------------------------------------------|
| `lightspeed.app.trex_dev.bat`          | Developer mode — extra logging, hot-reload *(default for development)* |
| `lightspeed.app.trex.bat`              | Full Toolkit — test the release experience                             |
| `lightspeed.app.trex.stagecraft.bat`   | Modding Layout (StageCraft)                                            |
| `lightspeed.app.trex.texturecraft.bat` | AI Tools Layout (TextureCraft)                                         |
| `lightspeed.app.trex.ingestcraft.bat`  | Ingestion Layout (IngestCraft)                                         |

All launchers are in `_build\windows-x86_64\release\`. If the bat doesn't exist, run `build.bat` first.

| Launch flag                                | Effect                                             |
|--------------------------------------------|----------------------------------------------------|
| `--/telemetry/enableSentry=false`          | Disable Sentry (avoid creating tickets during dev) |
| `--/rtx/verifyDriverVersion/enabled=false` | Skip driver-version check on startup               |

---

## Repo Subcommands (`repo.bat`)

Tools prefixed with `repo_` are custom subcommands registered with `repo.bat`. Run them via `repo.bat <subcommand>` (
e.g., `repo.bat check_changelog`). They live in `tools/utils/` and are dispatched through `tools/repoman/repoman.py`.

| Subcommand                          | Description                                                      |
|-------------------------------------|------------------------------------------------------------------|
| `repo.bat bump_changed_extensions`  | Bump versions in `config/extension.toml` for changed extensions  |
| `repo.bat check_changelog`          | Verify all modified extensions have changelog entries (CI)       |
| `repo.bat check_test_file_location` | Verify `test_*.py` files are in required directories (CI)        |
| `repo.bat check_forbidden_words`    | Validate that specified words are not present in code files (CI) |

## Standalone Utilities (`tools/utils/`)

| Tool                                                 | Description                                     |
|------------------------------------------------------|-------------------------------------------------|
| `python tools/utils/list_changed_exts.py`            | List extensions changed vs. main branch         |
| `python tools/utils/update_pyright_from_settings.py` | Sync Pyright config from VSCode `settings.json` |

---

## CLI Launchers (generated in `_build/`)

| Tool                                      | Description                              |
|-------------------------------------------|------------------------------------------|
| `lightspeed.app.trex.migration.cli.bat`   | Run USD compatibility migrations         |
| `lightspeed.app.trex.ingestcraft.cli.bat` | Ingestion CLI (headless asset ingestion) |
