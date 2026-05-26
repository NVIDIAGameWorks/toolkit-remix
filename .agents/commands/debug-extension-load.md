# debug-extension-load

Diagnose load failure, missing test bat, test discovery. Stop at first cause. Ref:
`docs_dev/architecture/overview.md` Extension Lifecycle.

## 1 - Build Output

```powershell
ls _build/windows-x86_64/release/tests-<extension-name>.bat
```

Missing -> run `.\build.bat`, then retry. Build fail -> read errors first.

## 2 - Python Module

`[[python.module]]` in `config/extension.toml` must map exactly to directory with `__init__.py`. Mismatch -> silent load
fail. Ref: `docs_dev/architecture/extension-guide.md` Directory Layout.

## 3 - Premake Symlink

`premake5.lua` must symlink correct root: `lightspeed/` or `omni/`. Wrong root -> package not found. Ref:
`docs_dev/architecture/extension-guide.md` `premake5.lua` Boilerplate.

## 4 - Import Errors

Run without `-n default`:

```powershell
.\_build\windows-x86_64\release\tests-<extension-name>.bat -- --no-window
```

Check stdout + `_testoutput/exttest_<sanitized_name>/` for traceback. `ImportError`/`ModuleNotFoundError` -> missing dep
or bad import path.

## 5 - Dependencies

For each `[dependencies]` item: spelling uses dots; dep exists locally or registry. Third-party pip import fail ->
confirm `omni.flux.pip_archive`.

## 6 - Test Exports

If loads but tests missing, check `<namespace>/tests/__init__.py` exports classes:

```python
from .unit.test_my_module import TestMyModule
```

Empty `tests/__init__.py` -> runner finds nothing.

## 7 - Circular Imports

Traceback says circular import -> find lazy imports (`import` inside functions) and fix boundaries. Do not suppress with
`# noqa: PLC0415`.
