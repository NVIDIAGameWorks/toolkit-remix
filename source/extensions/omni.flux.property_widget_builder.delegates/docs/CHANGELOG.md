# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.8.0]
### Added
- Added `AbstractSliderField` base class with shared min/max/step handling, undo grouping (begin_edit/end_edit), and abstract `build_drag_widget()` for slider UI
- Added `IntSliderField` for integer slider widgets with configurable min, max, and step (default step: 1 for range ≤100, else max(1, int(range * 0.01)))
- Added E2E tests for AbstractSliderField, FloatSliderField, and IntSliderField

### Changed
- `FloatSliderField` now extends `AbstractSliderField`; min_value and max_value are optional (defaults 0.0 and 100.0); step is optional with computed default `(max - min) * 0.005`
- De-duplicated slider build logic between int and float sliders via shared base class

## [1.7.2]
### Changed
- Modernize python style and enable more ruff checks

## [1.7.1]
### Changed
- Switched to ruff for linting and formatting

## [1.7.0]
### Added
- Added `use_relative_paths` parameter to FilePicker to convert paths relative to USD edit target

## [1.6.2]
### Fixed
- Suppressed unnecessary file path validation error logging in FilePicker

## [1.6.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [1.6.0]
## Changed
- Update the documentation for Pydantic V2 compatbility

## [1.5.0]
## Added
- Added the ability to left-align property names

## [1.4.4]
## Changed
- Update to Kit 106.5

## [1.4.3]
## Fixed
- Fixed color widget default value

## [1.4.2]
### Fixed
- Fixed tests flakiness

## [1.4.1]
### Added
- Added dynamic tooltips for displaying mixed values

## [1.4.0]
### Added
- Added identifier for UI elements

## [1.3.4]
### Changed
- Update deps

## [1.3.3]
### Changed
- Update test deps

## [1.3.2]
### Changed
- FloatSliderField now calculates step size lazily

## [1.3.1]
### Changed
- Update deps

## [1.3.0] - 2024-04-02
### Added
- Added `FloatSliderField` for creating a slider widget for items representing color Vec
- Added `NameField` to create a simple label widget
### Changed
- Removed (unused) `ui.AbstractItemDelegate` base class
- Moved unique args into init so the UI build call have the same `Callable[[Item], ui.Widget | list[ui.Widget] | None]` interface

## [1.2.2]
### Changed
- Set Apache 2 license headers

## [1.2.1] - 2024-03-25
### Fixed
- Fixed various issues with ColorField

## [1.2.0] - 2023-10-05
### Changed
- Changed `DefaultStringField` to `DefaultField`
- Make readonly widget follow the `widget_type` extra data

## [1.1.3] - 2023-06-01
### Fixed
- Fixed import

## [1.1.2] - 2022-11-03
### Fixed
- Fixed casting issues with color widget

## [1.1.1] - 2022-10-31
### Fixed
- Fix color widget (to not re-order colors)

## [1.1.0] - 2022-10-06
### Changed
- Added a multiline delegate for the property widget builder

## [1.0.0] - 2022-09-26
### Added
- Init commit.
