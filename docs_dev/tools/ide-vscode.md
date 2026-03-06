# VSCode / Cursor Setup

Tips and configuration for developing with VSCode or Cursor. The committed `.vscode/` files (`tasks.json`,
`launch.json`, `extensions.json`, `settings.template.json`) give you tasks, debugging, and recommended extensions out of
the box — two local-only files need to be created before everything works.

---

## Initial Setup

### 1. Create your local `settings.json`

`.vscode/settings.json` is gitignored (each developer has their own). Copy the template to get started:

```batch
copy .vscode\settings.template.json .vscode\settings.json
```

Then build the project (`Ctrl+Shift+B`) — the build populates `python.analysis.extraPaths` in `settings.json` with all
`_build/` extension paths, enabling Python autocomplete.

### 2. Create a workspace file (optional but recommended)

`.code-workspace` files are also gitignored. Create one to get the best multi-root experience:

```text
File → Save Workspace As → .vscode\lightspeed-kit.code-workspace
```

### 3. Install recommended extensions

When prompted, install the recommended extensions (or run **Extensions: Show Recommended Extensions**). Key ones:

| Extension                                      | Purpose                                                  |
|------------------------------------------------|----------------------------------------------------------|
| `charliermarsh.ruff`                           | Linter + formatter (replaces pylint/flake8/autopep8)     |
| `ms-python.python` + `anysphere.cursorpyright` | Python language server, autocomplete                     |
| `psioniq.psi-header`                           | Auto-inserts the SPDX license header on new Python files |
| `tamasfe.even-better-toml`                     | Syntax highlighting for `.toml` and `.kit` files         |
| `eamodio.gitlens`                              | Git history and blame                                    |

---

## Tasks

Run tasks via `Ctrl+Shift+B` (default build) or `Ctrl+Shift+P` → **Tasks: Run Task**:

| Task                        | What it does                                |
|-----------------------------|---------------------------------------------|
| **3. Build** *(default)*    | Incremental build — `build.bat`             |
| **4. Rebuild**              | Clean rebuild — `build.bat --rebuild`       |
| **5. Clean**                | Clean artefacts only — `build.bat --clean`  |
| **1. Format Code**          | Run `format_code.bat` (black + isort)       |
| **2. Lint Code**            | Run `lint_code.bat all` (ruff)              |
| **7. Launch (Release)**     | Start full app with VSCode debugger enabled |
| **8. Launch (Development)** | Start dev app with VSCode debugger enabled  |

The launch tasks automatically pass `--enable omni.kit.debug.vscode` so the debugger server is already running when the
app starts.

---

## Debugging

The `.vscode/launch.json` is pre-configured with a **Python: Remote Attach** config (port `3000`).

1. Use **Task 7 or 8** to launch the app — the debug server starts automatically.
2. Run the **Python: Remote Attach** launch config (`F5` or the Run panel).
3. Set breakpoints and debug normally.

For everything else — how the debug server works, debugging tests, debugging startup logic, and the PyCharm
alternative — see [Debugging Guide](debugging.md).

---

## Code Quality

**Format on save** is configured in `settings.template.json` (Ruff, modifications only) and copied into your local
`settings.json`. No manual steps needed during development once set up. For a full format pass: **Task 1. Format Code**.

**License header** is auto-inserted on new Python files via the `psioniq.psi-header` extension. The template is
configured in `settings.template.json` — just create a new `.py` file and save it.

---

## Agent Commands (Claude Code / Cursor)

Agent commands are available in both tools:

**In Claude Code** — type `/` followed by the command name, or describe the operation naturally:

- `/create-extension` — scaffold a new extension
- `/bump-exts-changelog` — bump versions and update changelogs
- `/add-omni-command` — implement an undoable action
- `/add-pip-dep` — add a third-party pip package
- `/add-service-endpoint` — add a REST endpoint
- `/debug-extension-load` — diagnose extension load failures
- `/remove-extension` — safely remove an extension
- `/update-remix-deps` — update RTX Remix target dependencies

You don't need to type the slash command explicitly — Claude Code recognizes intent. If you say "make a new extension
called X" or "run the tests for Y", it will load and follow the right command automatically.

**In Cursor** — commands are available via the AI panel. The same command files in `.cursor/commands/` are automatically
picked up.

Full command procedures live in `.agents/commands/`. The `.claude/commands/` and `.cursor/commands/` files are thin
wrappers that reference them.
