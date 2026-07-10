# lightspeed.trex.viewports.manipulators

Provides viewport manipulators for StageCraft viewports, including camera gesture wrapping. Camera gestures keep
pseudo-orthographic perspective inspection cameras locked to their Front, Top, or Right axis while allowing position
updates during navigation. Those inspection cameras disable perspective tumble/look gestures and keep pan/zoom enabled
so they navigate like orthographic views while still rendering through perspective cameras.
