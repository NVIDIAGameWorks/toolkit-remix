# debug-extension-load

Diagnose why an extension fails to load, a test bat file doesn't exist, or tests can't be discovered. Work through these
steps in order and stop at the first one that reveals the problem.

*Extension load patterns: `docs_dev/architecture/overview.md` → Extension Lifecycle section*

## Step 1 — Check the Build Output Exists

```
ls _build/windows-x86_64/release/tests-<extension-name>.bat
```

If the file doesn't exist, the extension hasn't been built yet. Run `.\build.bat` and retry. If the build fails, read
the build output for errors before proceeding.

## Step 2 — Verify `[[python.module]]` Matches the Directory

The `[[python.module]]` name in `config/extension.toml` must map exactly to a real directory with an `__init__.py`. Any
mismatch causes a silent load failure. See `docs_dev/architecture/extension-guide.md` → Directory Layout for the naming
convention.

## Step 3 — Check `premake5.lua` Symlinks

The `premake5.lua` must symlink the correct root namespace (`lightspeed/` or `omni/`). A wrong root path means the
Python package is never found. See `docs_dev/architecture/extension-guide.md` → `premake5.lua` Boilerplate for the
correct pattern.

## Step 4 — Scan for Import Errors

Run the test bat without `-n default` to catch startup errors:

```
.\_build\windows-x86_64\release\tests-<extension-name>.bat
```

Look in the output and in `_testoutput/exttest_<sanitized_name>/` for tracebacks. An `ImportError` or
`ModuleNotFoundError` points to a missing dependency or a bad import path.

## Step 5 — Check Declared Dependencies

For each dependency listed in `[dependencies]` in `extension.toml`:

- Confirm the dependency name is spelled correctly (dots, not underscores).
- Confirm it is available in the build (either a local extension or a registered registry package).

If an import of a third-party pip package fails, confirm `"omni.flux.pip_archive" = {}` is in `[dependencies]`.

## Step 6 — Check `tests/__init__.py` Exports

If the extension loads but tests aren't discovered, open `<namespace>/tests/__init__.py` and confirm test classes are
exported:

```python
from .unit.test_my_module import TestMyModule
```

An empty `tests/__init__.py` causes the test runner to find nothing.

## Step 7 — Check for Circular Imports

If the traceback mentions a circular import, there is a lazy import somewhere hiding the cycle. Find it (search for
`import` inside function bodies) and fix the module boundaries — do not suppress with `# noqa: PLC0415`.
