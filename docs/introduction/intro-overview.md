![Lightspeed Studio](../data/images/lightspeed.png)

# What is RTX Remix?

RTX Remix is a modding platform that lets you remaster classic DirectX 8 and 9 games with modern graphics. It allows
modders to:

* Enhance textures using AI.
* Replace game assets with high-quality, physically accurate (PBR) models.
* Add RTX ray tracing, DLSS, and Reflex technologies.

Think of it as a tool to give older games a stunning visual upgrade.

## How Does RTX Remix Work?

RTX Remix has two main parts:

1. **RTX Remix Runtime:** This runs alongside the game. It captures game scenes and then, when you play the mod, it
   replaces old assets with remastered ones in real-time and relights the game using path tracing.
2. **RTX Remix Toolkit:** This offline editor empowers users to design mods. It facilitates setting up asset
   replacements, modifying and adding lights, and leveraging AI tools to enhance captured textures.

### The RTX Remix Runtime Explained

The Runtime has two components:

* **Remix Bridge:** This acts as a translator between the game and another program called `NvRemixBridge.exe`. The
  bridge allows the original game (often 32-bit) to run in 64-bit, enabling it to use more system memory. This is
  crucial for rendering high-resolution textures and meshes with ray tracing.
* **Renderer:** This is a powerful graphics engine that takes the game's drawing instructions and renders everything
  using real-time path tracing. It also swaps out old game assets with the new ones you've added in your mod, using
  asset hashes to keep track of what needs to be replaced.

### The RTX Remix Toolkit Explained

The Toolkit provides tools to easily create and add new game objects, materials, and lights. It's built on the NVIDIA
Omniverse ecosystem, giving you access to advanced features for making your game look fantastic.

```{note}
Game objects added to the game using RTX Remix will not affect gameplay. They are purely visual enhancements.
```

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) </sub>
