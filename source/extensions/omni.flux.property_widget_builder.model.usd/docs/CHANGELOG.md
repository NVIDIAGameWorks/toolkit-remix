# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.18.1]
### Fixed
- Changed to using a ImageWithProvider to better display single channel textures

## [2.18.0]
## Added
- Added the ability to left-align property names

## [2.17.1]
## Fixed
- Virtual attr should display default until they are set

## [2.17.0]
### Added
- Add support for non-xform stub attributes
- Added slider widget for material attribute subsurface_radius_scale

## [2.16.0]
## Changed
- Update to Kit 106.5
- property widget tree: support virtual attribute items
- simplified and refactored property tree items and value models

## [2.15.0]
### Added
- Added slider widget for material attribute displace_out

## [2.14.0]
### Added
- Added support for multi-edit and displaying "mixed" values

### Changed
- Refactored value model classes to clarify and share more code

## [2.13.1]
### Fixed
- Fixed material property builder string field tooltip and copy menus

## [2.13.0]
### Added
- Added identifier for UI elements

## [2.12.0]
### Changed
- Use centralized LayerTree widget

## [2.11.7] - 2024-07-12
### Added
- Full file path hover tooltip for material string field properties
- Copy file path menu for material string field properties

### Fixed
- Now the fallback texture preview window title doesn't break when there are multiple assets selected

## [2.11.6] - 2024-06-26
### Fixed
- Texture preview windows sharing the same UI instance

## [2.11.5]
### Fixed
- Fixed issue resetting color widget to default value

## [2.11.4]
### Changed
- Updated default values for material attribute displace_in

## [2.11.3]
### Changed
- Use updated `SUPPORTED_TEXTURE_EXTENSIONS`

## [2.11.2]
### Changed
- Update deps

## [2.11.1] - 2024-04-12
### Fixed
- Fix property editor crash for unknowns widget builders

## [2.11.0] - 2024-04-02
### Added
- Rework how all the per-item UI building works with new `FieldBuilder` system
- Implemented a USD specific `FieldBuilderRegistry` to simplify registering `FieldBuilder` for `USDItem`
- Added `USDFloatSliderField` which can adjust min/max range of slider using USD metadata
### Changed
- Updated Field widget builder objects to adopt updates from `omni.flux.property_widget_builder.delegates-1.3.0`
- Updated many float attributes to use sliders

## [2.10.5]
### Changed
- Set Apache 2 license headers

## [2.10.4] - 2024-03-25
### Changed
- Update color types to use a single value model to hold the Gf.Vec* value
- Add clipboard serializer for Gf.Vec* types

## [2.10.3] - 2024-02-21
### Fixed
- Reverted a change which made file texture widgets update before editing was complete

## [2.10.2] - 2024-02-09
### Changed
- Renamed Delegate `set_selected_items` to `selected_items_changed`
- Implemented abstract method `ItemModel.get_value` used for serialization in copy/paste
- Added serializer hooks to handle serialization of `Sdf.AssetPath`

## [2.10.1] - 2024-01-19
### Changed
- Keep widget focus when editing a value
- Modify how "virtual" attributes are presented

## [2.10.0] - 2024-01-13
### Changed
- Allow setting asset path items' `file_extension_options` property

## [2.9.3] - 2023-12-01
### Fixed
- Fixed a bug when previewing single channel textures

## [2.9.2] - 2023-11-15
### Fixed
- "reset_default_value" should always set a value and ignore `block_set_value`

## [2.9.1] - 2023-11-14
### Fixed
- Fix undo that was still "open" when the delegate was refreshing

## [2.9.0] - 2023-10-26
### Added
- Added `display_attr_names_tooltip`

## [2.8.0] - 2023-10-05
### Changed
- Use renamed `DefaultField` delegate

## [2.7.0] - 2023-09-05
### Changed
- Don't allow deleting overrides on locked layers

## [2.6.2] - 2023-08-02
### Fixed
- Optimization

## [2.6.1] - 2023-07-24
### Fixed
- Check for a valid stage before using it

## [2.6.0] - 2023-06-01
### Added
- Pre and post callback during `set_value` for items
- Expose `utils` module

### Changed
- centralize the default `build_branch()` creation in the delegate
- `file_texture_picker` delegate set the texture only at the end of the field edit

## [2.5.2] - 2023-05-10
### Fixed
- Fix for 105

## [2.5.1] - 2023-05-02
### Changed
- Close button on the texture preview window

## [2.5.0] - 2023-03-13
### Changed
- The property tree will only update the delegates after the values stop changing for 0.25s. This greatly reduces the number of UI update calls and makes the UI a lot smoother.

### Fixed
- Fixed nullref exception on destroy

## [2.4.2] - 2023-03-10
### Fixed
- Fixed xform attribute undo grouping
- Fixed xform attribute refreshing when ending edit with default value

## [2.4.1] - 2023-01-13
### Fixed
- Fixed material target layer for undo (new SDK)

## [2.4.0] - 2022-12-05
### Added
- Added the ability for Virtual Attributes to be created

## [2.3.5] - 2023-01-10
### Fixed
- Remove fixed material target layer for undo (because Kit team said it was merged, but it wasn't)

## [2.3.4] - 2023-01-09
### Fixed
- Fixed material target layer for undo

## [2.3.3] - 2022-11-28
### Changed
- Added a callback for layer events in the base widget

## [2.3.2] - 2022-11-22
### Fixed
- Fix the default value for scale

## [2.3.1] - 2022-11-04
### Fixed
- Fix empty paths for textures

## [2.3.0] - 2022-11-02
### Changed
- Added layer override indicators

## [2.2.1] - 2022-11-02
### Fixed
- Added missing extension dependency

## [2.2.0] - 2022-10-28
### Fixed
- Hierarchy attribute items didn't call `supress_usd_events_during_widget_edit`

## [2.1.0] - 2022-10-07
### Changed
- Improved texture picker delegate to preview the images + show file attributes

## [2.0.0] - 2022-09-19
### Changed
- Use context name
- Use `omni.flux.property_widget_builder.delegates`
- `add_model_and_delegate()` renamed to `add_model()` (and it only takes a model as input)
- `remove_model_and_delegate()` renamed to `remove_model()` (and it only takes a model as input)
- `USDAttributeItem` takes the context name as input (not the stage anymore)

### Added
- `set_display_attr_names()` to `USDAttributeItem`
- `USDMetadataListItem` to be able to set USD metadata of an attribute
- `USDAttrListItem` to be able to set USD attribute with multiple value choice (like enums)
- `USDDelegate` uses some delegates from `omni.flux.property_widget_builder.delegates`
- `UsdListModelBaseValueModel` to read and set a metedata of an USD attribute
- `UsdListModelAttrValueModel` to read the value of an attribute with multiple value choice (like enums)
- `FileTexturePicker` delegate derived from `omni.flux.property_widget_builder.delegates`, to show texture paths of USD attributes
- `Combobox` delegate derived from `omni.flux.property_widget_builder.delegates`, to show multiple value choice (like enums) of USD attributes

## [1.0.0] - 2022-07-08
### Added
- Init commit.
