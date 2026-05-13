## create-extension

Scaffold extension. Templates live in `docs_dev/architecture/extension-guide.md`; read there, do not copy from memory.

## Step 0 - Author

```bash
git config user.name
git config user.email
```

Missing value -> ask. Use `"Full Name <email>"` in `config/extension.toml` `authors`.

## Step 1 - Name

Ask/confirm full ext name, example `omni.flux.my_feature.core`.

- Remix-specific -> `lightspeed.trex.*`; reusable -> `omni.flux.*`.
- Suffixes: `.core`, `.widget`, `.window`, `.menu`, `.model`, `.service`, `.plugin.*`, `.bundle`.
- Feature entry ext wires pieces; match nearby repo naming/loading.
- Python path: dots -> slashes. Example `omni.flux.job_queue.core` -> `omni/flux/job_queue/core/`.
- Premake root: Flux `omni/`; Trex `lightspeed/`.

## Steps 2-9 - Files

Create under `source/extensions/<ext-name>/`, following `docs_dev/architecture/extension-guide.md`:

1. Directory layout.
2. `config/extension.toml`; use `lightspeed.trex.tests.dependencies` for Trex, `omni.flux.tests.dependencies` for Flux.
3. `premake5.lua`; correct root namespace.
4. Python stubs: package `__init__.py` + `extension.py`; replace year/name/class.
5. `docs/CHANGELOG.md`.
6. Full `docs/README.md`; no one-line stub.
7. `docs/index.rst`.
8. `tests/__init__.py` export pattern. Leave `unit/__init__.py` and `e2e/__init__.py` empty.

## Step 10 - Verify

Mandatory:

```bash
.\build.bat
```

Fix failures. Common: missing `premake5.lua`, wrong namespace root, bad `[[python.module]]`, missing `__init__.py`.

## Step 11 - Remind User

- Replace placeholder deps with actual imports.
- Add `omni.flux.pip_archive` for third-party pip.
- New ext loads through deps; add to `.kit` only if standalone top-level UI entry.
