# add-pip-dep

Add third-party pip package for extension runtime. Full ref: `docs_dev/patterns/pip-packages.md`.

## Critical

License + OSRB required for every new package. Apache-2.0/MIT/BSD usually OK; avoid GPL/LGPL. Tell user OSRB required
and link `docs_dev/patterns/pip-packages.md` "Step 0 - License Check".

## Steps

1. Add exact version to `deps/pip_flux.toml` with OSRB comment; use doc format.
2. Build:

   ```powershell
   .\build.bat
   ```

3. Every importing extension declares:

   ```toml
   [dependencies]
   "omni.flux.pip_archive" = {}
   ```

4. Verify import in test.
5. After merge to `main`, CI publishes new `pip_repo_cache`; private by default. Remind user to make cache public.
