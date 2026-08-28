# lightspeed.trex.control.ingestcraft

Creates one IngestCraft USD stage for standalone and on-demand startup.

## Responsibilities

- Create one IngestCraft USD stage for standalone and on-demand startup.
- Publish the supported USD stage-opened lifecycle event for callers waiting to open the IngestCraft layout.

## Non-Responsibilities

- Does not enable the IngestCraft extension set or switch layouts; `lightspeed.trex.utils.widget` owns that loader.
- Does not build the IngestCraft UI; `lightspeed.trex.ingestcraft.widget` owns the workspace.

## Architecture

`TrexStageCraftControlExtension` owns a `Setup` instance. `Setup` creates one stage through the context callback and
reports creation failures. The context's native `StageEventType.OPENED` event is the readiness boundary.
