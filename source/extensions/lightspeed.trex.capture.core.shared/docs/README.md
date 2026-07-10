# lightspeed.trex.capture.core.shared

Loads capture layers and emits capture-load events for downstream systems.

Existing capture layers emit the capture-loaded event during project open even when saved perspective metadata exists,
so the capture game camera can reassert camera authority.
