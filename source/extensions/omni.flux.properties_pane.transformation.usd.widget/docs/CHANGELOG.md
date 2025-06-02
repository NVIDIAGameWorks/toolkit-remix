# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.8.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [2.8.0]
## Changed
- Update the documentation for Pydantic V2 compatbility

## [2.7.0]
### Added
- Added the ability to resize columns
- Added the ability to set column widths
- Added the ability to left-align property names

## [2.6.2]
### Added
- Add support for editing multiple prims at once

## [2.6.1]
### Changed
- Update deps

## [2.6.0] - 2024-04-02
### Changed
- Add a way to customize widgets per-property

## [2.5.2]
### Changed
- Set Apache 2 license headers

## [2.5.1] - 2024-01-19
### Changed
- Keep widget focus when editing a value
- Modify how "virtual" attributes are presented

## [2.5.0] - 2023-06-01
### Added
- Return the property model

### Changed
- Don't re-create the widget/model/delegate during refresh

## [2.4.0] - 2022-12-05
### Added
- Added the ability for Virtual Attributes to be created

## [2.3.1] - 2022-11-28
### Changed
- Refresh on layer event

## [2.3.0] - 2022-11-04
### Fixed
- Multiple transform op on one prim

### Added
- visibility property for the panel

## [2.2.0] - 2022-11-01
### Changed
- Added layer override indicators

## [2.0.1] - 2022-10-31
### Changed
- Change the root frame height to 0 by default

## [2.0.0] - 2022-07-08
### Changed
- Use `omni.flux.property_widget_builder.widget` v2
- Use context name
- remove "TRANSFORMATION" panel section. Let the user create it.

## [1.1.1] - 2022-06-20
### Changed
- Updated to use widget_builder 1.1.0

## [1.0.1] - 2022-06-13
### Changed
- destroy() implementations now use reset_default_attrs helper

## [1.0.0] - 2022-04-19
### Added
- Init commit.
