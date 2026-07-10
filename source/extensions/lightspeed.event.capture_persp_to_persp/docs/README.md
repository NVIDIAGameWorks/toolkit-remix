# lightspeed.event.capture_persp_to_persp

Copies the active capture layer's game camera to `/OmniverseKit_Persp` when a capture loads.

The capture game camera is the source of truth. On capture-load events, this extension clears authored game-camera
opinions outside the capture layer before copying the capture-authored camera to the disposable perspective camera.
It also configures Kit's Front, Top, and Right inspection cameras as session-only perspective cameras, then frames each
successfully configured inspection camera to `/RootNode/meshes` and `/RootNode/instances` so their default views center
on the active capture geometry while rendering through Remix's perspective camera path.
