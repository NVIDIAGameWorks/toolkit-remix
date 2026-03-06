# add-pip-dep

Add a new third-party Python package (pip dependency) to the project so it is available to extensions at runtime.

*Full reference: `docs_dev/patterns/pip-packages.md`*

## Important — License Check and OSRB Ticket Required

Confirm license compatibility (Apache-2.0, MIT, BSD are fine; avoid GPL/LGPL). An OSRB ticket **must** be filed for
every new package. See `docs_dev/patterns/pip-packages.md` → "Step 0 — License Check" for the full OSRB process,
including instructions for NVIDIA employees vs. external contributors. **Tell the user explicitly** about the OSRB
requirement and link them to the docs.

## Step 1 — Add to `deps/pip_flux.toml`

Pin to exact version with OSRB comment. See `docs_dev/patterns/pip-packages.md` for the exact format.

## Step 2 — Build

```
.\build.bat
```

## Step 3 — Declare the Runtime Dependency

Add to every extension that imports the package:

```toml
[dependencies]
"omni.flux.pip_archive" = {}
```

## Step 4 — Verify

Import in a test and confirm it loads.

## Step 5 — After Merging to Main

Merging a new package to `main` triggers a CI build that publishes a new `pip_repo_cache`. **This cache is private by
default.** After the merge completes, the cache must be manually set to public so that users and CI can download the
archive. Remind the user to do this after their PR is merged.
