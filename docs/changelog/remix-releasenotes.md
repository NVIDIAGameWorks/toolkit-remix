# Release Notes

## RTX Remix Release 1.0 Notes (3/13/2025)

We are excited to announce the official 1.0 release of RTX Remix.

Note: From now on the Toolkit version will follow the runtime version (1.0.0) and they will continue to be released
together.

RTX Remix comes out packed with new state of the art graphical features to empower you to build more beautiful worlds
and characters in your mods. And the runtime has been upgraded with new neural rendering with DLSS 4 and Neural Radiance
Cache to improve the experience playing Remix mods. DLSS 4 Transformer model ensures everything you create will retain
more detail, allowing your artistic vision to translate more perfectly to the screen. With Multi-Frame Generation, path
traced mods soar up to 8X performance over native. And, RTX Remix debuts the world’s first neural shader, Neural
Radiance Cache–an AI approach to estimating indirect light more accurately and performantly, that trains on your live
game session as you play.

Let’s get into the details:

### Improved RTX Remix Rendering

**DLSS 4 Multi-Frame Generation:**
DLSS 4 allows you to generate up to 3 frames per rendered frame, supercharging performance. In Half-Life 2 RTX, DLSS 4
MFG helps increase framerates by 10X over native at 4K, ensuring the game looks smooth no matter what bells and whistles
you turn on.

**DLSS 4 Ray Reconstruction Transformer Model:**
Ray Reconstruction has a new Transformer model that is much more accurate at accurately denoising ray-traced images,
ensuring the highest degree of detail is retained. With the new Transformer model, even lower DLSS presets can look as
good as higher presets with the old “CNN model” (Convolutional Neural Network). The image will be more temporally stable
and overall much more enjoyable.

Please note, the Transformer model is a slightly heavier network than the CNN model. As a result, we’ve opted to
automatically default to the CNN model at the “Low” and “Medium” presets to ensure people who are looking to claw back
any performance on the table can secure it.

**Neural Radiance Cache:**
NRC is a neural shader that estimates more accurate indirect light more performantly. While you play, a grid of tiny
neural networks in world space train live on your game session, tailoring their approach to the content you are seeing
in real time. The Remix pathtracer traces an extra, smaller set of long training ray paths that record radiance observed
at each bounce to train the NRC with. Regular per-pixel ray paths then terminate earlier, generally at 2-3 bounces, at
which point an indirect radiance from a multitude of additional bounces is inferred by AI. Because fewer bounces are
calculated for the vast majority of ray paths (and are instead inferred), NRC improves performance in Half-Life 2 RTX by
15%.

It offers three graphical settings with tradeoffs between performance and indirect lighting accuracy: Medium, High, and
Ultra.

**Performance & Memory Optimizations:**
The RTX Remix runtime has seen a number of optimizations to performance in both CPU bounded and GPU bounded scenarios.
The extent of this uplift may vary depending on the specific RTX Remix mod. Take a look at how performance is improved
in Portal With RTX on a 5070TI:

1. Portal With RTX (Beta Runtime): 111 FPS
2. Portal With RTX (Release Runtime): 132 FPS
3. Portal With RTX (Release Runtime with NRC On): 155 FPS
4. Portal With RTX (Release Runtime with NRC + DLSS): 260 FPS

Performance and memory optimizations come on the back of a multitude of changes:
Optimized memory and performance of BVH builds by utilizing instancing
Limited max bones per vertex for skinned meshes
Improved OMM budgeting to work better in scenarios using most of VRAM
Added runtime normal compression for replacement assets to reduce memory usage
Removed unnecessary resource allocations based on active graphics features
Disabled rendering passes that are not needed for active graphics features
Improved reuse of compatible resources' memory across different rendering passes
Reduced memory usage of ray tracing acceleration structures on lower memory GPUs
Tweaked RTXDI quality settings for more performance when Ray Reconstruction is enabled
Switched from host visible to device local allocations for mesh replacement buffers
Optimized CPU cost of CreateSurfaceMaterial by caching and reusing RtSurfaceMaterial within the same frame
Reused instance matching and projection decomposition to lower per instance CPU cost

**New Texture Streaming:**
Optimizes VRAM usage to maximize texture quality within the available video memory budget. Players will notice assets
streaming in faster, in higher quality more often, and will see “spilling” less frequently. Note: this will not
necessarily decrease total VRAM usage, as RTX Remix always tries to use available VRAM efficiently to ensure highest
quality textures are being seen.

**Changes to Shader Compilation**
Remix will now only prewarm shaders that are actually being used, improving shader compilation time at first launch.
Note that this may lead to shader compile stalls when changing Remix options that require different shader permutations.
Added asynchronous shader compilation functionality and a progress UI when the game is compiling shaders during play

### Upgraded Mod Authorship Tools

#### New Features

**Enhanced Character Creation:** In games that support GPU skinning, you will now be able to replace characters in the
same fidelity you have been replacing assets and world materials. Import a rigged character replacement into RTX Remix,
and from the Toolkit, remap its bones and joints to help it conform more closely to the skeleton RTX Remix captured (and
therefore expects to render). Once this is done, the character will animate as expected.

A new tool has been added to help with replacing animated assets using GPU Skinning.

```{seealso}
More information about the skeleton remapping tool is available [here](../howto/learning-assets.md#remapping-skeleton-tool).
```

**Controls for RTX Skin:**
RTX Skin represents one of the first implementations of sub-surface scattering in ray-traced gaming. Light can now
propagate and transmit through skin, grounding characters in a new realism. RTX Skin can also be used to make dazzling
world materials, like jade, which can sparkle and take on complex colors when illuminated.

Use the RTX Remix Toolkit to add SSS maps to any asset to tune the per pixel transmission level. And in the RTX Runtime,
you can adjust the SSS scale to influence the global multiplier for all assets marked with SSS to increase the intensity
of the effect.

```{seealso}
More information about subsurface scattering is available [here](../howto/learning-materials.md#subsurface-scattering).
```

**RTX Volumetrics:**
We’ve overhauled our volumetric system by leveraging a volume-based ReSTIR algorithm (Reservoir-based Spatiotemporal
Importance Resampling). Light beams now look more defined, with higher contrast volumetric lighting and shadows. Shafts
of light will look sharper, helping to create those epic moments in gameplay we love.

Within the RTX Remix menu you can adjust parameters to customize the volumetric atmosphere of your mod. We provide
presets so you can visualize your game scene with fog, smoke, haze, and other conditions, and each parameter is tunable.
You can even inject dust particles in the scene, and define their physics and properties.

In the RTX Remix Toolkit, the volumetric radiance scale attribute can make lighting larger than life (literally),
influencing how much light contributes to the volumetric look of your scene. This multiplier enables modifying
volumetric contribution on a per light basis to create more pronounced lighting effects. A 1 value keeps lighting
completely physically based obeying the laws of physics, but you can turn it up or down for a more stylized look.

#### Stage Manager

The most requested feature is here and it’s sure to speed up your modding. From this new control panel, modders can view
a complete list of all tweakable game elements, jumping directly to them with a click. Sort and find prims, lights,
meshes, materials, skeletons, and more, isolate remastered and original assets, and create custom searchable tags for
any prim, making finding and editing assets easier. You can also view prims by Remix category, like particles, decals,
UI, sky.

You can also temporarily hide assets in the Viewport, in the event you are modifying a game scene that is obstructed by
walls or large objects. And multiselection and editing is even easier when all of your assets are groupable in a list.

**Stage Manager Official Release:** The Stage Manager is now integrated as a key component of the RTX Remix Toolkit that
allows selecting and editing of any prim in your mod.

**ON by default:** The Stage Manager is now on by default, but can still be toggled under "Optional Features".

**New Stage Manager Tabs:**
Added Categories, Skeleton, Meshes, Materials, and Custom Tags tabs alongside the existing All Prims and Lights tabs to
Stage Manager.

**Custom Tags:**
Tag any capture or replacement prim with a custom name and make it easy to find again or manage similar objects.

**Contributions Welcome:** Stage Manager functionality can easily be expanded by contributing to our open source
project.

##### Refined Toolkit Experience

The Toolkit has had a thorough polish pass making it much easier to use.

**Updated to kit sdk 106.5:**
The app is now built on a new version of the
omniverse [kit sdk](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/106_5_highlights.html) which
contains many fixes and stability improvements.

**Removed Path Restrictions:**
Removed whitespace project path limitation for flexible project names and locations.

**Performance:**
Improved performance and responsiveness of Stage Manager and other widgets.

**New Homescreen:**
A redesigned home screen with a simplified project creation flow brings a cleaner interface to making new projects.
Added ability to cleanup deleted projects.

**Improved Packaging:**
Added a new tool to help automate resolving resource paths when packaging your mod.

```{seealso}
More information about mod packaging is available [here](../howto/learning-packaging.md).
```

**Property Widget Improvements:**
Continued to fix, improve the look and feel, and simplify code controlling selection panel and property editor widgets.

**Remix Categories:**
This key feature of Remix has been updated in Toolkit and aligned with the Runtime. We've foregrounded tooltips to help
guide Modders in tagging replacement meshes with the appropriate category for the runtime.

```{seealso}
More information about Remix Categories is available
[here](../gettingstarted/learning-runtimesetup.md#understanding-remix-categories).
```

**Ingestion Scale Factor**: Flipped asset ingestion parameter from "Meters per Unit" to "Asset Scale Factor" to make
ingesting assets at the right size more intuitive.

```{seealso}
More information about asset ingestion is available [here](../howto/learning-ingestion.md)
```

**Improved Documentation:** We have added more details and will continue to make updates to this documentation.
Contributions are also welcome as github PRs to
the [remix-toolkit repo](https://github.com/NVIDIAGameWorks/toolkit-remix).

### Bugfixes and Minor Changes

#### RTX Remix Runtime:

- Improved Ray Reconstruction responsiveness with animated textures.
- Updated NRD to 4.13 for better performance, sharper and more stable denoising
- AnimatedWaterTexture now works for translucent materials
- Fixed flickering in reflection & refraction rays that hit the sky
- Fixed incorrectly hidden meshes after hide / show is used in RTX Remix
- Added support for rays starting underwater or inside other translucent materials based on the game's fog state
- Fixed bugs with terrain and displace_out interactions
- Improved free camera keyboard turning controls
- Added max light intensity for light conversion
- Corrected an issue with the Bridge where inputs would sometimes not be forwarded.
- Added support for AddDirtyBox(), AddDirtyRect() and SetSoftwareVertexProcessing() API call forwarding.
- Corrected an issue where certain bridge messaging systems ignored that timeouts were disabled, which could cause
  timeout related crashes if the default value was too low for the host application.
- Corrected an issue where the bridge server or client could hang indefinitely when timeouts are disabled.

#### RTX Remix Toolkit:

- Fixed capture window behavior to avoid it hanging on other tabs
- Fixed disclosure icon display so tree view and panels mean the same thing
- Fixed display of Remix Categories icon for only when applicable mesh objects are selected
- Fixed various Stage Manager issues
- Fixed layers panel performance in large projects
- Fixed light selection behavior in selection panel
- Fixed layer panel inconsistent muteness state
- Fixed layer panel not refreshing after unloading stage + more fixes
- Fixed ingestion bug for drag and drop
- Fixed Tooltips on properties from USD schema which include a documentation string from the schema.

```{seealso}
Changelogs

- For runtime release notes, please click [here](https://github.com/NVIDIAGameWorks/rtx-remix/releases/tag/remix-1.0.0)
- For a full toolkit changelog, please click [here](remix-full-changelog.md)
```

***

## RTX Remix Release 0.6 Notes (12/3/2024)

The latest release of the RTX Remix Toolkit and Runtime brings powerful new features and enhancements designed to take
your modding experience to the next level. Here’s some of what the release has in store:

- **Introducing Experimental Features:** Dive into cutting-edge tools early with the new “Experimental Features” menu.
  This allows you to test in-progress features and provide valuable feedback to shape their development.

- **Stage Manager (Experimental):** the first experimental feature, Stage Manager, is a helpful UI that allows you to
  visualize every prim in your scene from an interactive list. For the first time, modders can easily access and edit
  prims that aren’t selectable within the viewport, and streamline their workflows. Share your feedback and ideas on
  our [GitHub](https://github.com/NVIDIAGameWorks/toolkit-remix/) to help us refine Stage Manager and other experimental
  features.

- **RTX Remix in the NVIDIA App:** RTX Remix is now available in the
  new [NVIDIA App Launcher](https://www.nvidia.com/en-us/software/nvidia-app/), offering faster startup times, reduced
  CPU overhead, and a seamless modding experience. We highly recommend all users download and mod through the NVIDIA App
  to take full advantage of these performance improvements.

Keep reading to see our detailed breakdown.

### RTX Remix Runtime Release 0.6

#### Features

**Big News for Gamers and Modders!**
32-Bit Games Now Supported by the RTX Remix Runtime SDK!
Elevate your favorite classic games with cutting-edge RTX technology.

**Huge Performance Upgrades**
The RTX Remix Runtime 0.6 delivers a major leap forward in performance, offering large performance improvements in GPU
and CPU-bound scenes. Whether you're working on graphically demanding environments or intricate, processor-heavy setups,
this update ensures a smoother and faster modding experience.

**Enhanced Compatibility with Render Targets**
Introducing support for Render Targets, a technique used in classic games like Half-Life 2 to project scenes within
scenes. This addition expands the range of games that can leverage RTX Remix, allowing modders to recreate and enhance
iconic visual effects with greater fidelity.

```{seealso}
Look below for our detailed release notes, and for a full changelog, please click [here](remix-full-changelog.md)
```

```{video} ../data/videos/0.6_Release/render_target.mp4
:alt: RenderTarget
:class: video-player
:autoplay:
:loop:
```

### RTX Remix Toolkit Release 2024.5.1

#### Features

**“Experimental Features” Menu**
Try the latest cutting-edge tools under development with the new "Experimental Features" menu. Access this option from
the top-left hamburger menu and enable features that are still being fine-tuned. While experimental features may have
some bugs, they provide an exciting glimpse into the future of RTX Remix. If you encounter issues or have feedback, help
shape the development by filing an issue on [GitHub](https://github.com/NVIDIAGameWorks/toolkit-remix/).

```{video} ../data/videos/0.6_Release/experimentalfeatures.mp4
:alt: ExperimentalFeatures
:class: video-player
:autoplay:
:loop:
```

**Assign Texture Sets**
Simplify your asset texturing process with the new "Assign Texture Sets" option. Select one texture from a folder, and
RTX Remix automatically pulls all relevant textures for that asset, saving you time and streamlining your workflow.

```{video} ../data/videos/0.6_Release/assign_texture_sets.mp4
:alt: AssignTextureSets
:class: video-player
:autoplay:
:loop:
```

**Stage Manager (Experimental)**
Revolutionize your project management with the all-new Stage Manager. This powerful tool provides a clear, categorized
view of every prim in your scene—meshes, textures, lights, and more—allowing you to easily isolate, edit, or replace
assets.

```{video} ../data/videos/0.6_Release/stagemanager_filtering.mp4
:alt: StageManagerFiltering
:class: video-player
:autoplay:
:loop:
```

*Note:* Stage Manager is experimental and may experience performance issues with larger projects (10,000+ prims).

- **Advanced Filtering:** Quickly identify and manage unreplaced or replaced assets.
- **Multi-Asset Editing:** Make bulk changes to selected prims directly from the Stage Manager.
- **Viewport Integration:** Center the camera on any asset, hide or unhide assets for efficient modding, and even edit
  elements not selectable in the viewport (like particles).
- **Example Workflow:** Mod a tight, hard-to-navigate space, such as a train cabin, by hiding walls, editing interior
  assets, and unhiding the walls to complete your scene.

In the future, we’ll be looking to add more functionality into the Stage Manager. We hope you enjoy this early
introduction.

**Standalone NVIDIA App Installer/Launcher**
RTX Remix now operates independently via the NVApp Launcher. Enjoy faster startup times, seamless updates, and optimized
CPU utilization for a smoother, more efficient experience.

**End to End REST API Tutorial**
Added a tutorial on how to use the REST API to build a Blender Add-On.

#### Quality of Life Improvements

**Multi-Selection & Multi-Editing**
Make broad changes with ease. Select multiple objects—like lights—and adjust their properties simultaneously, such as
intensity or color. This improvement streamlines your workflow, saving time and effort on repetitive edits.

```{video} ../data/videos/0.6_Release/multiselection_multiediting.mp4
:alt: Multiselection
:class: video-player
:autoplay:
:loop:
```

- REMIX-3600: Clarified Selection widget behavior and fixed issues.
- REMIX-3051: Configured the save prompt to open during stage unloads with unsaved changes.
- REMIX-2907: Added a warning when invalid file types are dropped for ingestion.
- REMIX-3214, REMIX-3215: Added checks for layer type validation during project and mod file imports.
- Improved the look of the scan file window.

#### Bug Fixes

- **Hot-Reload Stability:** Fixed hot-reload functionality by allowing the reuse of validators, improving reliability
  and reducing errors during reloads.
- **Material Tooltips:** Resolved issues with material file path tooltips and copy menus for a smoother user experience.
- **Texture Set Assignment:** Addressed problems with assigning texture sets, ensuring consistent and accurate
  assignments.
- **Lighting Panel:** Fixed icon display issues for lights in the selection panel.
- **Stage Manager Performance:** Resolved significant performance issues with the Stage Manager, enhancing usability,
  especially in larger projects.
- **Shell Script Permissions:** Corrected shell script permission issues for better compatibility.
- **REST API Crashes:** Fixed crashes in the REST API for select_prim_paths_with_data_model and
  append_reference_with_data_model, improving API stability.
- **Stage Manager Cleanup:** Ensured all listeners are cleared when disabling the Stage Manager feature flag to prevent
  residual issues.

#### Features

- REMIX-3052: Added a new "reload last stage" workfile menu item.
- REMIX-2874: Added a scan folder dialog for importing.
- REMIX-3113: Added control over Parallel process count dropdown for ingestion.
- REMIX-2518: Added external asset prevention/copying functionality.

#### Compatibility Improvements

- Added Data Migration documentation.

***

## RTX Remix Release 0.5.1 Notes (5/13/2024)

### RTX Remix Toolkit Release 2024.4.1

**Light Shaping Tools**
Take control of your scene's lighting with the ability to visualize and adjust attributes like intensity, radius, and
direction directly from the viewport. Perfect your lighting with intuitive tools that make your scene shine.

```{video} ../data/videos/0.6_Release/light_shaping_1.mp4
:alt: LightShaping1
:class: video-player
:autoplay:
:loop:
```

```{video} ../data/videos/0.6_Release/light_shaping_2.mp4
:alt: LightShaping2
:class: video-player
:autoplay:
:loop:
```

#### Features

- REMIX-2674: Adding a check for similar textures and auto-populating texture fields.
- REMIX-2779, REMIX-2780, REMIX-2781: Added light manipulators for RectLight, DistantLight, and DiskLight.
- REMIX-2782: Added light manipulator for SphereLight.
- REMIX-2137, REMIX-2138, REMIX-2139, REMIX-2142, REMIX-2842: Added microservices for the "Modding" & "Ingestion"
  sub-apps.
- REMIX-3096: Added a right-click copy menu for selection tree items.
- Added lightweight kit app for HdRemix image testing: lightspeed.hdremix.test-0.0.0.
- C function binding to set RtxOption directly into the Remix Renderer.

#### Quality of Life

- REMIX-2722: Reduced default light intensities.
- REMIX-3112: Changed displace_in slider range and default value to improve usability.
- REMIX-3125: Calculate float slider default step size lazily.
- Fixed documentation URL for release notes.
- Fixed release notes version to match the release version.

#### Compatibility Improvements

- REMIX-2876: Updated to Kit Kernel 106.
- OM-122163: Updated Remix manipulator to adapt omni.kit.manipulator.prim renaming.
- REMIX-2880: Improved CI setup for merged repos.
- REMIX-2880: Split PIP Archives between LSS, Flux & Internal Flux.
- REMIX-2880: Updated to the latest public Kit SDK.

#### Bug Fixes

- REMIX-2872: Made the non-ingested asset message more descriptive.
- REMIX-2789: Fixed ingestion queue scrollbar issues.
- REMIX-2943: Made file extension validation case-insensitive.
- REMIX-2684: Created camera light event.
- Fixed various issues with microservices, added new endpoints, and improved functionality.

### RTX Remix Toolkit Release 2024.4.0-RC.1

#### Changed

- Updated the runtime included with the RTX Remix Toolkit to version 0.5.1

### RTX Remix Runtime 0.5.1

#### Bug Fixes

- Fixed an issue preventing the Remix runtime from starting on AMD hardware with the latest Windows drivers

***

## RTX Remix Release 0.5 Notes (4/30/2024)

With the latest update of RTX Remix, we've enabled modders to add DLSS 3.5 Ray Reconstruction for Remix mods. Look below
for our detailed release notes, and for a full changelog, please click [here](remix-full-changelog.md)

As a reminder, you can update RTX Remix by clicking the menu next to the "Launch" prompt on the RTX Remix Application
page of the Omniverse Launcher.

### RTX Remix Toolkit Release 2024.3.0

#### Features

- Added a new "Teleport" action to teleport any selected object to your mouse cursor or the center of the screen.
  Teleport via the viewport sidebar or the Ctrl + T hotkey.

  ```{video} ../data/videos/teleport.mp4
  :alt: Teleport
  :class: video-player
  :autoplay:
  :loop:
  ```

- Added a new “Waypoint” feature, enabling modders to save camera positions as waypoints and snap the camera to them.
  Waypoint options can be found in the top right corner of the viewport. By default, opening a capture will save the
  camera starting position as a waypoint.

  ```{video} ../data/videos/waypoints.mp4
  :alt: Waypoint
  :class: video-player
  :autoplay:
  :loop:
  ```

- Added DLSS 3.5 Ray Reconstruction to the Viewport

- Material/object property panels can now be pinned for any selected asset, keeping them locked into view even after
  deselecting the object. This enables interesting workflows–for example, selecting a wall and locking its material
  properties panel, selecting a light near the wall and locking its object properties panel, and being able to
  simultaneously adjust the wall and light in relation to one another.

  ```{video} ../data/videos/panel_pinning.mp4
  :alt: Panel Pinning
  :class: video-player
  :autoplay:
  :loop:
  ```

- Added the option to unload the stage to reclaim resources without closing the app. This function is useful if you need
  to free up memory to do certain actions (for example, boot the game while running RTX Remix, or run RTX Remix’s AI
  Texture Tools). This option can be found in the top left menu.

  ```{video} ../data/videos/unload_stage.mp4
  :alt: Unload Stage
  :class: video-player
  :autoplay:
  :loop:
  ```

- Rearchitected AI Texture Tool and Ingestion processes to allow the RTX Remix Toolkit to run efficiently in parallel
  with them. Modders should have a much easier time multitasking while ingesting or AI enhancing assets.

  ```{video} ../data/videos/parallel_processing_no_lag.mp4
  :alt: Parallel Processing No Lag
  :class: video-player
  :autoplay:
  :loop:
  ```

#### Quality of Life Improvements

- ESC key now unselect all objects

- Added sliders for all material and object properties

  ```{video} ../data/videos/realtime_sliders.mp4
  :alt: Realtime Sliders
  :class: video-player
  :autoplay:
  :loop:
  ```

- Closing RTX Remix with unsaved data will now present a save prompt, so that modders do not lose any progress. Also
  streamlined UX for going between open and saved projects.

- Added a refresh button to the capture list, and improved thumbnail pop ins to be less disruptive

- Grouped several material properties that lacked a parent category into their own “Other” category

- Updated default light intensity values for all newly created lights to be much lower. Newer default behavior should
  pair better with more games.

- Project creation now creates symlinks

- Made several improvements to accessibility, text legibility and text clarity

#### Bug Fixes

- Attribute and material properties now properly behave with object selection and deselection

- Fixed issues with material properties pane changing unexpectedly when using undo and redo functions

- Fixed various responsiveness issues with the ColorField/color selector

- Added headers to the capture list to help explain captures and replacement progress

- Fixed crashes with the AI Texture Tools when processing DDS files

### RTX Remix Runtime 0.5.0

Note to modders–with RTX Remix Runtime 0.5 we have removed an option that was causing excessive ghosting with no benefit
to users. If your project requires you to remain on an older RTX Remix Runtime, we advise you to check your rtx.conf
file, and ensure `rtx.enableDeveloperOptions = false`.

#### Features

- Added DLSS 3.5 Ray Reconstruction to RTX Remix, making it possible for modders to improve image quality with this AI
  powered denoiser. With ray reconstruction, path traced lights update faster, reflections and thin light detail are
  more stable, and texture details can pop more. Learn more about ray reconstruction and its benefits for RTX Remix
  modding in our [GeForce article](https://www.nvidia.com/en-us/geforce/news/rtx-remix-dlss-3-5-ray-reconstruction)
- Added the d3d8to9 wrapper to the runtime release. The d3d8to9 wrapper was an essential file modders had to manually
  add to their runtime package in order to unlock proper compatibility in DirectX 8 titles. Now, we include it
  automatically–modders should find highly compatible DirectX 8 games to work better out of the box thanks to this
  change. This change should not impact non-DirectX 8 titles.
- Significantly changed the texture tagging flow, which is essential to properly setting up a game with RTX Remix. We’ve
  added several new options that should streamline how advanced users interact with these menus. These changes are
  likely to undergo further iteration, and we encourage any early feedback on them.

  We've changed how texture tagging works when the “Split Texture Category List” option is toggled on. When “Split
  Texture Category List” is toggled on, opening or hovering over a texture category selects it (indicated by it turning
  orange). Left clicking a texture in the gameworld or the category list will automatically assign it to the currently
  selected texture category. Right clicking a texture in the game world or in the Remix runtime category lists will give
  users the very familiar texture selection drop down menu to choose from all of the available texture tagging options.
  Please note, you must have a texture category selected to tag textures in this mode.

  We’ve also added an option to only view texture categories that contain textures you have already tagged. You can
  select this by toggling the "Only Show Assigned Textures in Category Lists" checkbox. When checked, untagged textures
  will appear in their own “Uncategorized” category

  Thank you to community contributor “xoxor4d” (Github PR #49) for submitting the code for this change. We look forward
  to further improving how game setup and texture tagging works in RTX Remix.

#### Quality of Life Improvements

- Improved stability and performance in shader-based games by enhancing the vertex capture system
- Resolved visual artifacts, like banding, with tonemapper by introducing blue noise driven dithering. To enable this
  feature in the RTX Remix Runtime menu, go to “Post-Processing” > “Tonemapping” and set “Dither Mode” in the dropdown
  to “Spatial + Temporal” (uses a noise pattern that changes over time) or “Spatial” (uses a static noise pattern). The
  config options for these settings are `rtx.localtonemap.ditherMode` and `rtx.tonemap.ditherMode` for the local and
  global tonemappers respectively. These config options can be set to 1 for Spatial dither mode or 2 for Spatial +
  Temporal dither mode (or 0 to disable dithering).
- Added config options to hide the RTX Remix splash banner (`rtx.hideSplashMessage = True/False`) and to display a
  custom welcome message to the user on startup (`rtx.welcomeMessage = “example text”`)
- Added option to pass the original game’s cubemaps to RTX Remix’s backend. This enables cubemap textures to be used for
  tagging. Note that cubemaps will not render correctly, and draw calls that reference only cubemaps are not usable in
  Remix. To enable this feature in the RTX Remix Runtime menu, go to the “Game Setup” tab > “Step 2: Parameter Tuning” >
  “Heuristics” and check off “Allow Cubemaps”. Or, use the config option `rtx.allowCubemaps = True`.
- Added the ability to ignore baked lighting associated with certain textures. This is useful in cases where the game
  bakes out lighting to vertex colors or texture factors (rather than lightmaps). To use this feature, in the RTX Remix
  Runtime menu’s "Game Setup" tab, as part of the texture tagging workflow, there is now a new category called “Ignore
  Baked Lighting Texture”.
- Added the option to configure various RTX Remix systems that rely on a game’s world space coordinate system (ex:
  terrain baking) to assume a left-handed coordinate system.

  When modding a game with a left-handed coordinate system, you may notice that terrain, even after being properly
  tagged in the Game Setup tab, still looks incorrect. Open the RTX Remix Runtime menu, and in the “Game Setup” tab,
  under parameter tuning check off the “Scene Left-Handed Coordinate System” checkbox, and suddenly all of these
  systems, like terrain baking, should begin to work properly. The config option for forcing these rendering systems to
  assume a left handed coordinate system is `rtx.leftHandedCoordinateSystem = True`.

  Thank you to community contributor “jdswebb” (Github PR# 65) for submitting the code for this change.

- Added an option to use AABBs to differentiate instances, and therefore track them better across frames. For gamers,
  that means less ghosting and flickering for animated objects and skinned meshes in motion. To enable this feature,
  open the "Game Setup" tab of the RTX Remix Runtime menu, select "Step 2: Parameter Tuning" > "Heuristics" and toggle
  on "Always Calculate AABB (For Instance Matching).

  Thank you to community contributor “xoxor4d” (Github PR# 67) for submitting the code for this change.

- Improved how RTX Remix mods run for Steam Deck and Linux AMD users, thanks to optimizations for RADV drivers.

  Thank you to community contributor “pixelcluster” (Github PR #63) for submitting the code for this change.

- Improved the consistency of distant lights, making them update properly when changing or reorienting them. This fixes
  bugs in certain scenarios like when a distant light was parented to a mesh that rotates.

  Thank you to community contributor “mmdanggg2” (Github PR #66) for submitting the code for this change, and thank you
  to “Kamilkampfwagen-II” for reporting the issue on GitHub (issue #49).

- Enabled the function logging feature in the RTX Remix Bridge found within the "Debug" build to also be in the "Debug
  Optimized" build.
- Added an option `logServerCommands` to the RTX Remix Bridge to write what commands the server is processing to the
  `NvRemixBridge.log` file. To enable, in the `bridge.conf` file found alongside the NvRemixBridge.exe, set
  `logServerCommands = True` with no leading # mark. If `bridge.conf` does not exist, you can get it
  from https://github.com/NVIDIAGameWorks/bridge-remix/blob/main/bridge.conf
- Added an additional logging mode that includes the messages of logServerCommands, and status information from the RTX
  Remix Bridge client/server messaging systems. This can be helpful for catching potential bridge messaging issues. To
  enable, in the `bridge.conf` file found alongside the `NvRemixBridge.exe`, set `logAllCommands = True` with no
  leading # mark. If `bridge.conf` does not exist, you can get it
  from https://github.com/NVIDIAGameWorks/bridge-remix/blob/main/bridge.conf

#### Compatibility Improvements

- Made several changes to the RTX Remix Bridge that enhance compatibility across a variety of games

- Fixed an issue that would cause certain games to hang. There was a deadlock in the RTX Remix Bridge where the client
  would be blocked waiting for a shared buffer to be read, thinking that the server was behind, while the server was in
  actuality caught up and waiting for a new command. The client was improperly telling the server that it had overflowed
  the shared data buffer because the command sending code was not distinguishing between a pointer with valid data to
  send (which has non-zero size on the buffer) and a null-pointer (which has zero size on the buffer).

- Fixed crashes, graphical errors, and unexpected behavior caused by games running with RTX Remix by stalling the data
  queue in the RTX Remix Bridge when a write would overflow the queue while the overflow flag was already set.

- Improved certain incompatibilities where RTX Remix would close unexpectedly or stop updating the visuals (while audio
  continued to play). To correct an issue where a command processing thread could prematurely terminate if starved of
  commands for the bridge timeout duration, RTX Remix Bridge server timeouts are now disabled. Additionally, we now
  close the RTX Remix Bridge client on unexpected bridge server closure.

#### Bug Fixes

- Fixed issues with texture capture, capture stutter, and capture corruption in certain titles

- Improved reliability of the RTX Remix Bridge build system.
- Sped up how quickly the RTX Remix Bridge informs the host game about invalid calls to `SetTransform()`. The RTX Remix
  Bridge client now verifies the `D3DTRANSFORMSTATETYPE` argument for calls to `SetTransform()`, and in the event the
  argument is invalid, it returns `D3DERR_INVALIDCALL` to the caller instead of making a round trip call to the RTX
  Remix Bridge server and the dxvk-remix component of the RTX Remix Runtime.

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) </sub>
