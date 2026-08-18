# lightspeed.trex.utils.widget

Shared RTX Remix UI primitives for workspace windows, validation dialogs, categories, messages, and quick layouts.

## Responsibilities

- Provide reusable workspace widget and window base classes.
- Validate replacement-asset selections and present the corresponding file pickers and confirmation dialogs.
- Provide shared category and message dialogs used by RTX Remix features.
- Load quick-layout files asynchronously and restore their visible tab-bar settings.

## Non-Responsibilities

- Owning product workflows or feature-specific UI state.
- Opening projects or mutating replacement data after a selection is validated.
- Defining layout resources; callers resolve and pass the layout file to this extension's loader.

## Architecture

- `WorkspaceWidget` and `WorkspaceWindowBase` define reusable context-aware workspace lifecycles.
- `load_layout` schedules Kit's async quick-layout loader and reapplies tab-bar visibility after docking settles. The
  returned task owns file and layout errors so each caller can report them in its product context.
- `RemixCategoriesDialog` and `TrexMessageDialog` provide shared dialog components.
- `asset_validation` owns replacement file-picker validation and routes accepted selections to caller callbacks.
