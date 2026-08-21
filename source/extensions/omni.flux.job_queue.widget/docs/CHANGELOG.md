# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [3.2.2]
### Fixed
- Fixed the Job Queue and Job Details windows showing no jobs: the queue widget and the job details panel now report their `destroyed` state, which an owning workspace window reads before it shows or cleans up its content.

## [3.2.1]
### Added
- Added queue-owned subscriptions for product adapter action events and targeted model refreshes.
- Added handler-provided Apply guidance, targeted readiness refreshes, a Stopping state that names active graphs, and Delete-key removal for selected graphs.
- Added compact collapsible job details with section-owned actions, severity-aware logs, expandable two-column typed-value trees, declared port-type diagnostics, responsive native middle-elision, and filtered graph reordering that preserves hidden queue order.
- Added an event-driven hierarchical graph/job queue with child-aware filters, collapsible structured details and logs, responsive long-name headers, section-owned detail actions, standard label sizing with monospace input/output values, exclusive state summaries, completion times, explicit Apply controls, deterministic bulk actions and selected-root deletion, exact-type product adapters, and native empty-tree behavior; removed the flat, widget-scheduled callback-era UI.
- Added queue filtering, drag-and-drop ordering, and display adapter hooks for product-owned queue integrations.

### Changed
- Updated queue states, filtering, and Apply controls for streamed snapshots and explicit handler policies.
- Redesigned the queue UI around Flux tree infrastructure, shared core settings, a details workspace panel, factory-backed adapter registration, and standard Kit prompts.

### Fixed
- Coalesced worker events into targeted visible-row updates, kept queue chrome and empty-state rendering stable, and allowed active job details to render before progress counts exist.
- Fixed queue status display, database event subscriptions, and runtime resource cleanup.
- Retained the job details typed-value trees so their native rows keep rendering, and refreshed the details panel when a details link reveals a child.

## [1.0.1]
### Changed
- Updated extension metadata for Kit SDK 110 compatibility.

## [1.0.0] - 2025-10-20
### Added
- Init commit.

### Fixed
- Opened job folders on Linux and macOS without raising `NotImplementedError`.
- Added explicit queue widget cleanup for event subscribers, schedulers, and owned executors.
