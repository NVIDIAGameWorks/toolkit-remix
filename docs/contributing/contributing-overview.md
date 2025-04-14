# How to Contribute to RTX Remix

Community contributions are highly valued, regardless of whether you are an artist, technical artist, developer, or
possess other relevant skills.

## Reporting Issues

To report a bug or suggest a new feature, please refer to the instructions provided in
the [How do I give feedback to NVIDIA about my experience with RTX Remix?](../remix-faq.md#how-do-i-give-feedback-to-nvidia-about-my-experience-with-rtx-remix)
section.

## Contributing Code

The primary GitHub repository for RTX Remix
is [NVIDIAGameWorks/rtx-remix](https://github.com/NVIDIAGameWorks/rtx-remix). This repository is structured with
submodules that correspond to the various components of the RTX Remix project:

* **[dxvk-remix](https://github.com/NVIDIAGameWorks/dxvk-remix):** This submodule contains the RTX Remix Renderer,
  responsible for rendering the ray-traced visuals.
* **[bridge-remix](https://github.com/NVIDIAGameWorks/bridge-remix):** This submodule encompasses the RTX Remix
  Interceptor and Converter, which handles the translation of game data for use with the renderer.
* **[toolkit-remix](https://github.com/NVIDIAGameWorks/toolkit-remix):** This submodule houses the RTX Remix Toolkit,
  the user interface and set of tools used for authoring RTX Remix mods.

Each of these submodules includes a `README.md` file that provides instructions on how to build and run the respective
project. These README files are essential starting points for developers looking to contribute code.

Furthermore, the Toolkit repository contains
comprehensive [developer documentation](https://github.com/NVIDIAGameWorks/toolkit-remix/tree/main/docs_dev), which
includes a dedicated
[contribution guide](https://github.com/NVIDIAGameWorks/toolkit-remix/blob/main/docs_dev/CONTRIBUTING.md). This
guide offers detailed information on coding standards, workflow processes, and other best practices to ensure
contributions are integrated smoothly.

## Contributing to Mod Projects

For those interested in collaborating on existing mod projects or sharing their own creations,
the [RTX Remix Showcase Discord Community](https://discord.gg/c7J6gUhXMk) provides a dedicated
channel: [team-project-requests](https://discord.com/channels/1028444667789967381/1219748702487318591). This channel
facilitates communication and coordination among modders. The
[remix-projects](https://discord.com/channels/1028444667789967381/1055020377430048848) channel is also a good source of
information for modders.

***

<sub>Need to leave feedback about the RTX Remix
Documentation? [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+)</sub>
