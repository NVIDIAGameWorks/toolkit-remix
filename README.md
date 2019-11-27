# Graphene
This is where the Omniverse Kit (reference viewer/editor) is being developed. The automatically-published user guide from this repo can be viewed 
[here](https://carbon.gitlab-master-pages.nvidia.com/Graphene/).

## Prerequisites
#### Hardware
- GPU supporting DirectX Raytracing or Vulkan Raytracing (This includes Pascal cards with 6 GB of RAM or more, Volta or Turing GPUs)

#### Linux/Windows
- Install Ubuntu 16.04/18.04 (linux-x86_64) / Windows 10 version 1809+ (windows-x86_64 and DXR)
- Install NVIDIA driver 435.21+ (Linux) / NVIDIA driver 436.02+ (Windows)
- Install VS Code (recommended) or VS2017 with [SDK 10.17763+](https://go.microsoft.com/fwlink/?LinkID=2023014)
- Install Vulkan SDK 1.1.106.0:
    * Required for debug builds and validation layers only.
    * [Windows] (https://sdk.lunarg.com/sdk/download/1.1.106.0/windows/VulkanSDK-1.1.106.0-Installer.exe)
    * [Linux] (https://sdk.lunarg.com/sdk/download/1.1.106.0/linux/vulkansdk-linux-x86_64-1.1.106.0.tar.gz)
- Install "git".
- Install "git-lfs":
    * Required for fetching data folder used in unit tests only.
    * Reboot your machine after installation.
    * Execute `git lfs install` once to enable LFS features after installation.
        * If you cloned the repo before above steps, you have to fetch the data with `git lfs pull` in the repo.
- [Fork Graphene repository](https://gitlab-master.nvidia.com/carbon/Graphene/forks/new)
- Go to your newly created fork in GitLab, select
    * go to "Settings->Repository->Mirroring repositories"
        * set "Git repository URL" to https://gitlab-master.nvidia.com/carbon/Graphene.git
        * select "Pull" under "Mirror direction".
        * clear out the text under "Password".
        * check the "Overwrite diverged branches" checkbox.
    * go to "Settings->General->Visibility, project features, permissions"
        * ensure "Project Visibility" is set to "Public".
- Clone your fork to a local hard drive, make sure to use a NTFS drive on Windows (Carbonite uses symbolic links)
- Execute `./setup.sh` (Linux) which will install Docker. Logging out and back
  in is required to update your account's group membership to include "docker".

#### Building With a Custom Carbonite SDK

If you will not be making changes to Carbonite you may skip this section and
jump to the Building Graphene section. There was previously a need on Linux to
build Carbonite from source if Graphene was being built from source due to ABI
issues, that is no longer the case.

There was previously a need on Linux to have Carbonite exist as a subdirectory
of Graphene. This is no longer the case; as long as the process below is 
followed, then the build will properly configure Docker to use the appropriate
version of Carbonite.

- Clone the Carbonite SDK from the following repo:
(https://gitlab-master.nvidia.com/carbon/Carbonite)
- Make sure to use git to check out the same commit ID as the one described in the package for the "carb_sdk_plugins" dependency in Graphene/deps/target-deps.packman.xml
- Build the Carbonite SDK using the following instructions:
(https://gitlab-master.nvidia.com/carbon/Carbonite/blob/master/README.md)

Create a file, Graphene/deps/target-deps.packman.xml.user containing the following lines:

```
<project toolsVersion="5.6">
  <dependency name="carb_sdk_plugins" linkPath="../_build/target-deps/carb_sdk_plugins">
    <source path="../../Carbonite" />
  </dependency>
</project>
```

The `path` in the `source` node should point to your local Carbonite checkout root relative to Graphene/deps/
This overrides the "carb_sdk_plugins" dependency in target-deps.packman.xml.

## Building Graphene

- Execute `./build.sh` (Linux) / `build.bat` (Windows)

The build output will be found in the generated
`_build` folder and the make/solution files will be found in the generated `_compiler` directory. Occasionally, when
drastic project level changes are made, you may have to regenerate these files using `--rebuild` option with the build
script.

> NOTE: To build the project minimal configuration is needed. Any version of Windows 10 or Linux with Docker will do. Then
run the setup and build scripts as described here above. That's it. The specific version of Windows, NVIDIA driver,
and Vulkan are all runtime dependencies, not compile/link time dependencies. This allows Graphene to build on stock
virtual machines that require zero configuration. This is a beautiful thing, help us keep it that way.

## Linux Build Environment

The linux-x86_64 build process uses a docker container to create a consistent
build environment across all systems. `setup.sh` is intended to take care of
installing Docker. We use docker-ce upstream from docker.com rather than the
version which comes with your host linux system.  Should you wish to set up
Docker manually, the process goes roughly as follows on Ubuntu systems:

- sudo apt update
- sudo apt install apt-transport-https ca-certificates curl software-properties-common
- curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
- sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
- sudo apt update
- sudo apt install docker-ce
- sudo usermod -aG docker ${USER} # Then log out and back in

> NOTE: Docker on Windows System for Linux is unsupported and likely will not work.

## Running Omniverse Kit

- Go to debug or release folder under _build/xxx-x86_64 (x86_64 platforms only)
- Execute `./omniverse-kit` (Linux) / `omniverse-kit.exe` (Windows)

## Troubleshooting

### Windows
Steps to upgrade windows 10 to 1809+ on an IT-managed machine:
- Download a complete 1809+ ISO from MSDN subscription.
- During installation, skip "Download and install updates" and choose "Not right now".

