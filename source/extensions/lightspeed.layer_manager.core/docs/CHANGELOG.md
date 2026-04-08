# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [3.2.1]
### Fixed
- REMIX-5242: Fix `open_stage()` regression introduced in 3.2.0 — use `ensure_future(open_stage_async())` to avoid blocking the UI thread during stage open

## [3.2.0]
### Changed
- `create_layer()` now returns the newly created `Sdf.Layer` instance (previously returned `None` implicitly)
- Add `omni.flux.commands` as a runtime dependency; required for `CreateOrInsertSublayer` command used in `create_layer()`
- Rename identifier-based methods to shorter forms: `set_edit_target_layer_with_identifier` → `set_edit_target`, `move_layer_with_identifier` → `move_layer`, `remove_layer_with_identifier` → `remove_layer`, `mute_layer_with_identifier` → `mute_layer`, `lock_layer_with_identifier` → `lock_layer`, `save_layer_with_identifier` → `save_layer`
- Rename type-based bulk methods to disambiguate from identifier methods: `save_layer` → `save_layer_of_type`, `set_edit_target_layer` → `set_edit_target_layer_of_type`, `lock_layer` → `lock_layers_of_type`, `mute_layer` → `mute_layers_of_type`, `remove_layer` → `remove_layers_of_type`
- Add `_get_layer_or_raise()` internal helper; use it in `get_loaded_project_with_data_models()`
- Remove dead `game_current_game_capture_folder()` method and its test
- Rename `set_edit_target_with_identifier()` → `set_edit_target_layer_with_identifier()` for API consistency
- Rename `LayerManagerValidators._iter_sublayer_tree()` → `iter_sublayer_tree()` (now public)
- Remove thin `*_with_data_model()` delegation wrappers (`create_layer_with_data_model`, `get_edit_target_with_data_model`, `set_edit_target_with_data_model`, `move_layer_with_data_model`, `remove_layer_with_data_model`, `mute_layer_with_data_model`, `lock_layer_with_data_model`, `save_layer_with_data_model`); logic moved to `lightspeed.layer_manager.service`
- Eliminate redundant `Sdf.Layer.FindOrOpen` call in `create_layer()` by caching the newly created layer handle
- Extracted `_iter_sublayer_tree()` static helper on `LayerManagerValidators`; eliminated two duplicate recursive layer-walk implementations
- Remove unused `omni.flux.commands` declared dependency
- Replace `six.add_metaclass` shim with `abc.ABC` (Python 3 native)
- Replace `omni.kit.window.file.open_stage()` with headless `context.open_stage()`; remove `omni.kit.window.file` dependency
- Privatise `get_sdf_layer`, `flatten_sublayers`, `set_custom_layer_type_data_with_identifier`, `layer_type_in_stack`
- Deprecate and delete `create_new_sublayer`, `insert_sublayer`, `create_new_stage` shims
- Promote `save_layer_with_identifier`, `get_sublayers_with_data_models`, and `is_valid_layer_type` to `@staticmethod`
- Fix `is_valid_layer_type` branch ordering to correctly handle `layer_type=None`
- Add unit tests for `get_sublayers_with_data_models` and `is_valid_layer_type`
- Corrected `@classmethod` to `@staticmethod` for pure-function validators in `LayerManagerValidators` and `LayerManagerCore`
- Improved and added missing docstrings across `core.py`, `validators.py`, layer type classes, and data models

## [3.1.3]
### Changed
- Applied new lint rules

## [3.1.2]
### Changed
- Modernize python style and enable more ruff checks

## [3.1.1]
### Changed
- Switched to ruff for linting and formatting

## [3.1.0]
### Added
- Added `get_all_replacement_layers` to list all replacement layers in the layer hierarchy

## [3.0.3]
### Added
- Added `close_project_with_data_models` method to close stage via context

## [3.0.2]
## Fixed
- Fixed validation when layer cannot be opened

## [3.0.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [3.0.0]
## Changed
- Updated Pydantic to V2

## [2.2.8]
### Fixed
- Changed usages of the `CreateSublayer` command for `CreateOrInsertSublayer`

## [2.2.7]
### Changed
- Update to Kit 106.5

## [2.2.6]
### Fixed
- Fixed crash for new stage unloading logic

## [2.2.5]
### Changed
- update to use omni.kit.test public api

## [2.2.4]
### Fixed
- Fixed tests flakiness

## [2.2.3]
### Added
- Added a new function for layer type validation

## [2.2.2]
### Changed
- Modified `open_stage()` and `create_new_stage()` to return non-anonymous previous root layer identifiers

## [2.2.1]
### Fixed
- Fixed hot-reload by allowing reuse of the validators

## [2.2.0]
### Added
- Added new functions `broken_layers_stack` and `remove_broken_layer`

## [2.1.0]
### Added
- Added endpoint to get layer types

### Fixed
- Fixed errors with service layer functions

## [2.0.1]
### Changed
- Don't use pydantic for typing to fix documentation

## [2.0.0] - 2023-11-16
### Changed
- Renamed the extension to `lightspeed.layer_manager.core`

### Added
- Added `with_identifier` functions equivalents for existing functions
- Added `with_data_model` functions equivalents for existing functions
- Added data models representing the various requests and responses possible
- Added validators for the data models

## [1.0.3]
### Changed
- Update to Kit 106

## [1.0.2]
### Changed
- Set Apache 2 license headers

## [1.0.1] - 2023-10-10
### Fixed
- remove layer: check is the layer is expired

## [1.0.0] - 2023-06-06
### Added
- Added `get_layers` to allow getting multiple layers of a given type

## [0.1.1] - 2022-06-09
### Fixed
- fixed `_reset_default_attrs`

## [0.1.0] - 2021-11-17
### Added
- First commit
