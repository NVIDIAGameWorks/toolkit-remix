# lightspeed.trex.viewports.shared.widget

Provides the shared StageCraft viewport widget.

If the active viewport camera is the capture game camera, camera-mutating gestures and frame/focus actions first copy
that view to `/OmniverseKit_Persp` and switch the viewport to perspective. Plain viewport focus keeps looking through
the capture game camera, which remains read-only source data. If the copy to perspective cannot be completed, the
camera-mutating action is canceled and a warning explains that the capture game camera was kept read-only.
