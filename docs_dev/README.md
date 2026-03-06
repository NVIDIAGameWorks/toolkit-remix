# Developer Documentation

Internal reference for contributors to the NVIDIA RTX Remix Toolkit.

---

## Quick Start

### Prerequisites

- Windows 10 or 11
- Git
- GPU with RTX support
- ~50 GB free disk space

For full hardware and software requirements, see [Technical Requirements](../docs/introduction/intro-requirements.md).

### Get the Source Code

```batch
git clone https://github.com/NVIDIAGameWorks/toolkit-remix.git
cd toolkit-remix
```

### Build the Project

```batch
.\build.bat
```

The first build downloads all dependencies (Kit SDK, Python 3.10, tools) automatically via packman. Subsequent builds
are incremental. See [Tech Stack Overview](getting-started/tech-stack.md) for how the build pipeline works.

### Run the App

```batch
.\_build\windows-x86_64\release\lightspeed.app.trex_dev.bat
```

Developer mode — includes verbose logging and extension hot-reload. See [Repo Tools → Run](tools/repo-tools.md#run) for
all launch options and flags.

### Format Your Code

```batch
.\format_code.bat
```

Auto-formats all Python files with ruff (style + import sorting) and C++ files with clang-format. Run before every
commit to avoid formatting-only diffs in review. See [Repo Tools → Root Scripts](tools/repo-tools.md#root-scripts) for
all available scripts.

### Lint Your Code

```batch
.\lint_code.bat all
```

Runs ruff checks with auto-fix. Catches common errors, unused imports, and style violations that formatting alone
doesn't cover. Both format and lint can be automated with pre-commit hooks —
see [Repo Tools → Root Scripts](tools/repo-tools.md#root-scripts).

### Run Tests

```batch
.\_build\windows-x86_64\release\tests-<extension.name>.bat -n default
```

Runs user-written tests for a single extension. See [Running Tests](code-quality/testing.md) for filtering, coverage,
and troubleshooting.

### Build the Documentation

```batch
.\build_docs.bat
```

Builds the Sphinx documentation locally. Output lands in `_build/docs/`. Useful for previewing doc changes before
submitting. See [Repo Tools → Root Scripts](tools/repo-tools.md#root-scripts) for all available scripts.

### Submit a Pull Request

Before opening a PR, check every item in the [Review Checklist](getting-started/review-checklist.md): branch naming (
`dev/<user>/<feature>`), version bumps for modified extensions, changelog entries, and ≥75% test coverage on new code.

#### External Contributors

Fork this repository, create a development branch, and submit a Pull Request against `main`. An automated bot will
prompt you to sign
the [Contributor License Agreement](https://github.com/NVIDIAGameWorks/toolkit-remix/blob/main/.github/workflows/cla/NVIDIA_CLA_v1.0.1.md)
via your PR's comment page.

---

## Table of Contents

### Getting Started

| Page                                                        | Description                                                                                                                                         |
|-------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------|
| [Tech Stack Overview](getting-started/tech-stack.md)        | How repoman, packman, Kit SDK, premake, and Python fit together. The build pipeline from `build.bat` to a running app.                              |
| [Git Workflow](getting-started/git-workflow.md)             | Branch naming, commit format, and merge request process.                                                                                            |
| [Running Tests](code-quality/testing.md)                    | Test commands, filtering with `-f`, troubleshooting (registry sync, timeouts), and coverage reports.                                                |
| [Review Checklist](getting-started/review-checklist.md)     | Pre-submission checklist: action undoability, USD context compatibility, dependency management, docstrings, version bumping, and changelog updates. |
| [Learning Resources](getting-started/learning-resources.md) | Kit SDK, USD, and Omniverse documentation and video tutorials.                                                                                      |

### Architecture & Design

| Page                                               | Description                                                                                                                                                                 |
|----------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [Code Architecture](architecture/overview.md)      | USD contexts, extension lifecycle, design principles, event subscriptions, and system-level patterns (Commands, Factory/Plugin, Settings, Job Queue, Pip Archive).          |
| [Extension Guide](architecture/extension-guide.md) | Extension naming, dependency direction, namespaces, directory layout, `extension.toml` reference, `premake5.lua` boilerplate, Python stubs, and `docs/README.md` structure. |

### Code Quality Standards

| Page                                                           | Description                                                                                                                                     |
|----------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------|
| [Code Style](code-quality/code-style.md)                       | Python 3.10, max 120 chars, black + isort + ruff, naming conventions, no lazy imports, `__all__`, license headers, and Google-style docstrings. |
| [Engineering Standards](code-quality/engineering-standards.md) | Fix root causes, never paper over. Anti-patterns table and smell tests for broken async, swallowed exceptions, and design problems.             |
| [Testing Standards](code-quality/testing.md)                   | 75% coverage requirement, plan-before-code, unit vs E2E, Arrange/Act/Assert, test naming, and anti-patterns.                                    |

### Implementation Patterns

| Page                                                                      | Description                                                                                                |
|---------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------|
| [Building UI Components](patterns/ui-style.md)                            | `omni.ui` layout guidelines: alignment, spacing, dimensions, and Remix stylesheet conventions.             |
| [Implementing Commands](patterns/commands.md)                             | Undoable user actions with `omni.kit.commands.Command`: `do()`/`undo()`, grouping, dispatch, and testing.  |
| [Implementing Service Endpoints](patterns/services.md)                    | REST endpoints with `ServiceBase` and `omni.flux.service.factory`: routing, registration, and testing.     |
| [Implementing Stage Manager Plugins](patterns/stage-manager.md)           | The Stage Manager plugin system: 8 plugin types, schema config, and Flux/Lightspeed layering.              |
| [Implementing Ingestion Pipeline Plugins](patterns/ingestion-pipeline.md) | Validation framework: 4 plugin types, execution flow, DataFlow, and mass validation.                       |
| [Adding Pip Package Dependencies](patterns/pip-packages.md)               | Third-party packages via `omni.flux.pip_archive`: OSRB requirement, `pip_flux.toml`, and post-merge steps. |

### Development Tools

| Page                                         | Description                                                                                                          |
|----------------------------------------------|----------------------------------------------------------------------------------------------------------------------|
| [Repo Tools](tools/repo-tools.md)            | All root-level scripts: build, run, format, lint, build docs, pre-commit hooks, repo subcommands, and CLI launchers. |
| [VSCode / Cursor Setup](tools/ide-vscode.md) | Workspace setup, recommended extensions, tasks, debug config, and agent commands.                                    |
| [PyCharm Setup](tools/ide-pycharm.md)        | Python path, run profiles, scope config, and external tools for format/lint.                                         |
| [Debugging](tools/debugging.md)              | Attaching debuggers to Kit: debugpy (VSCode) and PyCharm Professional. The `break` flag trick for tests.             |
| [Profiling](tools/profiling.md)              | Performance profiling with Tracy: app-start and on-demand (`F5`).                                                    |
