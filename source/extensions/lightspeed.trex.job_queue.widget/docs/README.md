# lightspeed.trex.job_queue.widget

Lightspeed workspace extension that exposes `omni.flux.job_queue.widget` through RTX Remix workspace windows.

## Responsibilities

- Register the RTX Remix job queue and job details workspace windows.
- Wire the Flux `QueueWidget` to the shared queue and `ApplyExecutor`.
- Register generic presentation for the reusable `TextureProcessingJob`; product-specific producer details remain in
  their owning extensions.

## Non-Responsibilities

- Persisting jobs, results, callback events, or execution state.
- Rendering the generic queue tree, toolbar, filters, or details panel internals.
- Owning product-specific Apply handlers or producer display adapters.
- Loading application layouts.

## Architecture

- **`JobQueueWorkspace`** creates the docked queue workspace, builds `QueueWidget`, and passes the Stagecraft
  `context_name` into the shared Flux UI.
- **`JobDetailsWindow`** embeds the Flux details panel and receives the queue model after the queue workspace creates it.
- **`TextureProcessingDisplayAdapter`** describes shared processing, publication, and Apply lifecycle states. It derives
  an exact local input directory for Inputs and a processed-texture directory for the product section placed after
  Outputs. Each section opens only the directory it represents, without importing any producer product or promoting
  file actions to the graph row.
- **Apply routing** uses the single runtime owned by `omni.flux.job_queue.core.handlers`; product extensions register
  exact handler classes for concrete jobs.
