# lightspeed.trex.utils.widget

Shared RTX Remix UI primitives for workspace windows, validation dialogs, categories, messages, quick layouts, and
on-demand IngestCraft activation.

## Responsibilities

- Provide reusable workspace widget and window base classes.
- Validate replacement-asset selections and present the corresponding file pickers and confirmation dialogs.
- Provide shared category and message dialogs used by RTX Remix features.
- Load quick-layout files asynchronously and restore their visible tab-bar settings.
- Enable the IngestCraft runtime extensions on demand and wait for native stage readiness.

## Non-Responsibilities

- Owning product workflows or feature-specific UI state.
- Opening projects or mutating replacement data after a selection is validated.
- Defining layout resources; callers resolve and pass the layout file to this extension's loader.
- Creating the IngestCraft stage or UI; its control and widget extensions own those lifecycles.

## Architecture

- `WorkspaceWidget` and `WorkspaceWindowBase` define reusable context-aware workspace lifecycles.
- `load_layout` schedules Kit's async quick-layout loader and reapplies tab-bar visibility after docking settles. The
  returned task owns file and layout errors so each caller can report them in its product context.
- `RemixCategoriesDialog` and `TrexMessageDialog` provide shared dialog components.
- `asset_validation` owns replacement file-picker validation and routes accepted selections to caller callbacks.
- `ingestcraft_loader` enables disabled runtime extensions without importing their modules eagerly and waits on the
  IngestCraft context's native stage-opened event.
