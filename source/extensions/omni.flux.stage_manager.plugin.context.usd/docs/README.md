# omni.flux.stage_manager.plugin.context.usd

Provides Stage Manager context plugins backed by USD stages.

## Responsibilities

- Bind Stage Manager data collection to a named `omni.usd` context.
- Track stage open, close, and context-destruction lifecycle events.
- Build parent-before-child `StageManagerItem` collections from the active USD stage.
- Open a configured USD file when using `UsdFileContextPlugin`.

## Non-Responsibilities

- Creating or destroying application-owned USD contexts.
- Rendering Stage Manager widgets or applying filters and interactions.
- Owning the lifetime of USD stages supplied by another extension.

## Architecture

- `StageManagerUSDContextPlugin` assigns the context name to compatible USD listeners.
- `CurrentStageContextPlugin` caches the active stage and refreshes its binding after ordinary stage close/open events.
  When the named context itself is destroyed, it detaches its listeners and remains inactive instead of rebinding.
- `UsdFileContextPlugin` opens a configured USD file before using the current-stage lifecycle.
