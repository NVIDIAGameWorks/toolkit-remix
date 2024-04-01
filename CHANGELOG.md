# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- REMIX-2640: Always use a group for material properties
- REMIX-2868: Added CI tool to verify that all tests are in 'e2e' or 'unit' directories
- REMIX-2734: Unselect all objects with ESC
- REMIX-2667: Added the CHANGELOG.md file and CI check for it

### Changed
- REMIX-2692: Ingestion has the option to use an external process to run, which doesn't slow down the main app. Enabled by default.

- REMIX-2866: Moved tests into 'e2e' or 'unit' subdirectories

### Fixed

- REMIX-2866: Corrected imports in several test directories

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
