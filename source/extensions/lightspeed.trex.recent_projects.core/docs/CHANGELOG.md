# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.1.4]
### Changed
- Use `is_layer_from_capture` path-based detection in `get_path_detail` to identify and skip opening capture sublayers

## [1.1.3]
### Changed
- Hardened file validation: added `UsdFileSignature` enum for magic-byte checks, per-sublayer path resolution and validation in `get_path_detail`, `OSError` guards in `save_recent_file`, backup-on-corrupt logic in `get_recent_file_data`, and a unified `_validate_usd_layer` helper

## [1.1.2]
### Changed
- Modernize python style and enable more ruff checks

## [1.1.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [1.1.0]
## Changed
- Update the documentation for Pydantic V2 compatbility

## [1.0.0]
### Added
- Init commit
