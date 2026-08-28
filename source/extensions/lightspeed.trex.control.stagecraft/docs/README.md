# lightspeed.trex.control.stagecraft

Controls the StageCraft USD context, workspace lifecycle, and StageCraft-owned navigation.

## Responsibilities

- Create and manage the StageCraft USD stage and its application event subscriptions.
- Validate project-open requests, present repair guidance, and transition valid or repaired projects to the workspace.
- Register the always-enabled Ingestion sidebar action separately from project-dependent StageCraft navigation.
- Open IngestCraft after on-demand activation completes, coalescing repeated requests and reporting activation timeouts.

## Non-Responsibilities

- Does not create the IngestCraft stage or UI; the IngestCraft control and widget extensions own them.
- Does not implement extension activation; it calls the loader in `lightspeed.trex.utils.widget`.
- Does not own Home card visibility, validity, or missing-path guards; `lightspeed.trex.home.widget` owns them.

## Architecture

`TrexStageCraftControlExtension` owns a `Setup` instance. `Setup` manages the StageCraft stage, event subscriptions,
and sidebar actions. The Modding and Ingestion actions use separate subscriptions so project state only controls
Modding. Ingestion awaits the shared IngestCraft loader before applying the IngestCraft layout. Project-open events are
fully validated once here before the unsaved-project prompt; the accepted callback opens the captured path without
revalidating it. `Setup` retains its deferred stage, layout, and IngestCraft tasks until they complete and cancels any
remaining work during teardown.
