# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.2.2]
### Changed
- Renamed workspace labels to `AI Tools (Experimental)`
- Updated AI Tools layout loading to use the `AI_TOOLS` layout constant
- Limited artifact application to implemented texture handlers so mesh outputs are logged as unsupported instead of raising

### Fixed
- Fixed combo box callbacks firing during workflow loading, which could replace user-modified workflows and discard LazyValue field overrides
- Fixed ComfyUI WebSocket cleanup and bounded the handshake read to avoid leaked sockets or indefinite reads on connection errors
- Replaced Comfy job runtime validation asserts with explicit `ValueError` checks
- Corrected the Comfy output iterator return type annotation
- Hardened ComfyUI connection checks, WebSocket frame handling, URL parsing, and upload return typing
- Simplified Comfy output type annotations and destroy AI Tools queue resources during widget cleanup
- Restored base Comfy job validation and guarded submission when no workflow is selected
- Cleaned up AI Tools workspace subscriptions during workspace cleanup
- Corrected lazy field widget return typing and declared missing runtime dependencies
- Added explicit cleanup for AI Tools field and submitter widgets and guarded related prim traversal against cycles
- Preserved multiple ComfyUI outputs per node and simplified upload handling
- Added support for fragmented ComfyUI WebSocket text messages
- Propagated ComfyUI execution failures and tightened workflow/lazy field typing
- Moved AI Tools apply handler registration into extension startup and logged unexpected ComfyUI WebSocket messages

## [1.2.1]
### Added
- Added "Open in Browser" icon button to the ComfyUI URL bar for quick access to the ComfyUI web interface

## [1.2.0]
### Added
- Added `ConnectionState` enum export for UI state management
- Added `ComfyEventType` for Stage Manager listener integration
- Added connection and workflow state change event subscriptions

## [1.1.1]
### Fixed
- Fixed issue with websocket lifecycle

## [1.1.0]
### Added
- Added singleton `get_comfy_interface()` for shared ComfyUI access
- Added `get_job_queue_interface()` export for external job submission
- Added workflow property to ComfyInterface for external access


## [1.0.0]
### Added
- Initial commit
