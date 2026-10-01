# Installing the RTX Remix Toolkit

The RTX Remix Toolkit includes everything you need to create your own RTX Remix mods, including a build of the RTX Remix
Runtime. Here's how to install it:

```{tip}
To find the installation directory of the RTX Remix Toolkit, see the
[How can I locate the RTX Remix Toolkit Installation Folder?](../remix-faq.md#how-can-i-locate-the-rtx-remix-toolkit-installation-folder)
section.
```

## Install from the NVIDIA App

1. Go to the [RTX Remix website](https://www.nvidia.com/en-us/geforce/rtx-remix/).
2. Follow the instructions to download and install the [NVIDIA App](https://www.nvidia.com/en-us/software/nvidia-app/).
3. Open the NVIDIA App and install `RTX Remix`.

![Install From THE NVIDIA App](../data/images/remix-install-from-nvapp.png)

## Install from GitHub

For access to the latest, potentially unstable features, you can install the RTX Remix Toolkit from GitHub.

### Download a Prebuilt Development Package

1) Sign in to [GitHub](https://github.com).
2) Open the
   [Download RTX Remix Toolkit Package runs](https://github.com/NVIDIAGameWorks/toolkit-remix/actions/workflows/toolkit-package.yml).
3) Open the newest run with a green check mark whose artifact is named `rtx_remix@...+main...windows-x86_64.release`.
4) Under **Artifacts** on the run's **Summary** page, click the artifact to download it as a ZIP.
5) Extract the ZIP to a short path, such as `C:\rtx_remix`. The default folder name is long and can hit Windows
   path-length limits.
6) Optional: run `install.bat` once from the extracted folder to warm up the apps before the first launch.
7) Run `lightspeed.app.trex.bat` from the extracted folder to start the Toolkit.

### Build from Source

1) Clone [the following repository](https://github.com/NVIDIAGameWorks/toolkit-remix)
2) Follow
   the [Build Instructions](https://github.com/NVIDIAGameWorks/toolkit-remix?tab=readme-ov-file#build-instructions) in
   the README.

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) </sub>
