# lightspeed.trex.viewports.manipulators

Provides viewport manipulators for StageCraft viewports, including camera gesture wrapping. Camera gestures keep
pseudo-orthographic perspective inspection cameras locked to their Front, Top, or Right axis while allowing position
updates during navigation. Those inspection cameras disable perspective tumble/look gestures and keep pan/zoom enabled
so they navigate like orthographic views while still rendering through perspective cameras.

Camera pointer drags use native cursor capture for continuous navigation beyond screen edges. When a drag completes,
the manipulator restores the cursor mode that was active before the drag. If reading the initial cursor mode fails,
the gesture ends its notice interaction without attempting to change the cursor mode.
Repeated capture requests before cleanup preserve the originally saved cursor mode.
