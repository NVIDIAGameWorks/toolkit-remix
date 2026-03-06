## Command: Create Extension

Scaffold a new extension from scratch. Follow every step in order. All file templates live in
`docs_dev/architecture/extension-guide.md` — read them there rather than reproducing them.

### Step 0 — Get the Author

Read the author from git config:

```bash
git config user.name   # e.g. "Pierre-Olivier Trottier"
git config user.email  # e.g. "ptrottier@nvidia.com"
```

If either value is empty or missing, ask the user for the missing information.

Carry `"Full Name <email>"` into the `authors` field of `config/extension.toml`.

### Step 1 — Confirm the Extension Name & Namespace

Ask (or confirm from context) the full extension name, e.g. `omni.flux.my_feature.core`.

- RTX Remix-specific → `lightspeed.trex.*` | Reusable → `omni.flux.*`
- Suffix: `.core` `.widget` `.window` `.menu` `.controller` `.model` `.service` `.plugin.*` `.bundle` (see
  `docs_dev/architecture/overview.md`)

Derive the Python package path: dots → slashes (`omni.flux.job_queue.core` → `omni/flux/job_queue/core/`). Premake root:
`omni/` for flux, `lightspeed/` for trex.

### Step 2 — Create Directories

Under `source/extensions/<ext-name>/`, create the directory structure from `docs_dev/architecture/extension-guide.md` →
Directory Layout.

### Step 3 — Write `config/extension.toml`

Use the template from `docs_dev/architecture/extension-guide.md` → `extension.toml` Reference. Substitute all
placeholders. Use `lightspeed.trex.tests.dependencies` for trex exts, `omni.flux.tests.dependencies` for flux.

### Step 4 — Write `premake5.lua`

Use the boilerplate from `docs_dev/architecture/extension-guide.md` → `premake5.lua` Boilerplate. Adjust the root
namespace (`lightspeed/` or `omni/`).

### Step 5 — Write Python stubs

Use the templates from `docs_dev/architecture/extension-guide.md` → Python Module Stubs. Replace `<YEAR>`, `<ext-name>`,
and `MyExtension` with actual values.

Files to create: `__init__.py` and `extension.py` in the package root.

### Step 6 — Write `docs/CHANGELOG.md`

Use the starter from `docs_dev/architecture/extension-guide.md` → `docs/CHANGELOG.md` Starter.

### Step 7 — Write `docs/README.md`

Do not leave a one-line stub. Fill in the full structure from `docs_dev/architecture/extension-guide.md` → README
Structure section based on what the user has described.

### Step 8 — Write `docs/index.rst`

Use the pattern from `docs_dev/architecture/extension-guide.md` → `docs/index.rst`.

### Step 9 — Write `tests/__init__.py`

Use the export pattern from `docs_dev/architecture/extension-guide.md` → `tests/__init__.py` Export Pattern. Leave
`unit/__init__.py` and `e2e/__init__.py` as empty files.

### Step 10 — Remind the User

- Replace the placeholder dependency in `config/extension.toml` with actual imports. Add `"omni.flux.pip_archive" = {}`
  for any third-party pip packages.
- New extensions load via dependencies in other extensions — only add to a `.kit` app file if this is a standalone
  top-level UI entry point.
- Run `.\build.bat` to verify the extension builds and links correctly.
