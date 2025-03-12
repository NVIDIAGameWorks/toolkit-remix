# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.8.0]
### Added
- Added the ability to left-align property names

## [1.7.1]
### Changed
- Updated names after refactor of property_widget_builder

## [1.7.0]
### Changed
- Use centralized LayerTree widget

## [1.6.1]
### Changed
- Update deps

## [1.6.0] - 2024-04-02
### Changed
- Updated Field widget builder objects to adopt updates from `omni.flux.property_widget_builder.delegates-1.3.0`

## [1.5.2]
### Changed
- Set Apache 2 license headers

## [1.5.1] - 2024-02-09
### Added
- Implemented abstract method `ItemModel.get_value` used for serialization in copy/paste

## [1.5.0] - 2023-10-05
### Changed
- Use renamed `DefaultField` delegate

## [1.4.0] - 2023-06-01
### Added
- Pre and post callback during `set_value` for items

## [1.3.0] - 2022-11-01
### Changed
- Added dummy method to match USD model

## [1.2.0] - 2022-09-26
### Changed
- Use `omni.flux.property_widget_builder.delegates` to show some attribute(s) humanly readable
- `add_model_and_delegate()` renamed to `add_model()` (and it only takes a model as input)
- `remove_model_and_delegate()` renamed to `remove_model()` (and it only takes a model as input)

## [1.1.0] - 2022-08-02
### Changed
- always listen, even if the file is not modified (some attributes are not part of "modified file")

## [1.0.0] - 2022-07-08
### Added
- Init commit.
