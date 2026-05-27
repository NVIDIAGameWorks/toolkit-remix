"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

from __future__ import annotations

__doc__ = """
Central configuration for particle curve edit groups.

Each entry maps a logical group of curve-animatable primvars to the hierarchy that the curve editor displays.
Keep these mappings aligned with generatedSchema.usda so edit groups mirror runtime particle channels.

Outlet placement comes from schema display group metadata on the first controlled ``:values`` attr, not from
Python grouping overrides.

``curve_map`` values can be a plain path string or a dict with ``path`` and optional ``display_color`` /
``display_name`` metadata.
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
        "legacy": {
            "spawn": ["primvars:particle:minSpawnSize", "primvars:particle:maxSpawnSize"],
            "target": ["primvars:particle:minTargetSize", "primvars:particle:maxTargetSize"],
            "animated": [
                ["primvars:particle:minSize:x", "primvars:particle:minSize:y"],
                ["primvars:particle:maxSize:x", "primvars:particle:maxSize:y"],
            ],
        },
    },
    "velocity": {
        "display_name": "Velocity",
        "tooltip": "Velocity curves over particle lifetime",
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
        "legacy": {
            "spawn": ["primvars:particle:minSpawnRotationSpeed", "primvars:particle:maxSpawnRotationSpeed"],
            "target": ["primvars:particle:minTargetRotationSpeed", "primvars:particle:maxTargetRotationSpeed"],
            "animated": [
                ["primvars:particle:minRotationSpeed"],
                ["primvars:particle:maxRotationSpeed"],
            ],
        },
    },
    "color": {
        "legacy": {
            "spawn": ["primvars:particle:minSpawnColor", "primvars:particle:maxSpawnColor"],
            "target": ["primvars:particle:minTargetColor", "primvars:particle:maxTargetColor"],
            "animated": [
                ["primvars:particle:minColor"],
                ["primvars:particle:maxColor"],
            ],
        },
    },
}

# Reverse lookup: curve_id -> (group_key, layout_dict, edit_group_path)
PARTICLE_CURVE_LOOKUP: dict[str, tuple[str, dict, str]] = {}
for _group_key, _group in PARTICLE_EDIT_GROUPS.items():
    for _curve_id, _entry in _group.get("curve_map", {}).items():
        _rel_path = _entry["path"] if isinstance(_entry, dict) else _entry
        PARTICLE_CURVE_LOOKUP[_curve_id] = (_group_key, _group, f"{_group_key}/{_rel_path}")

# Legacy lookup: legacy attr -> animated attrs, lifetime seed time, and target kind.
PARTICLE_LEGACY_ANIMATION_MAPPINGS = {}
for _group in PARTICLE_EDIT_GROUPS.values():
    _legacy = _group.get("legacy")
    if _legacy is None:
        continue
    _kind = "curve" if _group.get("curve_map") else "gradient"
    for _spawn, _target, _animated_attrs in zip(
        _legacy["spawn"],
        _legacy["target"],
        _legacy["animated"],
    ):
        _animated = dict(enumerate(_animated_attrs))
        PARTICLE_LEGACY_ANIMATION_MAPPINGS[_spawn] = {
            "kind": _kind,
            "animated": _animated,
            "time": 0.0,
        }
        PARTICLE_LEGACY_ANIMATION_MAPPINGS[_target] = {
            "kind": _kind,
            "animated": _animated,
            "time": 1.0,
        }
