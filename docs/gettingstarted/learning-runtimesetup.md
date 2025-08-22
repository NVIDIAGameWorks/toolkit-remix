# Setting Up the RTX Remix Runtime with your Game

```{warning}
**Make sure the RTX Remix Runtime is installed before you start setting up your game.**

You can follow the [RTX Remix Runtime Installation](../installation/install-runtime.md) section
for directions on how to install the RTX Remix Runtime.
```

If you're using RTX Remix with a game for the first time, you might need to do some initial setup so the game's menus
and visuals display correctly. Use the RTX Remix developer menu for this.

```{note}
Per game setup may be different depending on the game you are trying to remaster.

Join the [RTX Remix Showcase Discord Community](https://discord.gg/c7J6gUhXMk)
where you can check out the [remix-projects](https://discord.com/channels/1028444667789967381/1055020377430048848)
channel for help with the game you wish to remaster!
```

***

## Understanding CONF Files

Let's take a moment to get familiar with the settings in the **Alt+X** menu, specifically in the "game setup" tab.
Firstly, here you’ll find a list of materials from the original game displayed in
a grid view. RTX Remix will populate this list of materials based on what the original game is currently rendering. You
might see this list change depending on what's being displayed in the game (this is normal).
The purpose of this list is to provide an easy way for RTX Remix users to categorize the different materials in
the original game (see the [Understanding Render Categories](#understanding-render-categories) section).
This helps Remix understand how to handle objects from the original game with a modern
renderer.

For example, materials marked as UI in the original game don’t need to be raytraced. By letting Remix know about
them, it can use the original game's rendering for UI, which is often the desired outcome.

Changes you make in the game setup tab are saved in an `RTX.conf` config file. This helps keep all
your changes for the next time you start the game.

### ModDB CONF Files

[ModDB](https://www.moddb.com/rtx/) hosts `RTX.conf` files for many games, which can help them run best with RTX Remix.
You can simply download the `RTX.conf` file and place it along with the RTX Remix runtime next to the game’s executable.
The community can help keep these `RTX.conf` files updated on ModDB, so modders can easily set up a game for RTX Remix.

## Understanding Render Categories

Render Categories give special instructions on how to render certain elements. Some important categories include:

* UI (tells Remix to use the original game's rendering)
* Sky (allows Remix to create a realistic environment map)
* Particles (lets Remix correctly orient particle effects based on lighting and create a "soft
  particles" effect)
* Decals (tells Remix to treat these materials as realistic decals when using path tracing).
* etc.

These categories primarily help the RTX Runtime render correctly, so some might not be perfectly
displayed in the Remix Toolkit.
There are many more categories. Please check the tooltips in the runtime or the specific setting documentation if
you're unsure what a category means.

Changes you make in the game setup tab are saved in the `RTX.conf` config file. This helps keep all
your changes for the next time you start the game. For a full list of settings (including Render Categories) and their
descriptions, please refer to
[this document](https://github.com/NVIDIAGameWorks/dxvk-remix/blob/main/RtxOptions.md).

```{note}
You can also set Render Categories for meshes and materials in the RTX Remix Toolkit. For more information on
this, please refer to the [Render Categories](../toolkitinterface/remix-toolkitinterface-categories.md) section of the
Toolkit Interface documentation.
```

***

## Setting Up UI Textures

Now that you understand the CONF files, let’s start setting up the game. The first thing to do is set up the UI.

1. Press `Alt+X` to open the User Graphics Settings Menu, then select Developer Settings Menu.
   ```{tip}
   You can check the `Always Developer Menu` option in the `Developer Settings` menu to always open the developer menu
   instead of the `Graphics Settings Menu`. This can be useful when setting up a game and needing frequent menu access.
   ```
2. In Developer Settings, go to the `Game Setup` tab, then `Step 1 – UI Textures`.
3. Click on any textures that are part of the game's user interface (UI). This tells RTX Remix to treat them as UI
   elements, not in-game objects.
4. After tagging the UI textures, the game's main menu and world should display correctly.
5. Click `Save Settings` to save your UI texture settings in a file called `rtx.conf`. This file is created next to your
   game's executable, so you won't need to do this again.
6. You can always go back to the UI tagging menu if you find more UI textures later.

## Capturing the Scene

RTX Remix can create exact copies of in-game scenes as USD files through a process called “capturing”. These “captures”
can be opened and edited in NVIDIA Omniverse and other popular DCC tools that support USD. Because the scene is captured
into a USD file, all assets will be in a single common format. Captured assets include materials, textures, meshes, and
skeletal data, as well as scene-specific instances and lighting. Meshes and materials are converted to USD format, and
textures are converted to DDS. These copies are saved next to the captures in similarly named folders.

1. Go to the `Enhancements` tab in the RTX Remix Developer Menu.
2. Make sure `Enable Enhanced Assets` (in the `Enhancements` sub-menu) is turned off.
3. Click the `Capture Scene` button to start capturing.
   ```{tip}
   You can name your capture in the `Name` field to easily find it later.

   Setting the captured file extension to `USDA` instead of `USD` will capture the scene as readable text files, which
   can be helpful for debugging.
   ```
4. This will create your first game capture. You can use this to improve assets, materials, and lighting. Capture files
   are saved in the `rtx-remix/captures` folder, next to your game's executable. The `rtx_remix` folder also contains
   RTX Remix mods (in the `mods` subfolder).

```{note}
[ModDB](https://www.moddb.com/rtx) also has captures available to help you start your remaster.
```

***

## Next Steps

Now that you've got everything set up, it's time to start remastering your game using the RTX Remix Toolkit.
The main focus of the modding process will be to replace assets and textures. By using higher-poly models and PBR
(Physically-Based Rendering) textures, you can significantly enhance the game's visual quality, surpassing what you
could achieve with in-engine edits alone.

Go to the
[Setting Up a Project with the RTX Remix Toolkit](./learning-toolkitsetup.md#setting-up-a-project-with-the-rtx-remix-toolkit)
section to learn how to set up your first RTX Remix Toolkit project.

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) </sub>
