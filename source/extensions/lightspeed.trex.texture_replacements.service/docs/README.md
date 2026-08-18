# lightspeed.trex.texture_replacements.service

Exposes texture discovery and replacement operations over the service API.

Forced replacement requests must include `expected_current_textures` with one unique entry for every replacement
target. The request succeeds only when those values exactly match the current edit-layer opinions; stale requests return
HTTP 422 without modifying the layer.
