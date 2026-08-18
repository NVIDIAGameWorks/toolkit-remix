# lightspeed.trex.stage_manager.plugin.widget.usd

USD-specific Stage Manager state and action widgets for RTX Remix capture editing and AI Tools submission.

## Responsibilities

- Register the RTX Remix USD widget plugins with the Stage Manager factory.
- Render capture, category, nickname, particle, skeleton, logic-graph, rename, focus, and delete/restore controls.
- Snapshot explicit selections, confirm skipped prepared jobs, and pass accepted submissions back to the ComfyUI core.
- Observe and cancel asynchronous ComfyUI submission and AI Tools layout tasks owned by the extension.

## Non-Responsibilities

- Building the Stage Manager tree or context-menu payloads; the Flux Stage Manager extensions own those models.
- Creating ComfyUI job graphs or executing queued jobs; the ComfyUI and job-queue core extensions own that work.
- Bridging ComfyUI state events into Stage Manager; the ComfyUI listener plugin owns event integration.

## Architecture

- `LightspeedStageManagerUSDWidgetPluginsExtension` registers all widget classes and coordinates teardown.
- `SubmitComfyUIJobActionWidgetPlugin` snapshots the explicit selection and connection readiness, then lets the
  ComfyUI core resolve candidates and create skipped jobs for missing inputs.
- `DeleteRestoreActionWidgetPlugin` applies undoable capture-reference and light-intensity edits.
- The remaining action, state, and information plugins each provide one Stage Manager column or context-menu behavior.

### ComfyUI Submission

The ComfyUI action snapshots the active USD context's selected prim paths, asks the ComfyUI core to prepare one job per
unique material, confirms any skipped jobs, and passes the accepted immutable submission back to the context-bound
core. It renders exact returned counts and never mutates the queue directly. It reports preparation or submission
failures through Toolkit notifications, and its menu opens the organized AI Tools layout.

### Delete And Restore

Deleting a capture prim removes its capture reference through undoable Kit commands so the delete can be
restored. Capture lights also author `inputs:intensity = 0` while deleted, which keeps render runtime from
evaluating stale light attributes after the reference is cleared.

Restoring a capture light uses the same reference restore path as other capture prims, then removes only the
delete-authored `inputs:intensity` override from replacement layers so the light resolves back to the capture value.
