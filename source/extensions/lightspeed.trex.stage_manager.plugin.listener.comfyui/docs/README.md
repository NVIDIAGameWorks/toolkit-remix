# lightspeed.trex.stage_manager.plugin.listener.comfyui

Bridges typed ComfyUI state, workflow, and shared endpoint-setting events into Stage Manager using the manager's
injected USD context.

## Responsibilities

- Register the ComfyUI listener plugin with the Stage Manager factory.
- Subscribe to context-qualified ComfyUI changes through `lightspeed.events_manager`.
- Notify Stage Manager when typed connection-state, workflow-selection, or endpoint-setting events occur.
- Release the event subscription during plugin cleanup.

## Non-Responsibilities

- Connecting to ComfyUI, selecting workflows, or creating jobs; `lightspeed.trex.comfyui.core` owns that state.
- Rendering Stage Manager actions or state widgets.
- Translating unrelated ComfyUI events into Stage Manager refreshes.

## Architecture

- `StageManagerComfyListenerPluginsExtension` registers and unregisters the plugin class with the shared factory.
- `StageManagerComfyListenerPlugin` subscribes with Stage Manager's injected context name, filters shared typed state,
  workflow, and settings events, and emits the corresponding Stage Manager listener event. Repeated setup owns
  distinct callback wrappers so cleanup of a displaced subscription cannot remove the active listener.
