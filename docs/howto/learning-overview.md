# Remaster a Game

Now that you've got everything set up, it's time to start remastering your game using Remix. The Remix runtime will automatically inject path tracing into the game, but the main focus of your Remix mod will be on replacing assets and textures. By using higher-poly models and PBR (Physically-Based Rendering) textures, you can significantly enhance the game's visual quality, surpassing what you could achieve with in-engine edits alone.

```{seealso}
Please refer to our [Installation Guide](../remix-installation.md) for both the **RTX Remix Runtime** and the **RTX Remix Toolkit**.
```

```{seealso}
Please refer to our [Requirements Guide](../remix-overview.md) for both the **RTX Remix Runtime** and the **RTX Remix Toolkit**.
```

## Understanding CONF Files

Before we dive into replacing assets, let's take a moment to get familiar with the settings in the **Alt+X** menu, specifically in the "game setup" tab. Firstly, here you’ll find a list of materials from the original game displayed in a grid view. RTX Remix will populate this list of materials based on what the original game is currently rendering, you may find this list changes over time or with respect to what you’re looking at in game (this is normal). The purpose of this list is to provide a convenient way for users of RTX Remix to categorize the various materials in the original game. It’s with this context that Remix understands how to treat objects in the original game with respect to a modern renderer. For instance, materials marked as UI in the original game don’t need to be raytraced, and by letting Remix know about them, it can use the original games renderer for displaying UI, which is often desirable.

Changes you make from the game setup tab will be recorded in an RTX.conf config file, which will help preserve all of your changes for the next time you boot the game.

### Remix Categories
Remix Categories indicate special instructions to render certain elements. Some important categories are: UI (tells Remix to use original game renderer), Sky (lets Remix create a physically based environment map), Particles (let’s Remix reorient particle billboards with respect to all incoming rays, and also create the “soft particles” effect common in games), and Decals (tells Remix to treat these materials as physically based decals when path tracing). The categories are first and foremost intended for the RTX Runtime to properly render, so some may not be completely accurately displayed in the Remix Toolkit. There are many more categories, please refer to the tooltips in the runtime, or the per setting documentation if ever unclear what a particular category means.

Changes you make from the game setup tab will be recorded in an RTX.conf config file, which will help preserve all of your changes for the next time you boot the game.
To see a full list of settings (including Remix Categories) and their descriptions, please refer to this [document](https://github.com/NVIDIAGameWorks/dxvk-remix/blob/main/RtxOptions.md).

Once you have a capture, you can set a subset of categories in the Toolkit. These categories are set using USD attributes on the prim. There are also instructions on how to set these categories in the Toolkit, and you can find out more on this [page](../toolkitinterface/remix-toolkitinterface-categories.md). Others are set for textures, which you can find in the RTX.conf.

### ModDB Conf Files

Visit the [ModDB website](https://www.moddb.com/rtx/). ModDB is hosting rtx.conf files for any game, that will help them run best with RTX Remix. Simply download the RTX.conf file, and drop it and the RTX Remix runtime alongside the game’s .exe. The community can help keep the best RTX.conf files updated on ModDB so that every modder can have a drag and drop experience with setting up a game for RTX Remix.

## Captures

RTX Remix is capable of creating asset-exact copies of in-game scenes in the Universal Scene Description (USD) format through a process referred to as “capturing”. Captured scenes (“captures”) can be opened and edited in both NVIDIA Omniverse-based applications, as well as most popular public Digital Content Creation (DCC) tools that support the USD file format.   Because the scene is captured into a USD file, all assets will likewise be available in a single common format. Captured assets include: materials, textures, meshes, and skeletal data for skinned assets, in addition to scene-specific instances and lighting.  Meshes and materials are converted into USD format, whereas textures are converted to DDS. These copies are then stored adjacent to the captures in similarly named folders.

[ModDB](https://www.moddb.com/rtx) also hosts captures to make it easier to start your remaster.

## Folder Structure

RTX Remix automatically organizes the captures you take within a simple folder structure.

```text
rtx-remix
├ captures -> Contains captures taken within the runtime
│ ├ capture_(year)_(month)_(day)_(hour)_(minutes)_(seconds).usd
│ ├ gameicon.exe_icon
│ ├ lights
│ ├ materials
│ ├ meshes
│ ├ textures
│ └ thumbs
└ mods ← Automatically created after creating a project
  └ YOUR_PROJECT ← (Automatically created symlink to `YOUR_PROJECT` directory to make sure the project can be live updated in-game)

=================================================================

Projects ← (SUGGESTION) Can be located anywhere, contains a list of Remix projects
└ YOUR_PROJECT ← Created during the project creation process, contains the files for your project
  ├ assets ← (SUGGESTION) Manually Made
  | └ ingested ← (SUGGESTION) Manually Made -> Also the default value set in the ingestion wizard.
  |   ├ models ← (SUGGESTION) Manually Made -> Contains the ingested models
  |   └ materials ← (SUGGESTION) Manually Made -> Contains the ingested materials
  └ deps ← (Automatically created symlink to `rtx-remix` directory to make sure you have referenced files available)
```
**Project Naming Restrictions**

Ensure that each mod for a specific game has a distinct project directory name, which should be enforced by the wizard.
If there's already a mod with the same parent directory name when creating a project, the project creation will fail.

**Project Files Organization**

We suggest you create a project folder to keep your files organized.
This project folder should be outside the game install folder.

For example, if the game is in `C:/Program Files (x86)/Steam/common/Portal` don't place the project there.
Use a valid path like `C:/Users/<USER>/RemixProjects` or `D:/RemixProjects`.

**Drive Formatting**

Ensure that both your project drive and game install drive are formatted using NTFS (exFat doesn't support symlinks, which are crucial for us).

**Source and Ingested Assets**

- It is best to have separate directories for source and ingested assets.
- Source directory:
  - Contains pre-ingestion assets & textures (FBX, USD, OBJ, etc.)
  - Can be external from the project directory
- Output directory
  - Created manually and should be located somewhere within the project directory
    - `(project_root)/assets/ingested/` is a good output directory
  - The external asset copying feature uses `(project_root)/assets/ingested/` as a default output directory
  - Contains ingested assets of type USD or DDS that will be referenced in the project

```{important}
Referenced assets should exist within the project directory for references to work properly!
```

**Linking Assets**

If you want to output assets to a central depot, use symlinks. Example command:
```
mklink /J "YOUR_PROJECT_DIR/assets" "INGESTED_ASSET_DIR"
```

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) </sub>
