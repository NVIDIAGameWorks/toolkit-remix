# Changelog

This document records all notable changes to the **lightspeed.trex.logic.widget** extension.

The format is based on [Keep a Changelog](https://keepachangelog.com). The project adheres to [Semantic Versioning](https://semver.org).

## [1.6.0]
### Added
- Added backdrop rename functionality via F2 hotkey and right-click context menu
- Backdrops can now be renamed directly (changes the prim name)

## [1.5.1]
### Changed
- Improved error dialog texts and messaging for prim selection errors
- Improved graph creation dialog wording and button label

## [1.5.0]
### Added
- Added tree-based graph selection UI with improved UX for Edit Graph dialog

### Changed
- Disabled compound graphs feature in Remix Logic Graph

## [1.4.0]
### Added
- Added sidebar button for quick access to Logic Graph layout

## [1.3.1]
### Fixed
- Fixed small bug that would allow logic graph creation on mesh prims, instead of rerouting to the mesh_hash


## [1.3.0]
### Added
- Added node type descriptions in tooltips when hovering over nodes
- Added port type info for union/any attributes showing valid connection types
- Added custom documentation routing for Remix nodes to dxvk-remix docs

### Changed
- Improved graph name input with validation for valid USD prim identifiers
- Help button now links to Remix logic documentation

## [1.2.0]
### Added
- Added missing (select all, select none, and delete selection) actions & hotkeys to the Logic Graph widget

## [1.1.1]
### Removed
- Removed Variables panel and Edit toolbar button from Logic Graph widget

## [1.1.0]
### Added
- Added create and edit logic graph functionality with dialog support
- Added custom styling for Remix Logic node type categories (Act, Sense, Transform)
- Added integration with LogicGraphCore for graph operations

### Changed
- Improved graph selection dialog size, added scrolling and improved layout for better readability
- Rebranded from experimental to standard feature (moved from Experimental menu)

## [1.0.1]
### Changed
- Updated dependency from lightspeed.error_popup.window to omni.flux.utils.dialog

## [1.0.0]
### Added
- Created based on `omni.graph.window.generic-1.60.0` and customized for Remix Components
