# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.1.0]
### Changed
- Extract `.layer_id` from path-param model instances in `remove_layer`, `move_layer`, `lock_layer`, `mute_layer`, `save_layer`, and `set_edit_target` endpoints; `validate_path_param` returns a model instance, not a plain string
- Update all `LayerManagerCore` call sites to use renamed API: `remove_layer`, `move_layer`, `lock_layer`, `mute_layer`, `save_layer`, `set_edit_target`
- Inline data-model unpacking logic for `create_layer`, `remove_layer`, `move_layer`, `lock_layer`, `mute_layer`, `save_layer`, `get_edit_target_layer`, and `set_edit_target_layer` endpoints directly in the service; remove dependency on `*_with_data_model()` delegation wrappers in `LayerManagerCore`
- Update `set_edit_target_layer` to call the renamed `set_edit_target_layer_with_identifier()` method
- Call `LayerManagerCore.get_sublayers_with_data_models()` directly as a static method

## [2.0.3]
### Changed
- Modernize python style and enable more ruff checks

## [2.0.2]
### Changed
- Switched to ruff for linting and formatting

## [2.0.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [2.0.0]
## Changed
- Updated Pydantic to V2

## [1.2.2]
## Changed
- Updated test to use `deps` instead of `.deps` dir

## [1.2.1]
### Added
- Added tests for all the endpoints in the layer manager service

## [1.2.0]
### Changed
- Use generic factory instead of service-specific factory

## [1.1.0]
### Added
- Added endpoint to get layer types

## [1.0.0] - 2023-10-27
### Added
- Created
