# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [4.1.0]
### Added
- Added targeted progress and external-readiness events, handler-owned Apply readiness guidance, and atomic multi-graph submission with one structural-change notification.
- Added deterministic queue ordering plus product-owned apply-handler APIs.

### Changed
- Replaced persistence plugin classes with explicit immutable codec values and a focused registry.
- Replaced the queue with typed graphs, explicit codecs, event-driven per-type scheduling, structured progress, atomic dependency handling and selected-graph deletion, crash-safe Apply/Reapply/Revert state, and a minimal package-root API; removed superseded callback, compatibility, history, dynamic-import, callable-persistence, and synchronous-execution paths.
- Made `QueueInterface` the sole submission API and centralized streamed snapshots and explicit apply policies in the shared runtime.
- Moved job queue settings, apply-handler selection, plugin registration, and lifecycle ownership into the shared core and factory flow.

### Fixed
- Made Decline restore any target covered by a failed Apply receipt before recording the output as declined.
- Hardened dependency retries, atomic dispatch, persistent production storage, interrupted-runtime recovery, event
  replay, main-thread Apply evaluation, Apply retries, and shutdown.
- Fixed executor handling, durable applied-state tracking, persisted validation, database events, and nonblocking shutdown.
- Made an explicit Apply that promotes a running reconciliation still apply. The reconciliation resolved its handler binding off the loop, so a manual-policy job returned and reported success to the caller without applying anything.

### Removed
- Removed graph-owned submission, the ambiguous registry accessor, the obsolete pending state, and unused queue-level
  Revert scheduling and state; successful effects use product-owned undo workflows.

## [1.0.1]
### Changed
- Updated extension metadata for Kit SDK 110 compatibility.

## [1.0.0] - 2025-10-14
### Added
- Init commit.

### Fixed
- Ignored non-init dataclass fields during job queue serialization.
- Closed job stdout handles if stderr log setup fails and tightened callable job parameter typing.
- Made executor finalization nonblocking and improved job wait timeout diagnostics.
- Clarified job result timeout documentation.
- Added standard logging fallbacks for scheduler status messages.
- Tightened in-memory SQLite path detection for the default process executor.
- Added cleanup for job queue event subscriber threads.
