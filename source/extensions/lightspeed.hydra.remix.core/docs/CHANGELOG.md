# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.8.2]
### Fixed
- Returned actionable Toolkit guidance when HdRemix reports an incompatible NVIDIA graphics driver.

## [0.8.1]
### Fixed
- Disabled legacy HdRemix selection highlighting to avoid performance degradation on USD 25+.

## [0.8.0]
### Changed
- Simplified HdRemix bootstrap path registration and unsupported-state reporting.
- Updated extension metadata for Kit SDK 110 compatibility.

### Fixed
- Hardened Kit 110 HdRemix bootstrap by registering HdRemix and particle DLL paths, explicitly registering the USD plugin directory, deferring bounded support polling until a viewport requests it, and keeping shutdown tolerant when startup exits before DLL path tokens exist.
- Reported definitive HdRemix bootstrap failures through the Remix support state so the viewport can present the existing failure dialog instead of waiting for a timeout.
- Reset the cached HdRemix DLL handle when the extension shuts down.

## [0.7.2]
### Changed
- Modernize python style and enable more ruff checks

## [0.7.1]
### Changed
- Switched to ruff for linting and formatting

## [0.7.0]
## Fixed
- Refactored hdremix loading to be resilient to test race conditions

## Changed
- Cleaned up code and added typing

## [0.6.1]
## Fixed
- Fixed Test assets to large to work without LFS

## [0.6.0]
## Added
- Added missing automodule directives for documentation

## [0.5.3]
## Changed
- Update variables and resource locations for extension testing matrix (ETM) compliance

## [0.5.2]
## Fixed
- Cleaned up loading logic and logging

## [0.5.1]
### Added
- Specified path to NRC dependencies

## [0.5.0]
### Changed
- Update hdremix with new remixsdk

## [0.4.1]
### Added
- Texture file hot-reload on HdRemix side: recreate an HdRemix material when WinAPI detects a file change

## [0.4.0]
### Changed
- Disable HDRemix bootstrap

## [0.3.6]
### Fixed
- Fix USD export / import of distant lights in dxvk-remix: -Z now correctly points sun -> earth

## [0.3.5]
### Changed
- Changed repo link

## [0.3.4]
### Added
- A function to set Remix Renderer variables directly

## [0.3.3]
### Fixed
- Fix license headers

## [0.3.2]
### Changed
- Update to Kit 106

## [0.3.1]
### Changed
- Set Apache 2 license headers

## [0.3.0] - 2024-03-22
### Added
- A class to wrap C functions from HdRemix.dll.
- A set of exported module functions to access HdRemix-specific functionality, like object picking.
### Changed
- Extension file structure to be coherent with OV extension naming and Python modules.

## [0.2.1] - 2024-02-20
### Changed
- HdRemix to a newer version, so it chooses the same GPU as the Hydra Engine uses.
- Remix support request from blocking to non-blocking.

## [0.2.0] - 2024-01-26
### Changed
- Remix initialization sequence to async via a HdRemix bootstrap.
### Added
- 'is_remix_supported' function to request support of Remix renderer, and a reason if it has failed.

## [0.1.1] - 2023-14-12
### Changed
- RTX IO to be forcibly disabled when using HdRemix.

## [0.1.0] - 2023-10-12
### Added
- Created.
