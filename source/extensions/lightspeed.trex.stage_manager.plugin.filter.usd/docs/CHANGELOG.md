# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).


## [2.6.1]
### Fixed
- Fixed `SceneEditFilterPlugin` filter activation and context-rebind source-layer selection reset so non-default edit-state modes affect Stage Manager results.

## [2.6.0]
### Added
- Added `SceneEditFilterPlugin` ("Edit State"): plain-language filter for finding modified prims, untouched prims, and prims with unused edits. Sits parallel to the existing "Asset State" filter and targets scene cleanup workflows.
- Added Source Layer(s) picker to `SceneEditFilterPlugin`. When the combo is set to "Modified prims" or "Prims with unused edits", a clickable "Source Layers" action label below the combo opens a layer-tree window that lets the modder narrow the filter to a chosen subset of source layers. The tree is the standard `omni.flux.layer_tree.usd.widget.LayerTreeWidget` with a custom delegate that adds a checkbox per row; checkboxes are enabled only for layers in the replacement (mod) subtree. Includes a case-insensitive search field and Select all / Deselect all controls.

### Changed
- Added hyphenated option descriptions to Remix Stage Manager combobox filter tooltips.
- Included Remix Stage Manager `filter_active` runtime state in filter serialization for modified-state checks.
- Made Remix Stage Manager combobox filters fill the available control width, added dashed `SceneEditFilterPlugin` tooltip option descriptions, shortened the unused-edits label, renamed the source-layer filter action, and refreshed the source-layer picker layout, title, copy, and checkbox spacing.
- Updated Remix Stage Manager filters to share `filter_active` refresh wiring.

### Fixed
- Fixed `SceneEditFilterPlugin` source-layer cache invalidation when a new stage opens in the same USD context.
- Fixed neutral/default Remix combobox filters participating in Stage Manager filtering.

## [2.5.1]
### Changed
- Updated documentation index to include filter submodules

## [2.5.0]
### Added
- Added `DELETED` reference type to `IsCaptureFilterPlugin` to filter prims whose capture reference has been removed
- Added lightspeed-specific `GeometryPrimsFilterPlugin` that keeps deleted `mesh_HASH` prims visible when the geometry filter is active

## [2.4.1]
### Changed
- Updated tooltip for filter plugins to be on the HStack

## [2.4.0]
### Added
- Added filter categories to the filter plugins

## [2.3.3]
### Changed
- Modernize python style and enable more ruff checks

## [2.3.2]
### Changed
- Updated filter plugin comboboxes to use the correct index for combobox creation

## [2.3.1]
### Changed
- Updated MeshPrimsFilterPlugin to exclude lights in the filter

## [2.3.0]
### Added
- Added `InstanceGroupFilterPlugin` filter plugin
- Added `MeshGroupFilterPlugin` filter plugin
### Changed
- Renamed MeshPrimsFilterPlugin's label to "Geometry Prims"

## [2.2.1]
### Changed
- Updated is_logic_graph filter plugin to be more inline with current style guide and practices

## [2.2.0]
### Added
- Added `ParticleSystemFilterPlugin` filter plugin

## [2.1.1]
### Changed
- Updated is_logic_graph filter plugin to have a public field for the current filter type

## [2.1.0]
### Added
- Added filter plugin remix logic graphs

## [2.0.3]
### Changed
- Updated filter plugin UI to be more consistent

## [2.0.2]
### Changed
- rename "Remix Category" to "Render Category"

## [2.0.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [2.0.0]
## Changed
- Updated Pydantic to V2

## [1.3.2]
## Changed
- rename trex prim utility names for clarity

## [1.3.1]
## Changed
- Update to Kit 106.5

## [1.3.0]
### Added
- Added mesh prims filter

## [1.2.0]
### Added
- Added Remix Category check

## [1.1.1]
### Fixed
- Fixed tests flakiness

## [1.1.0]
### Changed
- Changed the filter function to the updated filter predicate

## [1.0.0]
### Added
- Created
