# Full changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Created 1.0.0 build
- Added release notes for 1.0.0
- Added tests for REST API endpoints
- REMIX-3891: Added Material Property Widget control with Stage Manager Materials Tab

### Changed
- Improved the documentation layout and contents
- Fixed changelog formatting
- Tweaked release notes

### Fixed
- Fixed tests for the `omni.flux.validator.mass.widget` extension
- Fixed `get_texture_material_inputs` API endpoint for Kit 106.5
- Fixed `is_valid_texture_prim` API validator for Kit 106.5
- Redirect documentation pages that were moved to avoid 404 errors
- REMIX-3869: Made extension lowercase for texture validation
- Fixed Quick Start Guide link on the home page
- REMIX-3900: Added ImageWithProvider to better display single channel textures
- REMIX-3581: Fix multi-selection visibility toggle to have consistent behavior
- REMIX-4043: Fixed layer creation transferring metadata from parent layer
- REMIX-4073: Fixed Material Property Widget saving overrides onto instances instead of meshes
- Fixed Toolkit Build Dependencies to allow building externally

### Removed
- Cleaned up legacy code and unused files

## [1.0.0]

### Added
- Created 2024.5.1 build
- REMIX-3399: Added Sentry metrics for unique users and app elapsed time
- fixed permissions after moving gitlab CI files
- fixed linux build script syntax
- REMIX-3048: Added slider widget for material attribute displace_out
- Added PyCharm Debugger extension
- REMIX-3656: Added nightly GitLab CI SOAK test pipelines
- Added 7 videos to remix-releasenotes.md for 0.6 Release Notes Documentation
- New repo tool to help when making similar changes across many extensions: `.\repo bump_changed_extensions`
- REMIX-3785: Added a Skeletons Interaction Tab to Stage Manager
- REMIX-1811: Added a skeleton remapper tool for animated character replacements
- REMIX-3769: Added Custom Tags widget for all existing Interactions
- REMIX-3769: Added Custom Tags Tab for the Stage Manager
- REMIX-3657: Added a Categories Interaction Tab to the Stage Manager
- REMIX-3767: Added a Meshes Tab for the Stage Manager
- REMIX-3659: Add the ability to get default output directory in Ingestion and AI Tools tabs
- REMIX-3770: Added a Materials Tab for the Stage Manager
- REMIX-3832: Added a new material api extension to omni.flux
- REMIX-3904: Added packaging documentation
- Added SSS material support
- Added slider widget for material attribute subsurface_diffusion_profile
- REMIX-3725: Added support for optional properties on light prims
- Added SSS radius texture: updated hdremix and MDL material definition
- REMIX-3992: Added alphabetical sorting for the Stage Manager parent items
- Created 1.0.0-rc1 build
- Added "Show Install Directory" entry to the home screen

### Changed
- Updated hdremix to dd92d0f
- REMIX-3640: Use Async Threaded Processing for Filtering of the Stage Manager items
- Stage Manager: Add set_context_name() as a way to refresh plugins before building tree.
- REMIX-3639: Reduce the number of refreshes requested by the USD Event Callback in the Stage Manager
- Updated remix-releasenotes.md with 0.6 Release Notes
- Updated to import AsyncTestCase from public api
- Updated remix-overview.md with correct specs and improved documentation
- Updated order of steps in remix-installation.md to reflect most likely execution order
- Publish apps for etm testing
- REMIX-3579: Updating Remix Categories window with more documentation
- Convert the Stage Manager row backgrounds to use a TreeView for improved performance
- Changed the Stage Manager frame raster policy for improved performance at rest
- Simplified the UAC logic
- REMIX-2714: Updated the Home Page of the app
- REMIX-3835: Removed whitespace restrictions from project creation
- REMIX-3858: Move Open option to the Home Screen
- Added automated CR/LF line endings for .toml files for dependencies
- Changed CI/CD stages to remove check-changelog from the start
- REMIX-3894: Use scale instead of meters per unit for ingestion
- REMIX-3896: Improve the Unload Stage (Close Project) button behavior
- REMIX-3831: Updated kit version to 106.5.0
- REMIX-3832: Update material property widget to work with virtual attributes
- Upgraded the AI Tools PyTorch Version
- REMIX-3904: Improved mod packaging flow by adding a window to fix unresolved assets
- Updated hdremix to 873426e, added params for supporting diffusion profile and transmission of subsurface scattering
- Updated hdremix to 9e5efd6, fixed NaN issue in SSS
- Update MDL Material to change the range of SSS Scale from 0-65504 to 0-1000
- Updated hdremix binaries to use the latest remix-2025 branch of dxvk-remix
- Updated hdremix to 13b89c8, volumetric influence fix
- Updated hdremix to 3c38541 and omni_core_materials to 16
- Centered UAC dialog + Added Show Logs on home screen
- REMIX-3989: Enable the Stage Manager by default
- REMIX-3989: Rename Experimental Features to Optional Features
- Modified the property trees throughout the app to make more efficient use of space
- Updated hdremix to 30ccb8e
- Updated runtime to 1.0.0

### Fixed
- REMIX-2350: Updating capture window behavior to avoid it hanging on other tabs
- Fixed CI Agent tags
- Fixed Flaky tests
- Fixed Linux Agents
- GH-PR1: Conform table format style in docs and cleanup bad table (Thanks @gordongrace)
- Fixed disclosure icon display so tree view and panels mean the same thing
- REMIX-3447: Fixed Material and Mesh widgets relying on the selection panel tree
- REMIX-3764: Only show categories icon when a mesh is selected
- Enabled Extension Registry
- Fixed various Stage Manager issues
- REMIX-1811: Skeleton Remapping Tool: Fixes, convenience buttons and alternating row colors
- Fixed capture list not loading captures properly
- REMIX-3866: Fixed layers panel performance in large projects
- REMIX-3895: Fixed light selection behavior in selection panel
- REMIX-3865: Fixed layer panel inconsistent muteness state
- REMIX-3888: Fixed layer panel not refreshing after unloading stage + more fixes
- REMIX-3832: Fix display of "display out" and other material attributes that shouldn't be hidden
- REMIX-3870: Fixed ingestion bug for drag and drop
- Tooltips on properties from USD schema now include the documentation string from the schema.
- Fixed packman remote configuration for building from lspackages
- Fixed initial display for virtual attributes like volumetric radiance scale before they are set.

## [2024.5.1]

### Added
- Create 2024.4.1 build
- REMIX-2988: Added manual CI test to measure app startup times
- REMIX-3401: Added Centralized Generic factory
- Add github windows and linux build actions
- Add Data Migration documentation
- Adding tests for Remix Categories
- Adding tests for layer validation
- REMIX-3402: Added skeleton and example implementation for the Stage Manager
- REMIX-3051: Configured the save prompt to open during stage unloads with unsaved changes
- REMIX-3052: Added a new "reload last stage" workfile menu item
- REMIX-3403: Setup Stage Manager Core & Schema
- REMIX-3404: Added Stage Manager Widget
- REMIX-3440: Implemented USD Tree Plugins
- REMIX-2874: Added a scan folder dialog for importing
- REMIX-3443: Implemented USD Visibility Plugins
- REMIX-2518: Added external asset prevention/copying functionality
- REMIX-2907: Added warning when invalid file types are dropped for ingestion
- REMIX-3441: Implemented Lights interaction plugins
- REMIX-3214: Checking layer type at project file import validation
- REMIX-3215: Checking layer type at mod file import validation
- REMIX-3477: Implemented USD listeners for the stage manager
- REMIX-3478: Implemented selection syncing for the stage manager
- REMIX-3479: Added the ability to deactivate interaction plugins when not visible
- REMIX-3398: Added settings for enabling Sentry reporting
- REMIX-3536: Implemented a widget to display captured & replaced prims
- REMIX-3535: Implemented a filter to display captured & replaced prims
- REMIX-2605: Added support for editing multiple meshes, materials or lights
- REMIX-2605: Added support for editing multiple mesh xforms
- REMIX-3541: Docked Stage Manager in Modding layout
- REMIX-3583: Added a Feature Flags system
- REMIX-3567: Enable Sentry for built versions
- REMIX-3113: Parallel process count dropdown for ingestion
- REMIX-3583: Added tests for the Feature Flags system
- Added a tutorial on how to use the REST API to build a Blender Add-On
- REMIX-3600: Selection panel behavior improvements and fixes
- REMIX-3576: Implement auto scroll to selection behavior for Stage Manager
- REMIX-3537: Added a "Focus in Viewport" widget plugin for Stage Manager

### Changed
- Updated runtime to 0.6.0
- Updated hdremix to a1863ffe
- Updated hdremix to e57c4c6
- Updated hdremix to 132d6dc
- Renamed `Feature Flags` to `Experimental Features`
- Updated Nucleus Registry accounts
- Updated Repo Tools to the latest public versions
- Refactored the Stage Manager to optimize performance and add flexibility
- Added `IsCapture` Widget & Filter to the `AllPrims` interaction in the Stage Manager

### Fixed
- REMIX-3401: Fixed hot-reload by allowing reuse of validators
- REMIX-3058: Fixed material file path tooltips and copy menus
- Fixed changelog checker with type casting to support semantic versioning
- Corrected documentation typo
- REMIX-3385: Fixing texture set assignment
- REMIX-2874: Improved look of scan file window
- REMIX-2605: Fixed some property widget styling
- REMIX-3567: Fixed shell script permission
- Fix `select_prim_paths_with_data_model` crash for the Rest API
- Fix `append_reference_with_data_model` crash for the Rest API
- REMIX-3602: Fix most important performance issues with the Stage Manager
- Clear all listeners when disabling the Stage Manager feature flag
- REMIX-3565: Fixed icon display for lights in selection panel
- Fix `replace_reference_with_data_model` crash for the Rest API
- Fix extension publication job in CI
- REMIX-3638: Fixed scroll to item behavior for tree selection
- REMIX-3615: Updating texture set search for better comparisons
- REMIX-3628: Fixed AI Tools "Current Process" executor mode.
- REMIX-3640: Fixed various stage manager bugs
- REMIX-3386: Fix transform manipulator bug that occurred after captured asset deletion

## [2024.4.1]

### Added
- Create 2024.4.0-RC.6 build

## [2024.4.0-RC.6]

### Added
- Create 2024.4.0-RC.5 build
- REST API Documentation

### Changed
- Update runtime to 0.5.4

### Fixed
- Fix `AllTextures` plugin

## [2024.4.0-RC.5]

### Added
- Create 2024.4.0-RC.4 build

### Changed
- Update to `remix-0.5.3`

### Fixed
- Fixed AI Tools by settings the internal pip archive import order
- REMIX-3058: Fixed material file path tooltips and copy menus
- Fixed changelog checker with type casting to support semantic versioning

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

## [2024.4.0-RC.3]

### Added
- Create 2024.4.0-RC.2 build
- REMIX-2593: Added a centralized TreeWidget with additional logic
- REMIX-3075: Added a layer type check in validation
- REMIX-2874: Added a scan folder dialog for importing

### Changed
- REMIX-2593: Changed the LayerTree widget to work with multiselect

### Fixed
- REMIX-3076: Added trailing slash to end of dirname when double-clicking in file dialog
- Fix manipulator that was giving wrong data
- Re-add event that was mistakenly removed
- Fixed inconsistent RC versions

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

## [2024.3.1]

### Changed
- Update runtime build to 0.5.1

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

## [2024.3.0-RC.3]

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

## [2024.3.0-RC.1]

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
