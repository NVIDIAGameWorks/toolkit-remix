# lightspeed.trex.comfyui.core

Core ComfyUI integration for RTX Remix. It owns server communication, typed workflow models, connection state,
events, value resolution, and queue job creation. UI and Stage Manager extensions consume this API.

## Responsibilities

- Connect to an external ComfyUI server and load its RTX Remix workflow catalog and workflow data.
- Parse typed workflow inputs, outputs, presets, and value resolvers.
- Maintain per-USD-context connection/workflow state and lifecycle events while sharing persistent server endpoint
  settings; endpoint edits notify every cached context and the shared queue so readiness consumers recompute
  immediately.
- Observe visibility changes in each core's injected USD context and publish that context through the shared ComfyUI
  event stream.
- Resolve selected USD data into one typed generation-processing graph per unique material, binding the resolved
  workflow request through the generation job's declared input port for product review and queue submission.
- Require a live stage only while preparing a new graph, capture its current root and edit-layer identities without
  saving, then let persisted ComfyUI generation and texture-processing jobs finish without an interactive project.
- Own durable queue submission, saved-workflow resolution, and queued ComfyUI server retargeting behind context-bound
  operations so product widgets only render confirmation and result state.
- Download declared workflow outputs into queue-owned artifact directories.
- Produce `TextureProcessingRequest` values for the shared `TextureProcessingJob` and register the reversible USD-only
  ComfyUI Apply handler used by that child.

## Non-Responsibilities

- Does not render ComfyUI setup, workflow, or queue UI. `lightspeed.trex.comfyui.widget` and Stage Manager integrations
  own those surfaces.
- Does not persist or execute the shared queue. `omni.flux.job_queue.core` owns queue storage, scheduling, and workers.
- Does not define asset-pipeline steps or USD replacement primitives. `lightspeed.trex.asset_pipeline.core` owns the
  reusable processing pipeline, and `lightspeed.trex.texture_replacements.core.shared` owns USD mutation.
- Does not install, launch, or stop a managed ComfyUI process. Only external-server setup is currently enabled.

## Architecture

```text
Product UI / Stage Manager
        |
        v
+--------------------------+
| ComfyUICore              |
| one per explicit context |
+--------------------------+
   | shared events| material JobGraph
   v              v
+-------------+  +------------------+     +----------------------+
| Events Mgr  |  | ComfyUIJob       |---->| TextureProcessingJob |
+-------------+  +------------------+     +----------------------+
                         |                          |
                         v                          v
                    +------------+          ComfyUI Apply handler
                    | ComfyUIAPI |
                    +------------+
```

### Key Classes

- `ComfyUICore` owns one context-bound connection, workflow selection, input resolution, and job preparation.
- `ComfyUIAPI` is the bounded HTTP client for server health, workflows, uploads, prompts, history, and downloads.
- `Workflow`, `WorkflowInput`, `WorkflowOutput`, and `Preset` define the typed workflow contract.
- `ComfyUIWorkflowRequest` carries the resolved prompt, upload bindings, output contract, and processing destination
  through `ComfyUIJob.WORKFLOW_REQUEST`.
- `ComfyUIJob.execute()` submits the prompt, downloads raw queue artifacts, and outputs a
  `TextureProcessingRequest`; it has no Apply binding or texture-processing ownership.
- `TextureProcessingJob` consumes that request, runs the reusable Remix asset pipeline, publishes the complete batch,
  and outputs `TextureProcessingResult`.
- `ComfyUIJobApplyHandler` validates the captured live USD target and applies, reapplies, or reverts the processed
  textures through the shared texture replacement core in one undo group.
- Execution, workflow models, prompt binding, and USD Apply behavior live in focused modules; consumers import the
  exact class or function from its owning module instead of relying on package or job-module re-exports.
- `lightspeed.events_manager` publishes context-qualified state, workflow, settings, and stage visibility changes to
  consumers.
- `ComfyUICoreExtension` keeps the core factory disabled until resolver, persisted-type, Apply-handler, and event
  registrations all succeed, and rolls back partial startup in reverse order.

### Design Decisions

- **Explicit context**: `get_comfyui_core_instance(context_name)` lazily creates one core per USD context. Production
  callers use this factory so process-wide endpoint edits reach every cached context; direct `ComfyUICore` construction
  is reserved for isolated tests.
- **Event-driven state**: Widgets and Stage Manager subscribe to the shared `lightspeed.events_manager` event using
  context-qualified helpers for state, workflow, and endpoint-setting changes. Verified endpoint changes notify every
  cached context and wake the shared queue scheduler and visible queue UI without polling. Workflow and settings
  setters commit before notifying observers.
- **External setup**: Connection settings describe an external ComfyUI server.
- **Connection diagnosis**: The current failed connection retains its exact technical error until the state changes so
  the setup UI can show useful details without searching general Toolkit logs.
- **Latest operation wins**: Connection, workflow discovery, and workflow loading capture their endpoint and generation.
  Stale pre-publication results emit nothing; endpoint changes during publication restore the prior workflow list.
  Successful connections and server-loaded workflows retain separate endpoint provenance. Editing any endpoint setting
  clears the verified connection, workflow catalog, and active workflow for every cached USD context. `is_connected`
  and `is_ready` reject a stale endpoint address, preparation rechecks it before returning the graph, and queued jobs
  persist and enforce that endpoint.
- **Direct job creation**: `ComfyUICore` captures workflow, context, project, edit target, prims, and inputs without a
  separate generator object. The live stage is required at this capture boundary only; submitted execution consumes
  persisted files and values.
- **Exact Apply target**: Apply, Reapply, and Revert compare the currently open root and edit-layer identifiers with the
  values captured at submission. A different project is never modified; pending automatic work resumes when the exact
  project is reopened.
- **Exact active preset**: Only the workflow metadata's exact `activePreset` name is applied. Missing or unknown names
  preserve the workflow defaults. Applying a preset resets every input to its workflow default before applying
  overrides; an explicit preset value updates the default typed Constant or selects the canonical Constant when a
  semantic getter was active.
- **Review before submit**: `prepare_submission()` returns immutable prepared graphs plus confirmation counts, and
  `submit_prepared_submission()` independently submits every accepted graph through the shared queue. Product UI does
  not resolve inputs or mutate durable queue state. Cancellation waits for the active graph transaction to settle
  before propagating. Committed graphs remain queued, while remaining graphs are not submitted.
- **Typed two-stage graph**: Every graph binds one `ComfyUIWorkflowRequest` to `ComfyUIJob.WORKFLOW_REQUEST`, then
  connects `ComfyUIJob.GENERATED_TEXTURES` to `TextureProcessingJob.SOURCE_TEXTURES`. Only the texture-processing child owns the exact
  `ComfyUIJobApplyHandler` binding.
- **Single-flight preparation and submission**: Concurrent ownership fails with an actionable busy error instead of
  being silently dropped.
- **Durable inputs and results**: Generation localizes inputs and downloads declared outputs into the queue's job
  directory. The texture-processing child runs the shared asset pipeline and publishes every output as one keyed batch.
  Saved projects use their ingested-assets directory; anonymous stages retain processed outputs in the durable queue
  job directory.
- **Dependency-derived skips**: A missing material input skips only the generation producer; the generic queue derives
  the dependent texture-processing skip from the typed edge.
- **Context-safe reversible Apply**: Apply revalidates the project and edit target, correlates processed textures by their
  stable keys, accepts the pipeline's OpenGL/DirectX-to-octahedral normal conversion while requiring every other final
  semantic to remain exact, preserves pre-first-Apply target-layer opinions across Reapply,
  rejects external edits, and restores the originals through the canonical replacement API on Revert. Revert verifies
  one exact target-layer snapshot against its durable applied-value receipt, then forwards that unchanged snapshot as
  the shared force baseline for mutation-boundary rechecks.
