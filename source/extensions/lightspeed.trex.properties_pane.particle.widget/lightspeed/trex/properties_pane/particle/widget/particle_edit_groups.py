"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0

Central configuration for particle curve edit groups.

Each entry maps a logical group of curve-animatable primvars to a hierarchy
that the curve editor will display. Derived from generatedSchema.usda.

To add a new group, add an entry here. No procedural code changes needed.

curve_map values can be a plain path string or a dict with "path" and
optional "display_color" / "display_name".
"""

_RED = 0xFF0E20AD
_GREEN = 0xFF0D7A0F
_BLUE = 0xFF9C2619
_ORANGE = 0xFFDDA844
_CYAN = 0xFF44AAAA

PARTICLE_EDIT_GROUPS = {
    "size": {
        "display_name": "Particle Size",
        "tooltip": "Size curves over particle lifetime",
        "accessor_groups": ["Lifetime Animation"],
        "children": {
            "minSize": {"display_name": "Min Size", "children": {}},
            "maxSize": {"display_name": "Max Size", "children": {}},
        },
        "curve_map": {
            "primvars:particle:minSize:x": {"path": "minSize/x", "display_color": _RED},
            "primvars:particle:minSize:y": {"path": "minSize/y", "display_color": _GREEN},
            "primvars:particle:maxSize:x": {"path": "maxSize/x", "display_color": _RED},
            "primvars:particle:maxSize:y": {"path": "maxSize/y", "display_color": _GREEN},
        },
    },
    "velocity": {
        "display_name": "Velocity",
        "tooltip": "Velocity curves over particle lifetime",
        "accessor_groups": ["Lifetime Animation"],
        "children": {
            "maxVelocity": {"display_name": "Max Velocity", "children": {}},
        },
        "curve_map": {
            "primvars:particle:maxVelocity:x": {"path": "maxVelocity/x", "display_color": _RED},
            "primvars:particle:maxVelocity:y": {"path": "maxVelocity/y", "display_color": _GREEN},
            "primvars:particle:maxVelocity:z": {"path": "maxVelocity/z", "display_color": _BLUE},
        },
    },
    "rotationSpeed": {
        "display_name": "Rotation Speed",
        "tooltip": "Rotation speed curves over particle lifetime",
        "accessor_groups": ["Lifetime Animation"],
        "children": {},
        "curve_map": {
            "primvars:particle:minRotationSpeed": {
                "path": "minRotationSpeed",
                "display_name": "Min",
                "display_color": _ORANGE,
            },
            "primvars:particle:maxRotationSpeed": {
                "path": "maxRotationSpeed",
                "display_name": "Max",
                "display_color": _CYAN,
            },
        },
    },
}

# Reverse lookup: curve_id -> (group_key, layout_dict, edit_group_path)
PARTICLE_CURVE_LOOKUP: dict[str, tuple[str, dict, str]] = {}
for _group_key, _group in PARTICLE_EDIT_GROUPS.items():
    for _curve_id, _entry in _group.get("curve_map", {}).items():
        _rel_path = _entry["path"] if isinstance(_entry, dict) else _entry
        PARTICLE_CURVE_LOOKUP[_curve_id] = (_group_key, _group, f"{_group_key}/{_rel_path}")
