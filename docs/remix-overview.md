![Lightspeed Studio](data/images/lightspeed.png "Lightspeed Studios")


# [Introduction](#introduction)

RTX Remix is a modding platform for remastering a catalog of fixed-function DirectX 8 and 9 games with cutting edge graphics. With NVIDIA RTX Remix, experienced modders can upgrade textures with AI, easily replace game assets with high fidelity assets built with physically accurate (PBR) materials, and inject RTX ray tracing, DLSS and Reflex technologies into the game. It's like giving your old games a makeover with gorgeous modern-looking graphical mods.

Remix consists of two components; there’s the RTX Remix Application (also known as the Toolkit), which is used for creating lights, revamping textures with AI, and adding remastered assets into a game scene that you’ve made with your favorite DCC tool. The second component is the RTX Remix Runtime, which helps you capture classic game scenes to bring into the RTX Remix application to begin your mod. The runtime also is responsible for making your mod “work” when a gamer is playing your mod–in real time, it replaces any old asset with the remastered assets you’ve added to the game scene, and relights the game with path tracing at playback. With the release of the RTX Remix application in Open Beta, the full power of RTX Remix is now in the hands of modders to make next level RTX mods.


## [How Does It Work](#how-does-it-work)

You don't need to be a computer expert to use RTX Remix. It does most of the hard work for you. But it helps to know a bit about how it works. RTX Remix has two main parts, the runtime which attaches to the game while being played, and the toolkit which is used to edit assets for the game offline (without needing to have the game running).

The runtime has two components, the Remix Bridge and Renderer.  The Bridge is like a middleman. It sits next to the game and listens to what the game wants to do. It then sends this information to another program called NvRemixBridge.exe, which is a special program that allows the original games renderer to operate in  64-bit, allowing the game to use more of the systems memory than is available in 32-bit (which most classic games are) and because of this, we can use raytracing to render high resolution textures and meshes.

The Bridge acts as the messenger - it sends all the game instructions to another part called the RTX Remix Renderer. This Renderer Is a super powerful graphics engine. It takes all the things the game wants to draw, like characters and objects,but does so using a powerful real-time path-tracing engine.

The renderer also knows how to swap out the old game stuff with new and improved things from an RTX Remix Mod that you put in a special folder. It keeps track of what's what using special codes (hash IDs) so it knows what to change in the game as you play.

Finally, using  the RTX Remix Toolkit, you are able to easily make and add new game objects, materials, and lights. And since it's built on the NVIDIA Omniverse ecosystem, you'll have lots of cool tools to make your game look even better.


<!----- ON HOLD - Need to figure out how to handle this section

### [Development Roadmap](#development-roadmap)

[https://github.com/NVIDIAGameWorks/rtx-remix/wiki/Roadmap](https://github.com/NVIDIAGameWorks/rtx-remix/wiki/Roadmap)

 ----->

# Requirements

## Technical Requirements

RTX Remix and its mods are built to run on RTX-powered machines. For ideal performance, we recommend using GeForce RTX™ 4070 or higher. For latest drivers, visit  [NVIDIA Driver Downloads](https://www.nvidia.com/Download/index.aspx)s. For Quadro, select 'Quadro New Feature Driver (QNF).


| Level                | Operating System  | CPU                   | CPU Cores | RAM     | GPU                | VRAM  | Disk           |
| :------------------: | :---------------: | :-------------------: | :-------: | :-----: | :----------------: | :---: | :------------: |
| Min              |   Windows 10/11   | Intel I7 or AMD Ryzen | 4         | 16 GB   | GeForce RTX 3060Ti | 8 GB  | 512 GB SSD     |
| Rec          |   Windows 10/11   | Intel I7 or AMD Ryzen | 8         | 32 GB   | GeForce RTX 4070   | 12 GB | 512 GB M.2 SSD |

We recommend that you review the [Omniverse Technical Requirement Documentation](https://docs.omniverse.nvidia.com/materials-and-rendering/latest/common/technical-requirements.html) for further details on what is required to use Applications within the Omniverse Platform.

## Requirements For Modders

* Windows 10 or 11
* [NVIDIA Omniverse](https://www.nvidia.com/en-us/omniverse/download/)

## RTX Remix Runtime Requirements for Developers

* Windows 10 or 11
* [Visual Studio](https://visualstudio.microsoft.com/vs/older-downloads/) _VS 2019 or newer_
* [Windows SDK and emulator](https://developer.microsoft.com/en-us/windows/downloads/sdk-archive/) _10.0.19041.0 or newer_
*  [Meson](https://mesonbuild.com/) _V0.61.4 or newer_
    * Please Note that v1.2.0 does not work (missing library)
    * Follow these [instructions](https://mesonbuild.com/SimpleStart.html#installing-meson) on how to install and reboot the PC before
* [Vulkan SDK](https://vulkan.lunarg.com/sdk/home#windows) _1.3.211.0 or newer_
    * Please Note that you may need to uninstall previous SDK if you have an old version
* [Python](https://www.python.org/downloads/) _version 3.9 or newer_


# Compatibility

The RTX Remix Runtime is primarily targeting DirectX 8 and 9 games with a fixed function pipeline for compatibility. Injecting the Remix runtime into other content is unlikely to work. It is important to state that even amongst DX8/9 games with fixed function pipelines, there is diversity in how they utilize certain shader techniques or handle rendering. As a result, there are crashes and unexpected rendering scenarios that require improvements to the RTX Remix Runtime for content to work perfectly.

It is our goal to work in parallel with the community to identify these errors and improve the runtime to widen compatibility with as many DX8 and 9 fixed function games as possible.  As Remix development continues, we will be adding revisions to the RTX Remix Runtime that will expand compatibility for more and more titles.  Some of those solutions will be code contributions submitted by our talented [developer community](http://discord.gg/rtxremix), which we will receive on our [GitHub as pull requests](https://github.com/NVIDIAGameWorks/rtx-remix/pulls) and integrate into the main RTX Remix Runtime.  RTX Remix is a first of its kind modding platform for reimagining a diverse set of classic games with the same workflow, but it's going to take some investigation and work to achieve that broad compatibility.

## [Defining Compatibility](#defining-compatibility)

Games are 'compatible' if the majority of their draw calls can be intercepted by Remix. That doesn't mean there won't currently be crashes or other bugs that prevent a specific game from launching. If the game crashes, but the content is compatible, then fixing the crash means the game can be remastered. If the game's content isn't compatible, then fixing the crash won't really achieve anything.

This also doesn't mean that everything in the game will be Remix compatible - often specific effects will either need to be replaced using the existing replacements flow, or will need some kind of custom support added to the runtime.


## [Fixed Function Pipelines](#fixed-function-pipelines)

Remix functions by intercepting the data the game sends to the GPU, recreating the game's scene based on that data, and then path tracing that recreated scene. With a fixed function graphics pipeline, the game is just sending textures and meshes to the GPU, using standardized data formats. It's reasonable (though not easy) to recreate a scene from this standardized data.

Part of why RTX Remix targets DX8 and 9 titles with fixed function pipelines is because  later games utilize shader graphics pipelines, where the game can send the data in any format, and the color of a given surface isn't determined until it is actually drawn on the screen. This makes it very difficult for RTX Remix to recreate the scene - which, amongst other problems, causes the game to be incompatible.

The transition from 100% fixed function to 100% shader was gradual - most early DirectX 9.0 games only used shaders for particularly tricky cases, while later DirectX 9.0 games (like most made with 9.0c) may not use the fixed function pipeline at all. Applying Remix to a game using a mix of techniques will likely result in the fixed function objects showing up, and the shader dependent objects either looking wrong, or not showing up at all.

We have some experimental code to handle very simple vertex shaders, which will enable some objects which would otherwise fail. Currently, though, this is very limited. See the ‘Vertex Shader Capture’ option in ‘Game Setup -> Parameters’.


## [DirectX Versions](#directx-versions)

Remix functions as a DirectX 9 replacer, and by itself cannot interact with OpenGL or DirectX 7, 8, etc.

However, there exists various wrapper libraries which can translate from early OpenGL or DirectX 8 to fixed function DirectX 9. While multiple translation layers introduce even more opportunities for bugs, these have been effectively used to get Remix working with several games that are not DirectX 9.

We are not currently aware of any wrapper libraries for DirectX 7 to fixed function DirectX 9, but in theory such a wrapper is reasonable to create.

## ModDB Compatibility Table
ModDB’s community has banded together to make modding with RTX Remix even easier. You can visit the [ModDB website](https://www.moddb.com/rtx/) and see a community maintained compatibility table, which indicates every game the mod community has found currently works with RTX Remix. It also specifies the last RTX Remix runtime that was tested with any given game, and provides config files (called “rtx.conf” files) that make any compatible game work with RTX Remix out of the box. Take a look, and be sure to contribute and update the table if you make any discoveries of your own.

## [Rules of Thumb](#rules-of-thumb)

The following quick checks can help you quickly narrow down on how likely a game is to be compatible, even before you try to run RTX Remix.

### [Publish Date](#publish-date)

The best “at a glance” way to guess if a game is compatible is to look at the publish date. Games released between 2000 and 2005 are most likely to work. Games after 2010 are almost certainly not going to work (unless they are modified to support fixed function pipelines).

### [Graphics API version](#graphics-api-version)

DirectX 8 and DirectX 9.0 will probably be fixed function, and thus feasible. DirectX 9.0c games are usually mostly shader based, so probably won't work.

### [Supported GPU](#supported-gpu)

The Nvidia Geforce 2 graphics card was the last card to be fixed function only, so if the game could run on that card, it's probably fixed function. Note that many games supported fixed functions when they were released, but removed that support in later updates. Testing the content It's actually possible to tell dxvk to dump out any shaders used by the game by adding these settings to your environment variables:

```text
DXVK_SHADER_DUMP_PATH=/some/path
DXVK_LOG_LEVEL=debug
```
If that dumps out a few shaders, then the content may mostly be Remix compatible. If it dumps out a lot of shaders, then the game probably won't be workable.

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) <sub>