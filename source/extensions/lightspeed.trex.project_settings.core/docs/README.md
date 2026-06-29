# lightspeed.trex.project_settings.core

Project-scoped USD Settings prim API for persistent toolkit settings.

Settings are stored as USD prims under `/ProjectSettings/<area>/<feature>` on the project's root layer, so they follow the project file across machines and shared installations.

## Camera clipping override

The first concrete setting exposed by this extension is the project-wide camera clipping override (REMIX-4628 / GH#912 item #1 / GH#1008):

```python
from lightspeed.trex.project_settings.core import (
    CameraClippingOverride,
    get_camera_clipping_override,
    set_camera_clipping_override,
)

# Read current state
override = get_camera_clipping_override(stage)
# override.enabled, override.near_clip, override.far_clip

# Write new state
set_camera_clipping_override(
    stage,
    CameraClippingOverride(enabled=True, near_clip=0.01, far_clip=100000.0),
)
```

The setting is stored on the prim `/ProjectSettings/Viewport/CameraClippingOverride` with attributes `enabled` (bool), `nearClip` (float), `farClip` (float). Parent prims are created on demand as typeless `def` prims.

## Future settings

This extension is the canonical home for any future project-scoped persistent USD setting. New settings should follow the same pattern: a typed prim under `/ProjectSettings/<area>/<feature>` with typed attributes, plus a dataclass + read/write helpers exposed from the package.
