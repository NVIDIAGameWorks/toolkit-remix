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

__all__ = [
    "CAMERA_CLIPPING_OVERRIDE_PATH",
    "SETTINGS_ROOT_PATH",
    "VIEWPORT_SETTINGS_PATH",
    "CameraClippingOverride",
    "get_camera_clipping_override",
    "set_camera_clipping_override",
]

from dataclasses import dataclass

from pxr import Sdf, Usd

SETTINGS_ROOT_PATH = "/ProjectSettings"
VIEWPORT_SETTINGS_PATH = "/ProjectSettings/Viewport"
CAMERA_CLIPPING_OVERRIDE_PATH = "/ProjectSettings/Viewport/CameraClippingOverride"

_ATTR_ENABLED = "enabled"
_ATTR_NEAR_CLIP = "nearClip"
_ATTR_FAR_CLIP = "farClip"

_DEFAULT_NEAR = 0.01
_DEFAULT_FAR = 100000.0

# Minimum allowed near-clip distance. A zero or negative near plane collapses
# the perspective frustum and produces undefined rendering. The exact floor
# is arbitrary; 0.0001 is small enough not to constrain any realistic scene
# and large enough to keep depth precision usable.
_MIN_NEAR_CLIP = 0.0001
# Minimum gap between far and near. Equal or inverted values produce a
# degenerate frustum.
_MIN_FAR_NEAR_DELTA = 0.0001


@dataclass
class CameraClippingOverride:
    """Project-scoped persistent clipping range override for all cameras."""

    enabled: bool = False
    near_clip: float = _DEFAULT_NEAR
    far_clip: float = _DEFAULT_FAR

    def __post_init__(self):
        # Clamp at the dataclass boundary so every writer (UI, scripts,
        # future APIs) gets the same invariants without duplicating logic.
        self.near_clip = max(_MIN_NEAR_CLIP, float(self.near_clip))
        self.far_clip = max(float(self.far_clip), self.near_clip + _MIN_FAR_NEAR_DELTA)


def get_camera_clipping_override(stage: Usd.Stage) -> CameraClippingOverride:
    """Read the project's camera clipping override from the Settings prim.

    Returns defaults (enabled=False, near=0.01, far=100000) if the prim or
    any individual attribute has no authored value on the composed stage.
    """
    if not stage:
        return CameraClippingOverride()
    prim = stage.GetPrimAtPath(CAMERA_CLIPPING_OVERRIDE_PATH)
    if not prim.IsValid():
        return CameraClippingOverride()

    def _read(attr_name: str, default):
        attr = prim.GetAttribute(attr_name)
        if attr and attr.HasAuthoredValue():
            return attr.Get()
        return default

    return CameraClippingOverride(
        enabled=bool(_read(_ATTR_ENABLED, False)),
        near_clip=float(_read(_ATTR_NEAR_CLIP, _DEFAULT_NEAR)),
        far_clip=float(_read(_ATTR_FAR_CLIP, _DEFAULT_FAR)),
    )


def set_camera_clipping_override(stage: Usd.Stage, override: CameraClippingOverride) -> None:
    """Author the project's camera clipping override under /ProjectSettings/Viewport.

    Authors directly via Sdf prim/attribute specs on the project's root layer so we
    don't depend on the stage's current edit target (which may be a capture sublayer
    or session layer that doesn't accept new prims). Creates intermediate parent
    specs as typeless `def` prims so the hierarchy works regardless of how the
    /ProjectSettings root is specified on other layers in the stack.
    """
    if not stage:
        return
    target_layer = stage.GetRootLayer()
    with Sdf.ChangeBlock():
        # Author every intermediate prim spec via Sdf directly. CreatePrimInLayer
        # walks the path and creates missing parents as typeless overs by default;
        # we then upgrade specifiers to `def` so they have a defining opinion.
        for path_str in (SETTINGS_ROOT_PATH, VIEWPORT_SETTINGS_PATH, CAMERA_CLIPPING_OVERRIDE_PATH):
            prim_spec = target_layer.GetPrimAtPath(path_str)
            if prim_spec is None:
                prim_spec = Sdf.CreatePrimInLayer(target_layer, path_str)
            prim_spec.specifier = Sdf.SpecifierDef

        override_spec = target_layer.GetPrimAtPath(CAMERA_CLIPPING_OVERRIDE_PATH)
        for attr_name, attr_value, attr_type in (
            (_ATTR_ENABLED, bool(override.enabled), Sdf.ValueTypeNames.Bool),
            (_ATTR_NEAR_CLIP, float(override.near_clip), Sdf.ValueTypeNames.Float),
            (_ATTR_FAR_CLIP, float(override.far_clip), Sdf.ValueTypeNames.Float),
        ):
            attr_spec = override_spec.attributes.get(attr_name)
            if attr_spec is None:
                attr_spec = Sdf.AttributeSpec(override_spec, attr_name, attr_type)
            attr_spec.default = attr_value
