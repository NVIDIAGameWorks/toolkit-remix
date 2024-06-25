# NVIDIA RTX Remix Toolkit Contribution Guide

This guide provides instructions for contributing to the RTX Remix Toolkit. It covers essential topics such as the Kit
SDK, Pixar USD, and development workflow.

## Getting Started

The RTX Remix Toolkit utilizes
the [Kit SDK](https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/kit_overview.html). Familiarize
yourself with the Kit SDK, which serves as the foundation for extension development.

Additionally, acquaint yourself with Pixar USD, a robust tool for creating and modifying digital assets. Resources for
learning USD are available on the following websites:

- [Learn USD](https://learnusd.github.io/index.html)
- [VFX UsdSurvivalGuide](https://lucascheller.github.io/VFX-UsdSurvivalGuide/index.html)
- [USDBook by Remedy Entertainment](https://remedy-entertainment.github.io/USDBook/index.html)

## Repository Structure

The RTX Remix Toolkit primarily consists of two repositories within this monorepo:

- **Lightspeed**
- **Flux**

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

# Developer's Guide

## Quick Start

To contribute to the RTX Remix Toolkit:

1. Fork this repository.
2. Create a development branch in your fork.
3. Submit a Pull Request to merge your changes from your fork's branch into this repository.

## Common Flags

When starting the RTX Remix Toolkit using the `lightspeed.app.trex.bat` (or `lightspeed.app.trex_dev.bat`) file, you can
use flags to modify the Toolkit's behavior.

- Disable Sentry for local development (to avoid creating Sentry tickets while working on bugs or features):
    - `--/telemetry/enableSentry=false`
- Turn off Driver-Version check (to prevent Kit from crashing on startup when it finds an unsupported driver version):
    - `--/rtx/verifyDriverVersion/enabled=false`
- Enable the PyCharm Debugger (see the [PYCHARM_GUIDE](./PYCHARM_GUIDE.md) for more details):
    - `--/app/extensions/registryEnabled=1 `
    - `--enable omni.kit.debug.pycharm`
    - `--/exts/omni.kit.debug.pycharm/pycharm_location="C:\Program Files\JetBrains\PyCharm 2023.2"` (Update the file
      path to match your PyCharm Installation)

## Additional Documentation

- **[Using Pycharm IDE + debug](./PYCHARM_GUIDE.md)**: Learn about developing with Pycharm and debugging.
- **[How to profile](./PROFILE_GUIDE.md)**: Introduction to profiling.
- **[Review Checklist](./REVIEW_CHECKLIST.md)**: Guidelines for engineers submitting merge requests.
- **[Automated Testing](./TESTING_GUIDELINES.md)**: Process for writing and deploying tests in lightspeed for kit
  applications.
- **[Omniverse Dev Tips](./OMNIVERSE_TIPS.md)**: Tips and tricks for developing on Omniverse from engineers.
- **[Security](../SECURITY.md)**: Anything related to security.
