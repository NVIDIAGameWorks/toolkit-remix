# remix-toolkit

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://github.com/NVIDIAGameWorks/toolkit-remix/graphs/commit-activity)

## Introduction

The RTX Remix Toolkit is a robust modding tool tailored to enhance classic DirectX 8 and 9 games.
Powered by NVIDIA Omniverse, this toolkit equips modders with advanced editing capabilities to elevate game assets.
Seamlessly integrated with the RTX Remix Runtime, it facilitates injecting remastered assets back into gameplay,
ensuring an enriched gaming experience.

With the RTX Remix Toolkit, users can seamlessly swap original game assets with high-fidelity remastered counterparts,
tweak lighting configurations, and leverage Generative AI for texture remastering. Streamlined for user-friendly
operation, this toolkit empowers creators to craft visually captivating game scenes, eliminating the need for extensive
technical know-how.

## Pre-Requirements

- [Git](https://www.git-scm.com/)

## Build Instructions

1. Clone this repository
2. Execute the build script:
   ```
   .\build.bat -r
   ```

### Additional notes

- Utilize the `repo.bat` file to execute additional commands. Run the following command to view available tools:
  ```
  .\repo.bat -h
  ```

## Getting Started

1. To launch the end-user version of the toolkit, execute the following file:
   ```
   .\_build\windows-x86_64\release\lightspeed.app.trex.bat
   ```
2. For the developer version of the toolkit with extra features conducive to development, launch:
   ```
   .\_build\windows-x86_64\release\lightspeed.app.trex_dev.bat
   ```
3. For launching specific sub-applications (e.g., Modding, Ingestion), directly run the corresponding files:
   ```
   _build\windows-x86_64\release\lightspeed.app.trex.ingestcraft.bat
   ```

## Contributing

Before contributing to the RTX Remix project, please review the [contributor documentation](./docs_dev/CONTRIBUTING.md).

For further queries, feel free to [create a GitHub issue](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new/choose)
or join the RTX Remix Showcase Discord server via [this link](https://discord.gg/rtxremix), where fellow modders can assist you.

## Additional Documentation

- [RTX Remix Documentation](https://docs.omniverse.nvidia.com/kit/docs/rtx_remix/latest/)
- [RTX Remix Toolkit Documentation](https://docs.omniverse.nvidia.com/kit/docs/rtx_remix/latest/docs/toolkitinterface/remix-toolkitinterface-launchscreen.html)
- [RTX Remix Toolkit API](https://docs.omniverse.nvidia.com/kit/docs/rtx_remix/latest/docs/contributing/api.html)


## Security
- [Security](./SECURITY.md)
