# lightspeed.trex.ingestcraft.widget

Hosts the IngestCraft workspace. In a standalone IngestCraft application it registers the Ingestion sidebar item;
when StageCraft control is enabled, StageCraft owns that item to prevent duplicate navigation.

## Responsibilities

- Build and manage the IngestCraft workspace window and ingestion UI.
- Register standalone IngestCraft navigation when StageCraft does not own the shared sidebar.

## Non-Responsibilities

- Does not create the IngestCraft USD stage; `lightspeed.trex.control.ingestcraft` owns stage lifecycle.
- Does not enable IngestCraft on demand; `lightspeed.trex.utils.widget` owns extension activation.

## Architecture

`TrexIngestCraftWindowExtension` owns an `IngestCraftWindow`, which creates `SetupUI` when visible. The window checks
the extension manager before registering its sidebar item so combined applications have one navigation owner.
