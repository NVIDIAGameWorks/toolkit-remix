# Introduction to Remastering

Now that you've got everything set up, it's time to start remastering your game using Remix. The Remix runtime will automatically inject path tracing into the game, but the main focus of your Remix mod will be on replacing assets and textures. By using higher-poly models and PBR (Physically-Based Rendering) textures, you can significantly enhance the game's visual quality, surpassing what you could achieve with in-engine edits alone.

> 📝 Please to our [Installation Guide](../remix-installation.md) for both the **RTX Remix Runtime** and the **RTX Remix Toolkit**.

> 📝 Please to our [Requirements Guide](../remix-overview.md) for both the **RTX Remix Runtime** and the **RTX Remix Toolkit**.

# Understanding CONF Files

Before we dive into replacing assets, let's take a moment to get familiar with the settings in the **Alt+X** menu, specifically in the "game setup" tab. Here, you'll find functions that allow you to change how certain textures in the game are rendered. Keep in mind that these options can vary depending on the game you're working on, but the tooltips should provide some initial guidance.

For instance, marking a texture as a "sky texture" will automatically make it emissive and ensure it's always visible to the player, even if it's in a separate space like the skybox (this is particularly important in Source Engine games). It's also a good idea to mark UI textures to make sure they aren't affected by the new rendering pipeline. If you want more detailed information on how these settings work, you can refer to the dedicated **RTX.conf** breakdown.

## ModDB Conf Files
<!--- need content here --->


# Introduction to Captures

RTX Remix is capable of creating asset-exact copies of in-game scenes in the Universal Scene Description (USD) format through a process referred to as “capturing”. Captured scenes (“captures”) can be opened and edited in both NVIDIA Omniverse-based applications, as well as most popular public Digital Content Creation (DCC) tools that support the USD file format.   Because the scene is captured into a USD file, all assets will likewise be available in a single common format. Captured assets include: materials, textures, meshes, and skeletal data for skinned assets, in addition to scene-specific instances and lighting.  Meshes and materials are converted into USD format, whereas textures are converted to DDS. These copies are then stored adjacent to the captures in similarly named folders.

# Folder Structure

RTX Remix automatically organizes the captures you take within a simple folder structure.  The name of your project folder should NOT have any spaces.

```text
rtx-remix
└ captures -> Contains captures taken within the runtime
│ └ capture_(year)_(month)_(day)_(hour)_(minutes)_(seconds).usd
│ └ gameicon.exe_icon
│ ├ lights
│ ├ materials
│ ├ meshes
│ ├ textures
│ ├ thumbs
└ mods ← Automatically created after creating a project
=================================================================
Projects ← Can be located anywhere -> Contains a list of Remix projects

└ YOUR_PROJECT ← Automatically created after creating a project -> contains the files for your project
│ ├ models ← (SUGGESTION) Manually Made -> Contains the ingested models
│ ├ materials ← (SUGGESTION) Manually Made -> Contains the ingested materials
│ ├ deps ← (Automatically created symlink to `rtx-remix` directory to make sure you have referenced files available)
```
**Create a Desktop Shortcut**

Make a shortcut for the "rtx-remix" folder on your desktop.
Rename the shortcut to your project's name.

**Organize Project Files**

Create a project folder to keep your files organized.
This project folder should be outside the game install folder.
For example, if the game is in "C:/Program Files (x86)/Steam/common/Portal," don't place the project there.
Use a valid path like "C:/Users/user/Remix Projects" or "D:/Remix Projects."

**Drive Formatting**

Ensure that both your project drive and game install drive are formatted using NTFS (exFat doesn't support symlinks, which are crucial for us).

**Source and Ingested Assets**

Have separate directories for source and output assets.
Source directory: Store pre-ingestion assets & textures (FBX, USD, OBJ, etc.).
Output directory: Keep ingested assets (USD) here.

> Important: The output directory must be inside your project for correct references.

**Linking Assets**

If you want to output assets to a central depot, use symlinks.
Example command: mklink /J "YOUR_PROJECT_DIR/assets" "INGESTED_ASSET_DIR"
During mod packaging, this ensures all assets are resolved correctly, creating a zippable folder.

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) <sub>