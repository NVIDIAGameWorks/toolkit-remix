# lightspeed.trex.capture_tree.model

Reusable model and delegate classes for displaying RTX Remix captures in an `omni.ui` tree.

## Responsibilities

- Build capture-tree items from capture paths and optional thumbnail paths.
- Refresh and expose replacement progress when the caller enables progress display.
- Provide thumbnail-preview interaction and an optional callback for a left-button double-click on the exact capture item.

## Non-Responsibilities

- Does not discover capture directories or decide whether a USD is a valid RTX Remix capture; Capture Core owns discovery and classification, while the Project Wizard setup page owns request timing and presentation.
- Does not decide whether activation advances a wizard or performs capture recovery; the caller owns navigation policy.
- Does not create or modify capture, replacement, or project layers.

## Architecture

- `CaptureTreeModel` sorts capture paths into `CaptureTreeItem` instances, owns stage and layer listeners, and refreshes cached replacement progress only when `show_progress` is enabled. A progress-hidden tree never schedules progress fetching during refresh.
- `CaptureTreeDelegate` builds the thumbnail and path cells, provides the hover preview, and invokes its optional `item_double_clicked_fn` only for a left-button double-click, passing the item that received the event. Without a callback, activation is inert.
- `CaptureTreeItem` holds the capture path, optional image path, and progress values rendered by the delegate.
