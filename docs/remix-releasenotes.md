# RTX Remix Release Notes (5/13/2024)

## RTX Remix Toolkit Release 2024.4.0-RC.1
### Changed
- Updated the runtime included with the RTX Remix Toolkit to version 0.5.1

## RTX Remix Runtime 0.5.1
### Bug Fixes
- Fixed an issue preventing the Remix runtime from starting on AMD hardware with the latest Windows drivers

# RTX Remix Release Notes (4/30/2024)

With the latest update of RTX Remix, we've enabled modders to add DLSS 3.5 Ray Reconstruction for Remix mods. Look below for our detailed release notes, and for a full changelog, please click [here](remix-full-changelog.md)

As a reminder, you can update RTX Remix by clicking the menu next to the "Launch" prompt on the RTX Remix Application page of the Omniverse Launcher.

## RTX Remix Toolkit Release 2024.3.0

### Features
- Added a new "Teleport" action to teleport any selected object to your mouse cursor or the center of the screen. Teleport via the viewport sidebar or the Ctrl + T hotkey.

<video width="640" height="400" style="display:block; margin: 0 auto;" autoplay loop muted controls>
  <source src="./videos/teleport.mp4" type="video/mp4" />
  Your browser does not support the video tag.
</video>

- Added a new “Waypoint” feature, enabling modders to save camera positions as waypoints and snap the camera to them. Waypoint options can be found in the top right corner of the viewport. By default, opening a capture will save the camera starting position as a waypoint.

<video width="640" height="400" style="display:block; margin: 0 auto;" autoplay loop muted controls>
  <source src="./videos/waypoints.mp4" type="video/mp4" />
  Your browser does not support the video tag.
</video>

- Added DLSS 3.5 Ray Reconstruction to the Viewport

- Material/object property panels can now be pinned for any selected asset, keeping them locked into view even after deselecting the object. This enables interesting workflows–for example, selecting a wall and locking its material properties panel, selecting a light near the wall and locking its object properties panel, and being able to simultaneously adjust the wall and light in relation to one another.

<video width="640" height="400" style="display:block; margin: 0 auto;" autoplay loop muted controls>
  <source src="./videos/panel_pinning.mp4" type="video/mp4" />
  Your browser does not support the video tag.
</video>

- Added the option to unload the stage to reclaim resources without closing the app. This function is useful if you need to free up memory to do certain actions (for example, boot the game while running RTX Remix, or run RTX Remix’s AI Texture Tools). This option can be found in the top left menu.

<video width="640" height="400" style="display:block; margin: 0 auto;" autoplay loop muted controls>
  <source src="./videos/unload_stage.mp4" type="video/mp4" />
  Your browser does not support the video tag.
</video>

- Rearchitected AI Texture Tool and Ingestion processes to allow the RTX Remix Toolkit to run efficiently in parallel with them. Modders should have a much easier time multitasking while ingesting or AI enhancing assets.

<video width="640" height="400" style="display:block; margin: 0 auto;" autoplay loop muted controls>
  <source src="./videos/parallel_processing_no_lag.mp4" type="video/mp4" />
  Your browser does not support the video tag.
</video>

### Quality of Life Improvements

- ESC key now unselect all objects

- Added sliders for all material and object properties

<video width="640" height="400" style="display:block; margin: 0 auto;" autoplay loop muted controls>
  <source src="./videos/realtime_sliders.mp4" type="video/mp4" />
  Your browser does not support the video tag.
</video>

- Closing RTX Remix with unsaved data will now present a save prompt, so that modders do not lose any progress. Also streamlined UX for going between open and saved projects.

- Added a refresh button to the capture list, and improved thumbnail pop ins to be less disruptive

- Grouped several material properties that lacked a parent category into their own “Other” category

- Updated default light intensity values for all newly created lights to be much lower. Newer default behavior should pair better with more games.

- Project creation now creates symlinks

- Made several improvements to accessibility, text legibility and text clarity

### Bug Fixes

- Attribute and material properties now properly behave with object selection and deselection

- Fixed issues with material properties pane changing unexpectedly when using undo and redo functions

- Fixed various responsiveness issues with the ColorField/color selector

- Added headers to the capture list to help explain captures and replacement progress

- Fixed crashes with the AI Texture Tools when processing DDS files

## RTX Remix Runtime 0.5.0
Note to modders–with RTX Remix Runtime 0.5 we have removed an option that was causing excessive ghosting with no benefit to users. If your project requires you to remain on an older RTX Remix Runtime, we advise you to check your rtx.conf file, and ensure `rtx.enableDeveloperOptions = false`.

### Features
- Added DLSS 3.5 Ray Reconstruction to RTX Remix, making it possible for modders to improve image quality with this AI powered denoiser. With ray reconstruction, path traced lights update faster, reflections and thin light detail are more stable, and texture details can pop more. Learn more about ray reconstruction and its benefits for RTX Remix modding in our [GeForce article](https://www.nvidia.com/en-us/geforce/news/rtx-remix-dlss-3-5-ray-reconstruction)
- Added the d3d8to9 wrapper to the runtime release. The d3d8to9 wrapper was an essential file modders had to manually add to their runtime package in order to unlock proper compatibility in DirectX 8 titles. Now, we include it automatically–modders should find highly compatible DirectX 8 games to work better out of the box thanks to this change. This change should not impact non-DirectX 8 titles.
- Significantly changed the texture tagging flow, which is essential to properly setting up a game with RTX Remix. We’ve added several new options that should streamline how advanced users interact with these menus. These changes are likely to undergo further iteration, and we encourage any early feedback on them.

  We've changed how texture tagging works when the “Split Texture Category List” option is toggled on. When “Split Texture Category List” is toggled on, opening or hovering over a texture category selects it (indicated by it turning orange). Left clicking a texture in the gameworld or the category list will automatically assign it to the currently selected texture category. Right clicking a texture in the game world or in the Remix runtime category lists will give users the very familiar texture selection drop down menu to choose from all of the available texture tagging options. Please note, you must have a texture category selected to tag textures in this mode.

  We’ve also added an option to only view texture categories that contain textures you have already tagged. You can select this by toggling the "Only Show Assigned Textures in Category Lists" checkbox. When checked, untagged textures will appear in their own “Uncategorized” category

  Thank you to community contributor “xoxor4d” (Github PR #49) for submitting the code for this change. We look forward to further improving how game setup and texture tagging works in RTX Remix.

### Quality of Life Improvements

- Improved stability and performance in shader-based games by enhancing the vertex capture system
- Resolved visual artifacts, like banding, with tonemapper by introducing blue noise driven dithering. To enable this feature in the RTX Remix Runtime menu, go to “Post-Processing” > “Tonemapping” and set “Dither Mode” in the dropdown to “Spatial + Temporal” (uses a noise pattern that changes over time) or “Spatial” (uses a static noise pattern). The config options for these settings are `rtx.localtonemap.ditherMode` and `rtx.tonemap.ditherMode` for the local and global tonemappers respectively. These config options can be set to 1 for Spatial dither mode or 2 for Spatial + Temporal dither mode (or 0 to disable dithering).
- Added config options to hide the RTX Remix splash banner (`rtx.hideSplashMessage = True/False`) and to display a custom welcome message to the user on startup (`rtx.welcomeMessage = “example text”`)
- Added option to pass the original game’s cubemaps to RTX Remix’s backend. This enables cubemap textures to be used for tagging. Note that cubemaps will not render correctly, and draw calls that reference only cubemaps are not usable in Remix. To enable this feature in the RTX Remix Runtime menu, go to the “Game Setup” tab > “Step 2: Parameter Tuning” > “Heuristics” and check off “Allow Cubemaps”. Or, use the config option `rtx.allowCubemaps = True`.
- Added the ability to ignore baked lighting associated with certain textures. This is useful in cases where the game bakes out lighting to vertex colors or texture factors (rather than lightmaps). To use this feature, in the RTX Remix Runtime menu’s "Game Setup" tab, as part of the texture tagging workflow, there is now a new category called “Ignore Baked Lighting Texture”.
- Added the option to configure various RTX Remix systems that rely on a game’s world space coordinate system (ex: terrain baking) to assume a left-handed coordinate system.

  When modding a game with a left-handed coordinate system, you may notice that terrain, even after being properly tagged in the Game Setup tab, still looks incorrect. Open the RTX Remix Runtime menu, and in the “Game Setup” tab, under parameter tuning check off the “Scene Left-Handed Coordinate System” checkbox, and suddenly all of these systems, like terrain baking, should begin to work properly. The config option for forcing these rendering systems to assume a left handed coordinate system is `rtx.leftHandedCoordinateSystem = True`.

  Thank you to community contributor “jdswebb” (Github PR# 65) for submitting the code for this change.

- Added an option to use AABBs to differentiate instances, and therefore track them better across frames. For gamers, that means less ghosting and flickering for animated objects and skinned meshes in motion. To enable this feature, open the "Game Setup" tab of the RTX Remix Runtime menu, select "Step 2: Parameter Tuning" > "Heuristics" and toggle on "Always Calculate AABB (For Instance Matching).

  Thank you to community contributor “xoxor4d” (Github PR# 67) for submitting the code for this change.

- Improved how RTX Remix mods run for Steam Deck and Linux AMD users, thanks to optimizations for RADV drivers.

  Thank you to community contributor “pixelcluster” (Github PR #63) for submitting the code for this change.

- Improved the consistency of distant lights, making them update properly when changing or reorienting them. This fixes bugs in certain scenarios like when a distant light was parented to a mesh that rotates.

  Thank you to community contributor “mmdanggg2” (Github PR #66) for submitting the code for this change, and thank you to “Kamilkampfwagen-II” for reporting the issue on GitHub (issue #49).

- Enabled the function logging feature in the RTX Remix Bridge found within the "Debug" build to also be in the "Debug Optimized" build.
- Added an option `logServerCommands` to the RTX Remix Bridge to write what commands the server is processing to the `NvRemixBridge.log` file. To enable, in the `bridge.conf` file found alongside the NvRemixBridge.exe, set `logServerCommands = True` with no leading # mark. If `bridge.conf` does not exist, you can get it from https://github.com/NVIDIAGameWorks/bridge-remix/blob/main/bridge.conf
- Added an additional logging mode that includes the messages of logServerCommands, and status information from the RTX Remix Bridge client/server messaging systems. This can be helpful for catching potential bridge messaging issues. To enable, in the `bridge.conf` file found alongside the `NvRemixBridge.exe`, set `logAllCommands = True` with no leading # mark. If `bridge.conf` does not exist, you can get it from https://github.com/NVIDIAGameWorks/bridge-remix/blob/main/bridge.conf

### Compatibility Improvements
- Made several changes to the RTX Remix Bridge that enhance compatibility across a variety of games

- Fixed an issue that would cause certain games to hang. There was a deadlock in the RTX Remix Bridge where the client would be blocked waiting for a shared buffer to be read, thinking that the server was behind, while the server was in actuality caught up and waiting for a new command. The client was improperly telling the server that it had overflowed the shared data buffer because the command sending code was not distinguishing between a pointer with valid data to send (which has non-zero size on the buffer) and a null-pointer (which has zero size on the buffer).

- Fixed crashes, graphical errors, and unexpected behavior caused by games running with RTX Remix by stalling the data queue in the RTX Remix Bridge when a write would overflow the queue while the overflow flag was already set.

- Improved certain incompatibilities where RTX Remix would close unexpectedly or stop updating the visuals (while audio continued to play). To correct an issue where a command processing thread could prematurely terminate if starved of commands for the bridge timeout duration, RTX Remix Bridge server timeouts are now disabled. Additionally, we now close the RTX Remix Bridge client on unexpected bridge server closure.


### Bug Fixes
- Fixed issues with texture capture, capture stutter, and capture corruption in certain titles

- Improved reliability of the RTX Remix Bridge build system.
- Sped up how quickly the RTX Remix Bridge informs the host game about invalid calls to `SetTransform()`. The RTX Remix Bridge client now verifies the `D3DTRANSFORMSTATETYPE` argument for calls to `SetTransform()`, and in the event the argument is invalid, it returns `D3DERR_INVALIDCALL` to the caller instead of making a round trip call to the RTX Remix Bridge server and the dxvk-remix component of the RTX Remix Runtime.
