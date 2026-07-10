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

import math
from typing import Protocol

import carb
from lightspeed.common import constants
from pxr import Gf, Sdf, Usd, UsdGeom

PERSPECTIVE_CAMERA_PATH = Sdf.Path("/OmniverseKit_Persp")
GAME_CAMERA_PATHS = (Sdf.Path(constants.CAPTURED_CAMERA), Sdf.Path(constants.ROOTNODE_CAMERA))
CENTER_OF_INTEREST_ATTR_NAME = "omni:kit:centerOfInterest"

_PSEUDO_ORTHOGRAPHIC_FOCAL_LENGTH = 1000.0
_PSEUDO_ORTHOGRAPHIC_APERTURE = 20.955
_PSEUDO_ORTHOGRAPHIC_DISTANCE_MULTIPLIER = 1.2
_PSEUDO_ORTHOGRAPHIC_CLIP_MULTIPLIER = 4.0
_PSEUDO_ORTHOGRAPHIC_NEAR_CLIP = 0.01
_PSEUDO_ORTHOGRAPHIC_CAMERA_AXES = {
    Sdf.Path("/OmniverseKit_Front"): (Gf.Vec3d(1.0, 0.0, 0.0), Gf.Vec3d(0.0, 0.0, 1.0)),
    Sdf.Path("/OmniverseKit_Top"): (Gf.Vec3d(0.0, 0.0, 1.0), Gf.Vec3d(0.0, 1.0, 0.0)),
    Sdf.Path("/OmniverseKit_Right"): (Gf.Vec3d(0.0, -1.0, 0.0), Gf.Vec3d(0.0, 0.0, 1.0)),
}
PSEUDO_ORTHOGRAPHIC_CAMERA_PATHS = tuple(_PSEUDO_ORTHOGRAPHIC_CAMERA_AXES)
_PSEUDO_ORTHOGRAPHIC_CAMERA_ATTRS_TO_COPY = (
    "horizontalApertureOffset",
    "verticalApertureOffset",
    "fStop",
    "focusDistance",
    "shutter:open",
    "shutter:close",
    "exposure:time",
    "exposure:iso",
    "exposure:fStop",
    "exposure",
    "exposure:responsivity",
)


class _ViewportCameraNavigationProtocol(Protocol):
    stage: Usd.Stage | None
    camera_path: Sdf.Path | str


def _as_path(path: Sdf.Path | str | None) -> Sdf.Path | None:
    if path is None:
        return None
    if isinstance(path, Sdf.Path):
        return path
    return Sdf.Path(path)


def is_game_camera_path(path: Sdf.Path | str | None) -> bool:
    """Return whether ``path`` points to a capture-authored game camera."""
    return _as_path(path) in GAME_CAMERA_PATHS


def is_pseudo_orthographic_camera_path(path: Sdf.Path | str | None) -> bool:
    """Return whether ``path`` points to a pseudo-orthographic inspection camera."""
    return _as_path(path) in PSEUDO_ORTHOGRAPHIC_CAMERA_PATHS


def find_capture_game_camera_path(capture_layer: Sdf.Layer | None) -> Sdf.Path | None:
    """Find the game camera path authored by the capture layer itself."""
    if capture_layer is None:
        return None
    for path in GAME_CAMERA_PATHS:
        if capture_layer.GetPrimAtPath(path) is not None:
            return path
    return None


def _remove_prim_spec(layer: Sdf.Layer, path: Sdf.Path, description: str) -> bool:
    if layer.GetPrimAtPath(path) is None:
        return False
    if not layer.permissionToEdit:
        carb.log_warn(f"Can't clear {description} {path} from locked layer {layer.identifier}")
        return False

    edit = Sdf.BatchNamespaceEdit()
    edit.Add(Sdf.NamespaceEdit.Remove(path))
    if not layer.Apply(edit):
        carb.log_warn(f"Failed to clear {description} {path} from layer {layer.identifier}")
        return False
    return True


def _get_camera_translation(camera_prim: Usd.Prim) -> Gf.Vec3d:
    translate_attr = camera_prim.GetAttribute("xformOp:translate")
    if translate_attr and translate_attr.HasAuthoredValue():
        translate = translate_attr.Get()
        if translate is not None:
            return Gf.Vec3d(translate[0], translate[1], translate[2])

    transform_attr = camera_prim.GetAttribute("xformOp:transform")
    if transform_attr and transform_attr.HasAuthoredValue():
        transform = transform_attr.Get()
        if transform is not None:
            matrix = transform if isinstance(transform, Gf.Matrix4d) else Gf.Matrix4d(*transform)
            return matrix.ExtractTranslation()

    return Gf.Vec3d(0.0, 0.0, 0.0)


def _set_camera_transform(camera_prim: Usd.Prim, transform: Gf.Matrix4d):
    xformable = UsdGeom.Xformable(camera_prim)
    xformable.ClearXformOpOrder()
    xformable.AddTransformOp().Set(transform)


def _copy_attr_values(source_attr: Usd.Attribute, target_attr: Usd.Attribute) -> None:
    value = source_attr.Get()
    if value is not None:
        target_attr.Set(value)

    for time_code in source_attr.GetTimeSamples():
        value = source_attr.Get(time_code)
        if value is not None:
            target_attr.Set(value, time_code)


def _copy_camera_attr(source_attr: Usd.Attribute, target_prim: Usd.Prim) -> None:
    target_attr = target_prim.CreateAttribute(
        source_attr.GetName(), source_attr.GetTypeName(), source_attr.IsCustom(), source_attr.GetVariability()
    )
    _copy_attr_values(source_attr, target_attr)


def _copy_camera_schema_attrs(
    source_camera: UsdGeom.Camera, target_camera: UsdGeom.Camera, attr_names: tuple[str, ...], authored_only: bool
):
    source_prim = source_camera.GetPrim()
    target_prim = target_camera.GetPrim()

    for attr_name in attr_names:
        source_attr = source_prim.GetAttribute(attr_name)
        if not source_attr or (authored_only and not source_attr.HasAuthoredValue()):
            continue
        _copy_camera_attr(source_attr, target_prim)


def _copy_authored_camera_attrs(source_camera: UsdGeom.Camera, target_camera: UsdGeom.Camera):
    """Copy authored camera attributes supported by both source and target schemas."""
    _copy_camera_schema_attrs(
        source_camera, target_camera, _PSEUDO_ORTHOGRAPHIC_CAMERA_ATTRS_TO_COPY, authored_only=True
    )


def _copy_composed_camera_attrs(source_camera: UsdGeom.Camera, target_camera: UsdGeom.Camera):
    """Copy composed camera schema values from source to target."""
    _copy_camera_schema_attrs(
        source_camera, target_camera, tuple(UsdGeom.Camera.GetSchemaAttributeNames(False)), authored_only=False
    )


def _copy_center_of_interest(source_prim: Usd.Prim, target_prim: Usd.Prim):
    source_attr = source_prim.GetAttribute(CENTER_OF_INTEREST_ATTR_NAME)
    if not source_attr:
        return

    target_attr = target_prim.CreateAttribute(
        CENTER_OF_INTEREST_ATTR_NAME, Sdf.ValueTypeNames.Vector3d, True, Sdf.VariabilityUniform
    )
    _copy_attr_values(source_attr, target_attr)


def _clear_perspective_camera_session_spec(stage: Usd.Stage) -> bool:
    session_layer = stage.GetSessionLayer()
    if session_layer.GetPrimAtPath(PERSPECTIVE_CAMERA_PATH) is None:
        return True
    return _remove_prim_spec(session_layer, PERSPECTIVE_CAMERA_PATH, "perspective camera session spec")


def _compute_world_range(stage: Usd.Stage, prim_paths: list[str]) -> Gf.Range3d | None:
    bbox_cache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(),
        [UsdGeom.Tokens.default_, UsdGeom.Tokens.render, UsdGeom.Tokens.proxy],
        True,
    )
    world_range = Gf.Range3d()
    for prim_path in prim_paths:
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            continue
        bound_range = bbox_cache.ComputeWorldBound(prim).ComputeAlignedRange()
        if not bound_range.IsEmpty():
            world_range.UnionWith(bound_range)
    if world_range.IsEmpty():
        return None
    return world_range


def _look_at_transform(eye: Gf.Vec3d, target: Gf.Vec3d, up: Gf.Vec3d) -> Gf.Matrix4d:
    return Gf.Matrix4d().SetLookAt(eye, target, up).GetInverse()


# Keep viewport zoom state usable while forcing pseudo-ortho cameras to use a close near clip.
def _get_center_of_interest_distance(camera_prim: Usd.Prim) -> float:
    center_of_interest_attr = camera_prim.GetAttribute(CENTER_OF_INTEREST_ATTR_NAME)
    if center_of_interest_attr:
        center_of_interest = center_of_interest_attr.Get()
        if center_of_interest is not None:
            return max(Gf.Vec3d(center_of_interest[0], center_of_interest[1], center_of_interest[2]).GetLength(), 1.0)

    translate = _get_camera_translation(camera_prim)
    return max(translate.GetLength(), 1.0)


def _author_center_of_interest(camera_prim: Usd.Prim, distance: float | None = None):
    if distance is None:
        distance = _get_center_of_interest_distance(camera_prim)
    distance = max(distance, 1.0)
    camera_prim.CreateAttribute(
        CENTER_OF_INTEREST_ATTR_NAME, Sdf.ValueTypeNames.Vector3d, True, Sdf.VariabilityUniform
    ).Set(Gf.Vec3d(0.0, 0.0, -distance))


def _set_pseudo_orthographic_clipping(camera: UsdGeom.Camera, far_clip: float):
    camera.CreateClippingRangeAttr().Set(
        Gf.Vec2f(_PSEUDO_ORTHOGRAPHIC_NEAR_CLIP, max(far_clip, _PSEUDO_ORTHOGRAPHIC_NEAR_CLIP + 1.0))
    )


def _get_camera_far_clip(camera: UsdGeom.Camera) -> float:
    clipping_range = camera.GetClippingRangeAttr().Get()
    if clipping_range is None:
        return _PSEUDO_ORTHOGRAPHIC_NEAR_CLIP + 1.0
    return max(float(clipping_range[1]), _PSEUDO_ORTHOGRAPHIC_NEAR_CLIP + 1.0)


def clear_game_camera_overrides(stage: Usd.Stage, capture_layer: Sdf.Layer | None) -> list[Sdf.Layer]:
    """Remove game camera prim specs from every layer except the active capture layer."""
    if stage is None:
        return []

    capture_identifier = capture_layer.identifier if capture_layer is not None else None
    removed_layers: list[Sdf.Layer] = []
    for layer in stage.GetLayerStack(True):
        if layer is None or layer.expired or layer.identifier == capture_identifier:
            continue
        removed_from_layer = False
        for path in GAME_CAMERA_PATHS:
            removed_from_layer = _remove_prim_spec(layer, path, "game camera override") or removed_from_layer
        if removed_from_layer:
            removed_layers.append(layer)
    return removed_layers


def copy_capture_camera_to_perspective(stage: Usd.Stage, capture_layer: Sdf.Layer | None) -> Sdf.Path | None:
    """Copy the capture-authored game camera to the disposable perspective camera."""
    if stage is None or capture_layer is None:
        return None

    source_path = find_capture_game_camera_path(capture_layer)
    if source_path is None:
        carb.log_warn("Can't find a game camera in the capture layer; perspective camera won't be updated")
        return None

    if not Sdf.CopySpec(capture_layer, source_path, stage.GetSessionLayer(), PERSPECTIVE_CAMERA_PATH):
        carb.log_warn(f"Failed to copy game camera {source_path} to {PERSPECTIVE_CAMERA_PATH}")
        return None
    with Usd.EditContext(stage, stage.GetSessionLayer()):
        _author_center_of_interest(stage.GetPrimAtPath(PERSPECTIVE_CAMERA_PATH))
    return source_path


def copy_composed_game_camera_to_perspective(stage: Usd.Stage, game_camera_path: Sdf.Path | str | None) -> bool:
    """Copy the currently composed game camera values to the disposable perspective camera."""
    source_path = _as_path(game_camera_path)
    if stage is None or source_path is None or not is_game_camera_path(source_path):
        return False

    game_camera_prim = stage.GetPrimAtPath(source_path)
    if not game_camera_prim.IsValid():
        return False

    source_camera = UsdGeom.Camera(game_camera_prim)
    if not source_camera:
        carb.log_warn(f"Failed to copy composed game camera {source_path}; source prim is not a camera")
        return False

    if not _clear_perspective_camera_session_spec(stage):
        return False

    source_transform = source_camera.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    with Usd.EditContext(stage, stage.GetSessionLayer()):
        target_camera = UsdGeom.Camera.Define(stage, PERSPECTIVE_CAMERA_PATH)
        _copy_composed_camera_attrs(source_camera, target_camera)
        _set_camera_transform(target_camera.GetPrim(), source_transform)
        _copy_center_of_interest(game_camera_prim, target_camera.GetPrim())
        _author_center_of_interest(target_camera.GetPrim())
    return True


def configure_pseudo_orthographic_perspective_cameras(stage: Usd.Stage, geometry_paths: list[str]) -> list[Sdf.Path]:
    """Author perspective-backed Front, Top, and Right cameras into the session layer."""
    if stage is None:
        return []

    world_range = _compute_world_range(stage, geometry_paths)
    if world_range is None:
        carb.log_warn("Can't compute capture bounds for pseudo-orthographic perspective cameras")
        return []

    center = world_range.GetMidpoint()
    radius = max(world_range.GetSize().GetLength() * 0.5, 1.0)
    fov_radians = 2.0 * math.atan(_PSEUDO_ORTHOGRAPHIC_APERTURE / (2.0 * _PSEUDO_ORTHOGRAPHIC_FOCAL_LENGTH))
    distance = max((radius / math.tan(fov_radians * 0.5)) * _PSEUDO_ORTHOGRAPHIC_DISTANCE_MULTIPLIER, 100.0)
    far_clip = distance + (radius * _PSEUDO_ORTHOGRAPHIC_CLIP_MULTIPLIER)
    perspective_camera = UsdGeom.Camera.Get(stage, PERSPECTIVE_CAMERA_PATH)

    configured_paths: list[Sdf.Path] = []
    with Usd.EditContext(stage, stage.GetSessionLayer()):
        for camera_path, (axis, up) in _PSEUDO_ORTHOGRAPHIC_CAMERA_AXES.items():
            camera = UsdGeom.Camera.Define(stage, camera_path)
            camera_prim = camera.GetPrim()
            eye = center + (axis * distance)
            _set_camera_transform(camera_prim, _look_at_transform(eye, center, up))
            if perspective_camera:
                _copy_authored_camera_attrs(perspective_camera, camera)
            camera.CreateProjectionAttr().Set(UsdGeom.Tokens.perspective)
            camera.CreateFocalLengthAttr().Set(_PSEUDO_ORTHOGRAPHIC_FOCAL_LENGTH)
            camera.CreateHorizontalApertureAttr().Set(_PSEUDO_ORTHOGRAPHIC_APERTURE)
            camera.CreateVerticalApertureAttr().Set(_PSEUDO_ORTHOGRAPHIC_APERTURE)
            _set_pseudo_orthographic_clipping(camera, far_clip)
            _author_center_of_interest(camera_prim, distance)
            configured_paths.append(camera_path)
    return configured_paths


def lock_pseudo_orthographic_camera_orientation(stage: Usd.Stage, camera_path: Sdf.Path | str | None) -> bool:
    """Restore a pseudo-orthographic camera's axis orientation while preserving its current position."""
    camera_sdf_path = _as_path(camera_path)
    if stage is None or camera_sdf_path not in _PSEUDO_ORTHOGRAPHIC_CAMERA_AXES:
        return False

    camera_prim = stage.GetPrimAtPath(camera_sdf_path)
    if not camera_prim.IsValid():
        return False

    axis, up = _PSEUDO_ORTHOGRAPHIC_CAMERA_AXES[camera_sdf_path]
    camera = UsdGeom.Camera(camera_prim)
    eye = UsdGeom.Xformable(camera_prim).GetLocalTransformation().ExtractTranslation()
    target = eye - axis
    center_of_interest_distance = _get_center_of_interest_distance(camera_prim)
    far_clip = _get_camera_far_clip(camera)
    with Usd.EditContext(stage, stage.GetSessionLayer()):
        _set_camera_transform(camera_prim, _look_at_transform(eye, target, up))
        # Reapply pseudo-ortho inspection attributes after gestures preserve the camera position.
        _set_pseudo_orthographic_clipping(camera, far_clip)
        _author_center_of_interest(camera_prim, center_of_interest_distance)
    return True


def ensure_perspective_camera_for_navigation(viewport_api: _ViewportCameraNavigationProtocol | None) -> bool:
    """Switch a viewport from the read-only game camera to perspective before navigation mutates it."""
    if viewport_api is None or not is_game_camera_path(viewport_api.camera_path):
        return False

    if not copy_composed_game_camera_to_perspective(viewport_api.stage, viewport_api.camera_path):
        return False

    viewport_api.camera_path = PERSPECTIVE_CAMERA_PATH
    return True


def ensure_editable_camera_for_navigation(
    viewport_api: _ViewportCameraNavigationProtocol | None, action_name: str
) -> bool:
    """Return whether a camera-mutating action can proceed without editing the game camera."""
    if viewport_api is None:
        carb.log_warn(f"{action_name} was canceled because the viewport is unavailable")
        return False

    if not is_game_camera_path(viewport_api.camera_path):
        return True

    if ensure_perspective_camera_for_navigation(viewport_api):
        return True

    carb.log_warn(
        f"{action_name} was canceled because the capture game camera could not be copied to "
        f"{PERSPECTIVE_CAMERA_PATH}; keeping the capture game camera read-only"
    )
    return False
