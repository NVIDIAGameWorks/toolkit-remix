# Adding Pip Package Dependencies

Third-party Python packages are bundled via `omni.flux.pip_archive`. Do not add packages to a `requirements.txt` or
install them any other way — the runtime environment is frozen and `pip install` is not available.

---

## How It Works

`omni.flux.pip_archive` is an extension that adds a pre-bundled package directory to `sys.path` when it loads.
Extensions that declare it as a dependency get all bundled packages on their import path automatically.

The bundle is built from `deps/pip_flux.toml` during `.\build.bat`. If a package you need is not already in the archive,
add it following the steps below.

---

## Step 0 — License Check (Required Before Adding)

Confirm the package's license is compatible with Omniverse:

- **Acceptable:** Apache-2.0, MIT, BSD, PSF
- **Avoid:** GPL, LGPL (these impose redistribution constraints)

An **OSRB (Open Source Review Board) ticket must be filed** for every new package added — this is a hard requirement
before the PR can be merged. OSRB is an NVIDIA-internal process:

- **NVIDIA employees:** file an Open Source Software Request using the templates at
  [Open Source Software Requests (Confluence)](https://nvidia.atlassian.net/wiki/spaces/LEG/pages/2417590688/Open+Source+Software+Requests).
  Record the NVBugs ticket number inline in `pip_flux.toml` before the PR is merged.
- **External contributors:** an NVIDIA employee must file the OSRB ticket on your behalf. Note the package name,
  version, and license in your PR description. The reviewing NVIDIA employee will file the ticket and update the
  comment before merging.

---

## Step 1 — Add to `deps/pip_flux.toml`

Add the package with a pinned version to the `packages` array in the existing `[[dependency]]` block:

```text
"package-name==1.2.3",     # OSRB filed under: https://nvbugs/XXXXXXX
```

**Rules:**

- Pin to an exact version (`==`). Never use ranges — this is a static bundle, not a live install.
- Add the OSRB ticket reference, or `# OSRB filed under: TODO` if not yet filed.
- If the package requires a non-standard index URL (e.g. PyTorch), add it to `extra_args` — check whether one already
  exists before adding.

---

## Step 2 — Build

```batch
.\build.bat
```

This triggers the pip prebundle step and downloads the package into `_build/target-deps/flux_pip_prebundle/`.

---

## Step 3 — Declare the Runtime Dependency

In every extension that imports the new package, add to `config/extension.toml`:

```toml
[dependencies]
"omni.flux.pip_archive" = {}
```

Without this, the import will fail at runtime even if the build succeeded — `sys.path` won't include the bundle
directory.

---

## Step 4 — Verify

Import the package in a test or the extension itself and run it to confirm it loads. If the import fails:

1. Check that `"omni.flux.pip_archive" = {}` is in `[dependencies]`.
2. Check that the build completed without errors.
3. Check that the package name in `pip_flux.toml` matches exactly what you're importing.

---

## Step 5 — After Merging to Main

Merging a new package to `main` triggers a CI build that publishes a new `pip_repo_cache`. **This cache is private by
default.** After the merge completes, the cache must be manually set to public so that users and downstream CI pipelines
can download the archive. Check with the team on where to do this if you're unsure.
