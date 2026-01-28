# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [4.8.1]
### Changed
- Switched to ruff for linting and formatting

## [4.8.0]
### Added
- Added a nickname attribute to the tree items

## [4.7.0]
### Changed
- Refactored `StageManagerInteractionPlugin` to use the new `ScrollingTreeWidget` component
- Decoupled scroll-frame and tree-view coordination logic into a reusable widget

## [4.6.0]
### Fixed
- Fixed stage manager not properly framing viewport selected items in the Skeleton Window

## [4.5.1]
### Added
- Added a delay to the refresh function to ensure the items are rendered before the refresh is called

## [4.5.0]
### Added
- Added `find_items_async` method to `StageManagerTreeModel` for non-blocking item searches
- Added `_is_expansion_task_cancelled` property for expansion task cancellation checks

### Changed
- Improved `_update_expansion_states_deferred` to run `items_dict` building in a background thread

## [4.4.0]
### Added
- Added `additional_filters` to the interaction plugins

## [4.3.1]
### Fixed
- Fixed stage manager not scrolling to the previous scroll position correctly

## [4.3.0]
### Added
- Refactor to expose `StageManagerFactory`
- Add `StageManagerMenuMixin`

## [4.2.0]
## Added
- Added a `cleanup` pattern to the stage manager context and listener plugins

## Fixed
- Fixed stage manager not refreshing to USD Notices

## [4.1.1]
## Added
- Integrating Omniverse Context Menu in the Stage Manager

## [4.1.0]
## Added
- Added telemetry to the stage manager refresh function

## [4.0.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [4.0.0]
## Changed
- Updated Pydantic to V2

## [3.6.2]
### Changed
- Removed a refresh call back to the interaction plugin

## [3.6.1]
### Added
- Added a refresh call back to the interaction plugin

## [3.6.0]
### Added
- Added `sort_items()` to `StageManagerTreeModel`
- Exposed `display_name_ancestor` as a property for `StageManagerTreeItem`

## [3.5.1]
## Changed
- Update to Kit 106.5

## [3.5.0]
### Added
- Added the ability for tree items to define their own `build_widget` method
- Added `display_name_ancestor` to the tree items constructor
- Added `get_unique_names` method to the Stage Manager Utils

## [3.4.0]
### Added
- Added the ability to cap the number of workers used for filtering

### Changed
- Force delegates to redraw on window resize
- Added a short delay between showing the loading screen and processing the context items to ensure the screen is displayed correctly

### Fixed
- Fixed Vertical Spacers in the interaction plugin tree UI

## [3.3.0]
### Changed
- Refactored row background to use a TreeView instead of a VStack

## [3.2.0]
## Added
- Added a `is_child_valid` method that is distinct from `is_valid` to tree items
- Added a `include_invalid_parents` option to the interaction plugin schema

## Changed
- Renamed `internal_filters` to `internal_context_filters` in the interaction plugin
- Renamed `filter_predicates` to `user_filter_predicates ` in the interaction plugin

## [3.1.1]
### Fixed
- Fixed tests flakiness

## [3.1.0]
### Added
- Added `debounce_frames` field for interaction plugins to debounce the item refresh function overloads
- Added `_queue_update` method to the interaction plugin to queue an update with debouncing

### Removed
- Removed `_queue_update_context_items`.

## [3.0.0]
### Added
- Added a loading overlay when the interaction plugin data is loading

### Changed
- Use asynchronous data filtering and refreshing methods in the interaction plugin
- Use flat list to represent the StageItems instead of a recursive tree
- Changed filtering to be threaded & async to avoid locking up the UI and parallelize work
- Changed the Tree Plugins `_build_items` and `_build_item` methods to use the flat list instead of the tree structure

## [2.0.2]
### Fixed
- Fixed the `filter_items` method from the `StageManagerUtils` that didn't use filtered children

## [2.0.1]
### Changed
- Added the ability to interaction plugins' `_update_expansion_states_deferred` method to not scroll to item on invocation

## [2.0.0]
### Added
- Introduced new `StageManagerItem` dataclass to transfer data between the context and interaction/tree/filter plugins
- Added `context_filters` to the interaction plugin
- Added a `_context_items_changed` event to the interaction plugin
- Added a 2-pass pipeline for data filtering (context filtering & user-filtering)
- Added `_build_items` and `_build_item` methods to the tree plugin to customize how items are refreshed

### Changed
- Moved `tree` definition from the schema to an abstract property in the interaction plugin
- Renamed `required_filters` to `internal_filters` in the interaction plugin
- Moved the tree refresh call to the `_context_items_changed` listener of the interaction plugin
- Simplified the alternating colors drawing logic in the interaction plugin
- Centralized the refresh logic in the tree plugin
- Filtering is now down in an upside-down manner to make sure we keep parent prims that have valid children

### Fixed
- Added missing `@omni.usd.handle_exception` decorators to the interaction plugin
- Fixed bugs hidden by the missing decorators
- Fixed circular imports due to absolute import paths

## [1.6.1]
### Added
- Added auto scroll to selection functionality

## [1.6.0]
### Added
- Added the ability to left-align column titles

### Changed
- Made the background of the interaction plugin tree alternating colors
- Bubble the `_item_clicked` event in the delegate when the widgets trigger the event

## [1.5.0]
### Changed
- Refresh interaction plugin widgets on tree model item changed
- Renamed `build_result_ui` to `build_overview_ui`

## [1.4.0]
### Added
- Added the ability to deactivate interaction plugins for performance optimizations

## [1.3.0]
### Added
- Added listener plugins

### Changed
- Changed the `GENERIC` data type to `NONE`

## [1.2.0]
### Changed
- Split context plugins setup between `setup()` and `get_items()`
- Add the ability not to display filters
- Changed interactions to not have `context_filters` separate from `filters`
- Centralized compatibility check for interaction plugins
- Filter context items at the interaction-level while allowing tree models to also filter afterwards (for recursive item creation)

## [1.1.1]
### Changed
- Added the ability to set the context from the core to the interaction plugin

### Fixed
- Fixed model serialization

## [1.1.0]
### Changed
- Implemented plugin base classes

## [1.0.0]
### Added
- Created
