# lightspeed.trex.utils.common

Provides shared utility helpers for StageCraft extensions.

## Camera Authority

Capture game-camera helpers keep `/RootNode/cameras/Camera` and legacy `/RootNode/Camera` as read-only capture data.
Use these helpers to copy capture camera data to `/OmniverseKit_Persp`, clear stronger game-camera opinions, and redirect
navigation/editing to the perspective camera. The perspective copy also authors `omni:kit:centerOfInterest` so Kit's
camera manipulator can initialize zoom/pan gestures immediately after the redirect.
Camera-mutating callers can use the editable-camera guard to cancel the action with a warning if the redirect cannot be
completed, keeping the capture game camera read-only.

The pseudo-orthographic helpers configure `/OmniverseKit_Front`, `/OmniverseKit_Top`, and `/OmniverseKit_Right` as
session-layer perspective cameras aimed at capture geometry. They preserve the familiar inspection-camera paths while
using a narrow field of view that Remix can render, and provide a lock helper to restore each camera's axis orientation
after viewport gestures.
