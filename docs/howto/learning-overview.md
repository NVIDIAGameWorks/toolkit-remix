# Requirements

* RTX Remix Runtime & Toolkit Applications

> 📝 Refer to our Installation Guide for both the **RTX Remix Runtime** and the **RTX Remix Toolkit**.

## Requirements For Creators

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

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://docs.google.com/forms/d/1vym6SgptS4QJvp6ZKTN8Mu9yfd5yQc76B3KHIl-n4DQ/prefill) <sub>

# Introduction to Remastering

Now that you've got everything set up, it's time to start remastering your game using Remix. The Remix runtime will automatically inject path tracing into the game, but the main focus of your Remix mod will be on replacing assets and textures. By using higher-poly models and PBR (Physically-Based Rendering) textures, you can significantly enhance the game's visual quality, surpassing what you could achieve with in-engine edits alone.

# Understanding CONF Files

Before we dive into replacing assets, let's take a moment to get familiar with the settings in the **Alt+X** menu, specifically in the "game setup" tab. Here, you'll find functions that allow you to change how certain textures in the game are rendered. Keep in mind that these options can vary depending on the game you're working on, but the tooltips should provide some initial guidance.

For instance, marking a texture as a "sky texture" will automatically make it emissive and ensure it's always visible to the player, even if it's in a separate space like the skybox (this is particularly important in Source Engine games). It's also a good idea to mark UI textures to make sure they aren't affected by the new rendering pipeline. If you want more detailed information on how these settings work, you can refer to the dedicated **RTX.conf** breakdown.


# Introduction to Captures

RTX Remix is capable of creating asset-exact copies of in-game scenes in the Universal Scene Description (USD) format through a process referred to as “capturing”. Captured scenes (“captures”) can be opened and edited in both NVIDIA Omniverse-based applications, as well as most popular public Digital Content Creation (DCC) tools that support the USD file format.   Because the scene is captured into a USD file, all assets will likewise be available in a single common format. Captured assets include: materials, textures, meshes, and skeletal data for skinned assets, in addition to scene-specific instances and lighting.  Meshes and materials are converted into USD format, whereas textures are converted to DDS. These copies are then stored adjacent to the captures in similarly named folders.

# Best Practices


## Folder Structure

RTX Remix automatically organizes the captures you take within a simple folder structure.  The name of your project folder should NOT have any spaces.

```text
rtx-remix
└ captures
│ └ capture_(year)_(month)_(day)_(hour)_(minutes)_(seconds).usd
│ └ gameicon.exe_icon
│ ├ lights
│ ├ materials
│ ├ meshes
│ ├ textures
│ ├ thumbs
└ mods ← Manually Made
└ project ← Manually Made
│ ├ models ← Manually Made
│ ├ materials ← Manually Made
│ ├ deps ← (Automatically created symlink to `rtx-remix` directory to make sure you have referenced files available)
```

It might be helpful to create a desktop shortcut to this rtx-remix folder and rename that shortcut to your preferred project name.  You may also want to create a project folder to contain the files you’ll be working on.


## Organizing Your Captures

During a big mod project, you might take lots of captures to capture everything you want to change in the game. To keep things organized, it's a good idea to give these pictures names that make sense, like naming them based on the part of the game they belong to. For example, you can choose to add a "ch1_" in front of the name for captures you took in chapter one.

> ⚠️ If you want to change the name of a capture, it's best to do it before creating a project in RTX Remix. Once a project with the capture is made, trying to change the capture's name will cause the project to fail when loading the capture. You can only rename the capture if it's not being used in any projects. \

## Layers

When you create your mod, a file called mod.usda serves as the main control center for your project. It's like the top-level manager. Now, while you can put all your replacement work in this mod.usda, you can also use multiple USDAs stacked on top of each other to keep things organized.

As your mod grows, that single mod.usda file can become massive, potentially reaching thousands or even tens of thousands of lines. The advantage of using USDAs is that they're in a format that's easy to read (ASCII), so you can edit them outside of Remix. This comes in handy when you need to fix any issues with your assets or when multiple people are collaborating in Remix. So, keeping your USDAs organized is crucial for your own peace of mind in the long run.

Before you dive into making replacements, it's smart to think about the kinds of assets you'll be working with. For example, if you're adding new 3D models and new materials to the game world, it's a good idea to split these replacements into different layers. And if the game you're remastering is extensive, you might even want to organize things on a chapter-by-chapter basis.

Remember, there can be such a thing as too much organization, but breaking down your mod into component layers will make it way easier to keep track of all your changes in the long haul.


## Storing Files (Source + Ingested)

In your Projects folder, where all the in-game files belong, remember that it's connected to the game's rtx-remix mod folder through a special shortcut called a symlink. This symlink acts like a shortcut, but it's also where the folder is supposed to be.

Now, to keep things neat and tidy, both for yourself and for the people who will use your mod, it's a good idea to make extra folders inside this project folder. These new folders should organize assets in a way that matches the layers we talked about earlier.

Here's another important point: for the files to work properly in Remix, they need to go through a process called **Ingest**. It's smart to set up another folder structure next to your main project folders. This new structure will hold your original assets, like .fbx files (3D models) and png textures, organized in a way that matches your main project folders.

Now, keep in mind that these two sets of folders, the ones for your in-game files and the ones for your source assets, will start taking up quite a bit of space on your computer over time. So, it might be a good idea to consider a versioning system, especially if you're working with a team of people. This helps keep everything organized and makes it easier to collaborate.


## Building a Team

Revamping an entire game is a big challenge, so you might think about forming a team to help out. Remix mods focus a lot on art, and even if your mod involves changing how the game works, it's a good idea to set up a structure that allows multiple artists to collaborate efficiently.

You may want to pick one or two people to handle the Remix setup and asset preparation. This helps avoid confusion and keeps everything consistent. Having too many people involved in this part could lead to mistakes and differences in the project files.

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) <sub>