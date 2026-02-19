# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.2.0]
### Added
- Added `ogn_read_metadata_key()` public utility for reading and converting a single OGN metadata key to a USD-compatible Python type
- Added shared `_ogn_value_to_python_type()` helper for JSON-to-USD type conversion of OGN metadata strings
- Added unit test suite for `get_ogn_default_value()` in `tests/unit/test_attributes.py`

### Changed
- Refactored `get_ogn_default_value()` to use shared `_ogn_value_to_python_type()` for JSON-to-USD type conversion
- Exported `ogn_read_metadata_key` from package `__all__`

## [1.1.1]
### Changed
- Modernize python style and enable more ruff checks

## [1.1.0]
### Added
- Added `get_ogn_default_value()` utility for retrieving OGN attribute defaults as USD types

### Fixed
- Fixed duplicate graph entries when multiple paths contain the same graph

## [1.0.0]
### Added
- Created extension for managing logic graphs
- Added LogicGraphCore class with basic functionality
