# lightspeed.trex.capture.core.shared

Loads capture layers and emits capture-load events for downstream systems.

Existing capture layers emit the capture-loaded event during project open even when saved perspective metadata exists,
so the capture game camera can reassert camera authority.

## Capture classification

`is_capture_file()` classifies persisted root-layer metadata through a metadata-only anonymous layer. It identifies
Remix captures without certifying that the full stage can be opened or composed.

`get_capture_files_with_thumbnails()` lists readable USD files in a capture directory, classifies them with bounded
concurrency, and returns valid captures in directory order with thumbnails resolved only for accepted files.

## Remix config

A capture stores the `rtx.*` options it was taken with on a `UsdRenderSettings` prim at `/remix_settings`, as a string
array of `key = value` entries.

Hydra gathers only namespaced attributes from a render settings prim, so the bare `remix_config` that pre-namespace
captures use never reaches HdRemix, and those captures render with default `rtx.sceneScale` and `rtx.zUp`.

Both capture-load paths republish that value as `remix:remix_config` on the session layer before emitting the
capture-loaded event. The session layer is used because it out-composes the capture and is never written to disk,
leaving both the locked capture file and the mod layer untouched.

This is a **fallback, not an override**. Any layer that states `remix:remix_config` itself is left alone: a current
capture that already namespaces its config, or a mod layer deliberately overriding the capture project-wide. Because
the capture is the weakest sublayer, such an override composes as the winner on its own. The fallback is also dropped
before every capture load, so it is never mistaken for an override and never outlives the capture it came from.
