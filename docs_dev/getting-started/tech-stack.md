# Tech Stack Overview

How the toolchain fits together — from `build.bat` to a running app with loaded extensions.

---

## Components

| Component       | What it is                                                                                                                                                                                                                               | Where it lives                              |
|-----------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------|
| **repoman**     | NVIDIA repo orchestration tool. Coordinates dependencies, building, testing, packaging, and publishing. All `repo.bat` subcommands dispatch through it.                                                                                  | `tools/repoman/repoman.py`                  |
| **packman**     | Binary package manager. Downloads and caches build dependencies (Kit SDK, premake, runtime assets) from NVIDIA servers. Packages are cached in `C:\packman-repo\` (Windows) or `~/.cache/packman/` (Linux) and symlinked into `_build/`. | `tools/packman/`                            |
| **Kit SDK**     | The Omniverse application framework. Provides the extension system, UI framework (`omni.ui`), USD integration, and an embedded Python 3.10 interpreter. Pulled in by packman via `deps/kit-sdk.packman.xml`.                             | `_build/windows-x86_64/release/kit/`        |
| **premake**     | Build system generator. In this repo, primarily used to discover extensions and create symlinks from `source/` to `_build/exts/` so Kit can load source code directly without copying.                                                   | `_build/host-deps/premake/`                 |
| **Python 3.10** | Bundled with Kit — no system Python required. All extensions, tools, and scripts run under Kit's embedded interpreter.                                                                                                                   | `_build/windows-x86_64/release/kit/python/` |

---

## Dependency Files (`deps/`)

| File                      | What it pulls                                                             |
|---------------------------|---------------------------------------------------------------------------|
| `kit-sdk.packman.xml`     | Kit SDK (kit-kernel) — the application framework + embedded Python        |
| `repo-deps.packman.xml`   | Repo tools (repo_build, repo_test, repo_format, repo_kit_tools, etc.)     |
| `host-deps.packman.xml`   | Build-time tools (premake)                                                |
| `target-deps.packman.xml` | Runtime dependencies (RTX Remix runtime, HDRemix models, AI tools models) |
| `pip_flux.toml`           | Open-source Python packages (frozen pip archive — see below)              |
| `pip_internal.toml`       | NVIDIA internal Python packages (frozen pip archive — see below)          |

---

## Pip Dependencies

Third-party Python packages (e.g., `pydantic`, `numpy`, `torch`) are not installed via `pip install` at runtime. They
are pre-bundled into frozen archives during the build and loaded by a dedicated extension at startup.

### Pip dependencies

| File                     | Target folder                                | Contains                                                                                                                                                                                   |
|--------------------------|----------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `deps/pip_flux.toml`     | `_build/target-deps/flux_pip_prebundle/`     | Open-source packages: `pydantic`, `numpy`, `fastapi`, `pillow`, `pygit2`, `sentry-sdk`, `huggingface-hub`, etc.                                                                            |

Repoman installs them during the build (configured in `repo.toml` under `[repo_build.fetch.pip]`).

### How packages reach extensions at runtime

1. During the build, repoman runs `pip install` from the TOML file into the prebundle folder using Kit's
   embedded Python
2. The `omni.flux.pip_archive` extension loads very early (order `-2000`) and adds the prebundle folder to `sys.path`
3. Any extension that imports a third-party package must declare `"omni.flux.pip_archive" = {}` in its
   `[dependencies]` — without it, the import will fail even though the package exists on disk
4. After merging to `main`, the prebundle is published to NVIDIA's packman servers so subsequent builds download the
   pre-built archive instead of running pip

### Why two files?

- **License separation:** open-source packages vs. proprietary NVIDIA packages require different OSRB tracking
- **Dependency layering:** internal packages declare `install_dependencies = false` because `pip_flux.toml` already
  provides all their transitive dependencies
- **Access control:** `pip_internal.toml` uses NVIDIA's internal PyPI registry, which requires VPN access

For the full procedure to add a new package, see [Adding Pip Package Dependencies](../patterns/pip-packages.md).

---

## Build Pipeline

What happens when you run `.\build.bat`:

```text
build.bat
  → repo.bat build
    → repoman.py (via Kit's Python)

      1. Resolve dependencies (packman)
         Download/cache Kit SDK, premake, runtime deps → symlink into _build/

      2. Install pip dependencies
         Read deps/pip_flux.toml → pip install into Kit's Python environment

      3. Discover extensions
         Scan source/extensions/ → find ~190 extension.toml files

      4. Generate symlinks (premake)
         For each extension: source/extensions/<name>/ → _build/exts/<name>/
         Kit reads source directly — no compile step needed for Python

      5. Run pre-build commands
         Type stub generation, CLI wrapper generation

      6. Precache extensions (optional)
         Run Kit once per app to pre-download registry dependencies into extscache/
```

---

## Build Output

```text
_build/windows-x86_64/release/
├── kit/                    ← Kit SDK (from packman)
│   ├── kit.exe             ← The application
│   ├── python/             ← Embedded Python 3.10 (+ pip packages)
│   └── exts/               ← Built-in Kit extensions
├── exts/                   ← Symlinked extensions from this repo (~190)
├── extscache/              ← Downloaded extension dependencies
├── apps/                   ← .kit app definitions
├── tests-*.bat             ← Generated test runners (one per extension)
└── lightspeed.app.*.bat    ← App launchers
```

---

## Runtime

When you launch `lightspeed.app.trex_dev.bat`:

1. Kit loads the `.kit` app file (e.g., `lightspeed.app.trex.kit`)
2. Resolves `[dependencies]` — each dependency is an extension name
3. Searches for extensions in `exts/`, `extscache/`, and `kit/exts/`
4. For each extension: loads `extension.toml`, imports the Python module, calls `on_startup()`
5. App is running with all extensions loaded

---

## Configuration

| File                                        | Purpose                                                                                            |
|---------------------------------------------|----------------------------------------------------------------------------------------------------|
| `repo.toml`                                 | Central config for repoman — controls build, test, format, lint, package, publish, and docs phases |
| `source/apps/*.kit`                         | App definitions — list which extensions to load and their settings                                 |
| `source/extensions/*/config/extension.toml` | Extension metadata — version, dependencies, settings, test config                                  |
| `source/extensions/*/premake5.lua`          | Symlink setup — maps source directories into the build output                                      |
| `deps/pip_flux.toml`                        | Open-source Python packages — installed into Kit's Python during build                             |
| `deps/pip_internal.toml`                    | NVIDIA internal Python packages — installed after `pip_flux.toml`                                  |
