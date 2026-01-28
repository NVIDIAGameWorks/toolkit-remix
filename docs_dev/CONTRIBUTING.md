# NVIDIA RTX Remix Toolkit Contribution Guide

This guide provides instructions for contributing to the RTX Remix Toolkit. It covers essential topics such as the Kit
SDK, Pixar USD, and development workflow.

## Getting Started

The RTX Remix Toolkit is built upon the
[Omniverse Kit SDK](https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/kit_overview.html). Familiarize
yourself with the Omniverse Kit SDK, which serves as the foundation for extension development. See the following video
for a brief overview on extension development with the Omniverse Kit SDK:

[![Build Your First Omniverse Extension With OpenUSD](https://img.youtube.com/vi/4RkR8YH6AaE/mqdefault.jpg)](https://www.youtube.com/watch?v=4RkR8YH6AaE)

Additionally, acquaint yourself with Pixar USD, a robust tool for creating and modifying digital assets. Resources for
learning USD are available on the following websites:

- [OpenUSD Intro to USD](https://openusd.org/dev/intro.html)
- [VFX UsdSurvivalGuide](https://lucascheller.github.io/VFX-UsdSurvivalGuide/index.html)
- [USDBook by Remedy Entertainment](https://remedy-entertainment.github.io/USDBook/index.html)

## Repository Structure

The RTX Remix Toolkit primarily consists of two repositories within this monorepo:

- **Lightspeed (lightspeed.trex.*)**
- **Flux (omni.flux.*)**

Both repositories are located in the [`extensions` directory](../source/extensions). Extensions can be identified by
their naming conventions.

### Flux Repository

Flux comprises a collection of generic, reusable extensions. These extensions are not specific to the RTX Remix Toolkit
and are designed to be adaptable and reusable across projects.

For example, to display a list of USD prims in the RTX Remix app using a list widget, follow these steps:

1. Create a Flux extension to display a list of items without focusing on USD implementation.
2. Develop a Lightspeed extension that utilizes the Flux extension and adds USD-specific details.

### Lightspeed

Lightspeed extensions are created for implementing features specific to the RTX Remix Toolkit, such as altering the app
layout. Reusable code fragments should be placed in a Flux extension first, then customized in a Lightspeed extension.

## Developer's Guide

## Quick Start

To contribute to the RTX Remix Toolkit:

1. Fork this repository.
2. Create a development branch in your fork.
3. Submit a Pull Request to merge your changes from your fork's branch into this repository.
    - Before your Pull Request can be accepted, an automated bot will prompt you to sign the
    [Contributor License Agreement](https://github.com/NVIDIAGameWorks/toolkit-remix/blob/main/.github/workflows/cla/NVIDIA_CLA_v1.0.1.md),
    via your Pull Request's comment page.

## Pre-commit Hooks (Optional)

Optional git hooks are available using [pre-commit](https://pre-commit.com/):
- **On commit:** Auto-format with ruff
- **On push:** Lint check with ruff (aborts if issues found)

**Install:** `install_hooks.bat` (Windows) or `install_hooks.sh` (Linux/Mac)

**Uninstall:** `uninstall_hooks.bat` (Windows) or `uninstall_hooks.sh` (Linux/Mac)

**Usage:**
- Skip with: `git commit --no-verify` or `git push --no-verify`
- Run manually: `pre-commit run --all-files`

Alternatively, use our convenience scripts directly (without installing pre-commit): `format_code.bat` and `lint_code.bat`

## Common Flags

When starting the RTX Remix Toolkit using the `lightspeed.app.trex.bat` (or `lightspeed.app.trex_dev.bat`) file, you can
use flags to modify the Toolkit's behavior.

- Disable Sentry for local development (to avoid creating Sentry tickets while working on bugs or features):
    - `--/telemetry/enableSentry=false`
- Turn off Driver-Version check (to prevent Kit from crashing on startup when it finds an unsupported driver version):
    - `--/rtx/verifyDriverVersion/enabled=false`
- Enable the PyCharm Debugger (see the [PYCHARM_GUIDE](./PYCHARM_GUIDE.md) for more details):
    - `--/app/extensions/registryEnabled=1`
    - `--enable omni.kit.debug.pycharm`
    - `--/exts/omni.kit.debug.pycharm/pycharm_location="C:\Program Files\JetBrains\PyCharm 2023.2"` (Update the file
      path to match your PyCharm Installation)

## Additional Documentation

- **[Using PyCharm IDE](./PYCHARM_GUIDE.md)**: Learn about developing with PyCharm.
- **[Debugging Guide](./DEBUGGING_GUIDE.md)**: Info on how to attach debuggers to the toolkit.
- **[How to profile](./PROFILE_GUIDE.md)**: Introduction to profiling.
- **[Review Checklist](./REVIEW_CHECKLIST.md)**: Guidelines for engineers submitting merge requests.
- **[Automated Testing](./TESTING_GUIDELINES.md)**: Process for writing and deploying tests.
- **[Omniverse Dev Tips](./OMNIVERSE_TIPS.md)**: Tips and tricks for developing on Omniverse from engineers.
- **[Security](../SECURITY.md)**: Security policies and reporting.
