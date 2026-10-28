# lightspeed.trex.layout.shared.mass_ingestion

Hosts the mass-ingestion workspace, its validation and stage-view panels, and its embedded viewport preview.

## Responsibilities

- Connect ingestion queue actions to the validation, stage-view, and preview panels.
- Forward window and preview-panel visibility to the embedded viewport.
- Suspend preview updates during ingestion and resume only when every running core has finished and the preview is visible.
  Core start and finish events remain tracked while the window is hidden.

## Non-Responsibilities

- Ingestion execution and queue management belong to the validator extensions.
- Renderer initialization, cancellation, and rendering belong to `lightspeed.trex.viewports.shared.widget`.

## Architecture

`SetupUI` implements the workspace widget interface and owns the panel layout. It subscribes to ingestion core lifecycle
events and combines running-core state with window and panel visibility before showing the shared viewport. Hiding the
window or starting ingestion cancels pending viewport initialization; showing an idle preview allows initialization
to resume.
