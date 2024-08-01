# Full changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Create 2024.4.0-RC.5 build
- REMIX-2988: Added manual CI test to measure app startup times

### Changed

### Fixed
- Fix `AllTextures` plugin

### Removed

## [2024.4.0-RC.5]

### Added
- Create 2024.4.0-RC.4 build

### Changed
- Update to `remix-0.5.3`

### Fixed
- Fixed AI Tools by settings the internal pip archive import order

### Removed

## [2024.4.0-RC.4]

### Added
- Create 2024.4.0-RC.3 build
- REMIX-2783: Added light manipulator for CylinderLight

### Changed
- Updated repo tools + added public version of repo lint
- REMIX-3071: Refactor shutdown event to cleanup 2 way dependency
- Disable HDRemix bootstrap

### Fixed
- Fixed layer validation for new layer
- Fixed layer validation
- Fixed Open Project microservice endpoint + Added tests for service
- Textures are now reloaded when the corresponding files are overwritten

### Removed

## [2024.4.0-RC.3]

### Added
- Create 2024.4.0-RC.2 build
- REMIX-2593: Added a centralized TreeWidget with additional logic
- REMIX-3075: Added a layer type check in validation

### Changed
- REMIX-2593: Changed the LayerTree widget to work with multiselect

### Fixed
- REMIX-3076: Added trailing slash to end of dirname when double-clicking in file dialog
- Fix manipulator that was giving wrong data
- Re-add event that was mistakenly removed
- Fixed inconsistent RC versions

### Removed

## [2024.4.0-RC.2]

### Added
- REMIX-2879: Added `USDC_USE_PREAD` environment variable to enable overriding opened deps
- REMIX-2489: Fixed and improved asset replacement and overwriting capabilities for referenced assets
- REMIX-2603: Added dialog to set remix categories
- REMIX-2814: Selection tree multi-selection upgrades
- Add a trigger pipeline to publish in the launcher (artifact bug)
- REMIX-2236: Added github actions config and necessary files for github CLA bot
- REMIX-3058: Added a material file path tooltip and copy menu for material property items
- REMIX-3345: Added a tool to help with compatibility migrations for breaking data changes
- Detect broken layers when creating a new one

### Changed
- Rename branch to `main`
- REMIX-2967: Changed CI tool to check changes to extensions are properly updated
- REMIX-2871: Remove parent prim override if there are no changed attrs
- REMIX-3105: Simplifying texture set logic with centralized texture set logic
- REMIX-3083: Fixed ingestion progress bar to update count when ingestion is complete
- Set back the regular pipeline
- REMIX-2880: Remove unused libs
- Move the job "publish in the launcher" into the Gitlab publish pipeline

### Fixed
- REMIX-3078: Fixed texture preview window overlapping
- REMIX-3079: Fixed texture preview windows showing the incorrect texture
- Fixed the hotkey test so that it can handle developer mode
- Removed the USDC_USE_PREAD environment variable since it causes crashes for projects with many textures
- REMIX-2825: Updated renderer to the latest dxvk-remix to accomodate USD distant light import/export fixes
- Fixed highlight outline rendering if selecting non-power-of-two amount of objects
- Fix trigger pipeline
- Fix CI that crash because of a wrong ingested asset
- Multiple fixes for Checkmarx

### Removed
- REMIX-3152: Removed the delete and duplicate button icons for asset reference light items in the selection tree

## [2024.4.0-RC.1]

### Added
- REMIX-2674: Adding a check for similar textures and auto-populating texture fields
- Add repo tool to delete `Unreleased` section from the changelog
- REMIX-2779, REMIX-2780, REMIX-2781: Add light manipulators for RectLight, DistantLight and DiskLight
- REMIX-2782: Added light manipulator for SphereLight
- Add packman publish stage for scheduled job(s)
- Added lightweight kit app for HdRemix image testing: lightspeed.hdremix.test-0.0.0
- Don't publish in the launcher for scheduled pipeline(s)
- REMIX-2137, REMIX-2138, REMIX-2139, REMIX-2142, REMIX-2842: Added microservices for the "Modding" & "Ingestion" sub-apps
- REMIX-2880: Merged Flux extensions for OSS release
- C function binding to set RtxOption directly into the Remix Renderer
- REMIX-3096: Added a right-click copy menu for selection tree items

### Changed
- REMIX-2880: Change to hide things for security
- REMIX-2722: Reduced default light intensities
- REMIX-2876: Update to Kit Kernel 106
- OM-122163: Update Remix manipulator to adapt omni.kit.manipulator.prim renaming
- REMIX-3125: Calculate float slider default step size lazily
- REMIX-3112: Change displace_in slider range and default value to improve useability.
- REMIX-2880: Improved CI setup for merged repos
- REMIX-2880: Split PIP Archives between LSS, Flux & Internal Flux
- REMIX-2880: Update to latest public Kit SDK

### Fixed
- REMIX-2872: Made the non-ingested asset message more descriptive
- Fixed release notes version to release version
- Fixed documentation URL for release notes
- REMIX-2872: Improved the non-ingested asset message
- REMIX-2789: Ingestion queue scroll bar
- REMIX-2943: Make file extension validation case-insensitive
- REMIX-2684: Created camera light event
- Fixed various issues with microservices & added new endpoints and improved functionality

### Removed

## [2024.3.1]

### Added

### Changed
- Update runtime build to 0.5.1

### Fixed

### Removed

## [2024.3.0]

### Added
- REMIX-1248: Cursor now visibly changes over vertical bar
- Add a test video in the doc

### Changed
- REMIX-1248: Cursor now visibly changes over scroll bars
- REMIX-3008: for now, because of REMIX-3008, disable drag and drop
- Update to remix-0.5.0
- Update `remix-releasenote.md`

### Fixed
- REMIX-2723: Fixed file browser search bar
- REMIX-3002: Fix when the process executor is run from a Kit that is in a folder with a space
- REMIX-1090: Fixed capture list popup height math

### Removed

## [2024.3.0-RC.3]

### Added

### Changed
- REMIX-2674: Adding a check for similar textures and auto-populating texture fields on value change
- Updated drag and drop regex to be case-insensitive and multi-texture dialog
- Create a release note in the documentation
- Update to remix-0.5.0-rc1
- REMIX-2939: optimize process executor from Ingestion and AI Tool to not update UI if not visible
- REMIX-2997: Improve Check Plugins load speed on startup

### Fixed
- REMIX-2820: Fix project wizard and file picker close
- Fix property editor crash for unknowns widget builders
- Start `lightspeed.event.capture_persp_to_persp` before the global event
- Fix default waypoint creation (create it in the root layer)
- Fix incorrect clear value for the viewport (appeared as red instead of black)
- REMIX-2939: Fix item progression update for the Ingestion and AI Tool (using process executor)
- REMIX-2422: Fixed Teleport to properly work with prototypes and instances

### Removed

## [2024.3.0-RC.2]

### Added
- REMIX-1596: Create waypoint for game camera on start
- Ray Reconstruction to the renderer
- Gitlab auto release pipeline
- REMIX-2880: Add Apache license to all files + add Apache license
- REMIX-2589: Add a way to customize property widgets per-attribute

### Changed
- Correcting shutdown function for waypoint extension
- REMIX-2791: Replace a variety of float widgets with sliders

### Fixed
- REMIX-2731: Fix AI tools failing for captured DDSs

### Removed

## [2024.3.0-RC.1]

### Added

- REMIX-2658: Added a menu option to Unload Stage to reclaim resources without closing app
- REMIX-2640: Always use a group for material properties
- REMIX-2868: Added CI tool to verify that all tests are in 'e2e' or 'unit' directories
- REMIX-2734: Unselect all objects with ESC
- REMIX-1596: Drag and drop textures from filebrowser
- REMIX-2667: Added the CHANGELOG.md file and CI check for it
- REMIX-2492: Added a save prompt that shows up if the project has been modified when closing the app to prevent lost work
- REMIX-2830: Attribute pinning and properties panel clearing
- REMIX-2620, REMIX-2636: Add capture list refresh button and fix invisible path
- REMIX-1924: Enabling waypoints in Remix
- REMIX-2831: A world position utility, exposed from HdRemix
- REMIX-2422: Added a new "teleport" tool to bring selected objects to your mouse or center screen
- Generate RC.1 for QA
- Pipeline to auto generate release build(s)
- Ray Reconstruction to the renderer

### Changed
- REMIX-2692: Ingestion has the option to use an external process to run, which doesn't slow down the main app. Enabled by default.
- REMIX-2866: Moved tests into 'e2e' or 'unit' subdirectories
- REMIX-1081: Improved UX for going from an open project to saved one by consolidating 2 dialogs into 1 with Save, Save As, Don't Save, Cancel options.
- REMIX-2875: HdRemix extension to be more independent from other extensions
- REMIX-2722: Update light default value extensions
- REMIX-2751: Create symlink(s) during project creation
- REMIX-1076, REMIX-2699: Improve text legibility
- REMIX-2829: Sanitize the whole project to publish extensions
- REMIX-2875: HdRemix extension to be more independent from other extensions
- REMIX-2869: Run the e2e tests, the unit tests, and the doc build in parallel

### Fixed
- REMIX-2707: Fix issue with material properties changing groups after overrides are deleted
- REMIX-2715: Fix various issues with the ColorField
- REMIX-2866: Corrected imports in several test directories
- REMIX-1090: Capture list header adjustment

### Removed


## [2024.2.1]

### Added:
- REMIX-2541: Expose Inference Mode UI for AI Texture Tool
- REMIX-2526: AI Texture accept jpeg
- REMIX-119: Automatically switch to the mod layer when a wrong layer is set as an edit target
- REMIX-74, REMIX-114, REMIX-1483: Add events to validate the project + restore edit target
- REMIX-2695: Check if Remix is supported
- REMIX-2028: Add duplicate button to lights in selection tree
- REMIX-1090: Add tree headers to the capture list to describe the columns
- REMIX-1923: Add xform copy/paste functionality
- REMIX-114: Save Authoring Layer on Set

### Fixed:
- REMIX-2669: Fix slowdown on project creation + light optimization
- REMIX-2521: Adding check for Windows reserved words
- REMIX-2709: Fix capture window dpi
- REMIX-1542 REMIX-1693: don't lose focus of widgets when modifying properties
- REMIX-2419 REMIX-2736: Handle 'f' key press anywhere on layout or ingestion tab. Handle 'Ctrl+S', etc. key presses on all tabs
- REMIX-2719: Choose the same GPU for DXVK, as the one in Hydra Engine
- REMIX-2722: Adjust default light intensity (first pass. Will do more ajustements)
- REMIX-2642: Spelling / Wording / Grammar corrections in the Annotations for the Input File Path
- REMIX-2654, REMIX-2661: AI Tools don't run on 20-series GPUs. AI Tools don't get cleaned out of memory after inference is done.
- [HDRemix] Fix scale not affecting lights
