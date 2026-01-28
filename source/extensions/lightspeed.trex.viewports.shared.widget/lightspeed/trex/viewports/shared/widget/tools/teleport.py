"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = [
    "teleport",
    "teleporter_factory",
    "TeleportButtonGroup",
    "PointMousePicker",
    "create_button_instance",
    "delete_button_instance",
]

import asyncio
import math
from typing import TYPE_CHECKING, Any, Callable, Sequence

import carb.settings
import omni.kit.commands
import omni.kit.undo
import omni.ui as ui
from lightspeed.hydra.remix.core import RemixRequestQueryType, viewport_api_request_query_hdremix
from lightspeed.trex.app.style import style
from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementsCore
from lightspeed.trex.contexts.setup import Contexts as _TrexContexts
from lightspeed.trex.hotkeys import TrexHotkeyEvent
from lightspeed.trex.hotkeys import get_global_hotkey_manager as _get_global_hotkey_manager
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.kit.notification_manager import NotificationStatus, post_notification
from omni.kit.widget.toolbar.widget_group import WidgetGroup
from pxr import Gf, Sdf, Usd, UsdGeom

if TYPE_CHECKING:
    from omni.kit.widget.viewport.api import ViewportAPI


# distance to teleport in front of camera if no objects are hit
DEFAULT_TELEPORT_DISTANCE = 50
MAX_PICK_DISTANCE = 1.0e5
TELEPORT_HOTKEY = "Ctrl+T"

_teleport_button_group: TeleportButtonGroup = None


class TeleportUserError(Exception):
    """Raised when we are unable to carry out teleport operation."""


def create_button_instance():
    # Since the toolbar is reused across viewports, we only want one toolbar button instance.
    global _teleport_button_group
    _teleport_button_group = TeleportButtonGroup()
    return _teleport_button_group


def delete_button_instance():
    global _teleport_button_group
    _teleport_button_group = None


def _get_current_mouse_coords() -> tuple[float, float]:
    """Get current mouse position in screen space"""
    app_window = omni.appwindow.get_default_app_window()
    interface = carb.input.acquire_input_interface()
    dpi_scale = ui.Workspace.get_dpi_scale()
    pos_x, pos_y = interface.get_mouse_coords_pixel(app_window.get_mouse())
    return pos_x / dpi_scale, pos_y / dpi_scale


def default_filter_fn(viewport_api: ViewportAPI, selection: list[Sdf.Path]):
    # default check to filter down to xformable types
    prims = [viewport_api.stage.GetPrimAtPath(path) for path in selection]
    prims = [prim for prim in prims if prim.IsA(UsdGeom.Xformable)]
    return [prim.GetPath() for prim in prims]


async def _teleport(
    viewport_api: ViewportAPI,
    prim_path: str,
    position: carb.Double3 | None,
    max_pick_distance: int = MAX_PICK_DISTANCE,
    default_distance: float = DEFAULT_TELEPORT_DISTANCE,
    filter_fn: Callable[[ViewportAPI, list[Sdf.Path]], list[Sdf.Path]] = default_filter_fn,
    default_to_centered: bool = False,
):
    """
    Move the currently selected object to the picked position.

    Args:
        prim_path : The path to the prim under the cursor
        position : The world position under the cursor
        max_pick_distance : max distance away from the camera for a teleport target
        default_distance : distance to teleport in front of camera if no objects are hit
        filter_fn : A func that will take a list of prim paths and return the prim_path to apply
            the transformation to or no paths if the prim is not teleport-able
        default_to_centered : Whether to raise an error or just center object if no position is
            determined under the cursor
    """

    # Get current selection
    selected_paths: list[str] = viewport_api.usd_context.get_selection().get_selected_prim_paths()
    if not selected_paths:
        raise TeleportUserError("Nothing selected.")

    # Get teleport targets
    target_path_map: dict[Sdf.Path, Sdf.Path] = {}
    for path in selected_paths:
        sdf_path = Sdf.Path(path)
        target_paths = filter_fn(viewport_api, [sdf_path])
        if target_paths:
            if len(target_paths) != 1:
                raise ValueError(f"Unexpectedly found more than one target for {path}")
            target_path_map[sdf_path] = target_paths[0]

    if not target_path_map:
        raise TeleportUserError("No selected prims are teleport-able!")

    # try and find a camera
    cam_xform = None
    cam_path = viewport_api.camera_path
    if cam_path:
        cam_prim = UsdGeom.Camera(viewport_api.stage.GetPrimAtPath(cam_path))
        if cam_prim:
            cam_xform = cam_prim.ComputeLocalToWorldTransform(Usd.TimeCode.Default())

    # check that point is close enough to camera
    # (With sky dome meshes, we probably will always hit "something" so we use this heuristic
    # to try and guess whether we're in a reasonable range.)
    if cam_xform and position:
        cam_position = cam_xform.ExtractTranslation()
        distance_between = math.dist(cam_position, position)
        if distance_between > max_pick_distance:
            carb.log_warn(f"Picked point is too far from camera (> {max_pick_distance}): {position}")
            # pretend we didn't hit anything so that default behaviour is used
            prim_path = None

    if not prim_path:
        if not default_to_centered:
            raise TeleportUserError("Specific world position could not be determined. No object under mouse?")
        post_notification(
            "Teleport: Specific world position could not be determined. Defaulting position to in front of camera"
        )
        # If there are no objects under mouse we shoot a ray from camera out to
        # default distance away and use that position
        offset = Gf.Vec3d(0.0, 0.0, -default_distance)
        position = cam_xform.Transform(offset)

    with omni.kit.undo.group():
        # Note: We also have "TransformPrimsSRT" command, but it's no more efficient and this
        # loop allows us to catch any failures.
        for path, target_path in target_path_map.items():
            # calculate the translation needed to get move the currently selected instance at `path` to
            # the provided world position.
            prim = viewport_api.stage.GetPrimAtPath(path)
            parent_xform = UsdGeom.Xformable(prim).ComputeParentToWorldTransform(Usd.TimeCode.Default()).GetInverse()
            local_translation = parent_xform.Transform(Gf.Vec3d(*position))

            success, _result = omni.kit.commands.execute(
                "TransformPrimSRT",
                path=target_path,
                new_translation=Gf.Vec3d(*local_translation),
                usd_context_name=viewport_api.usd_context_name,
            )
            if not success:
                raise RuntimeError("Teleport command failed.")

    return True


@omni.usd.handle_exception
async def teleport(
    viewport_api: ViewportAPI,
    prim_path: str,
    position: carb.Double3 | None,
    max_pick_distance: int = MAX_PICK_DISTANCE,
    default_distance: float = DEFAULT_TELEPORT_DISTANCE,
    filter_fn: Callable[[ViewportAPI, list[Sdf.Path]], list[Sdf.Path]] = None,
    default_to_centered: bool = False,
):
    """Move the currently selected object to the picked position."""
    try:
        await _teleport(
            viewport_api,
            prim_path,
            position,
            max_pick_distance=max_pick_distance,
            default_distance=default_distance,
            filter_fn=filter_fn,
            default_to_centered=default_to_centered,
        )
    except TeleportUserError as err:
        post_notification("Cannot Teleport: " + str(err), status=NotificationStatus.WARNING)


class PointMousePicker:
    """Class to help provide the 3d point under the mouse in the viewport."""

    def __init__(
        self,
        viewport_api: ViewportAPI,
        viewport_frame: ui.Frame,
        point_picked_callback_fn: Callable[[str, carb.Double3 | None, carb.Uint2], None],
    ):
        """
        Args:
            viewport_api: Current viewport's api object
            viewport_frame: Widget surrounding viewport, needed for determining screen space
            point_picked_callback_fn: User supplied function to call with pick result
        """
        if viewport_api is None or viewport_frame is None:
            raise ValueError("Value of required arguments cannot be none.")
        self._viewport_api = viewport_api
        self._viewport_frame = viewport_frame
        self._user_point_picked_callback_fn = point_picked_callback_fn

    def _convert_screen_coords_to_ndc_coords(self, mouse_coords: tuple[float, float]):
        frame = self._viewport_frame
        # converts the screen mouse coordinates to NDC coordinates within the frame
        mouse_ndc = (
            # coord - frame position x / width
            (-1.0 + 2.0 * ((mouse_coords[0] - frame.screen_position_x) / frame.computed_width)),
            (1 - 2.0 * ((mouse_coords[1] - frame.screen_position_y) / frame.computed_height)),
        )
        return mouse_ndc

    def _point_picked_fn(self, prim_path: str, position: Sequence[float], pixels: Sequence[int]) -> None:
        self._user_point_picked_callback_fn(prim_path, position, pixels)

    def _pick_default(self):
        self._point_picked_fn("", (0.0, 0.0, 0.0), (0, 0))

    def pick(self, mouse_coords: tuple[float, float] | None = None, ndc_coords: tuple[float, float] | None = None):
        if mouse_coords and ndc_coords:
            raise ValueError("Must provide either mouse coords in screen space or normalized device coordinates.")

        if not ndc_coords:
            if not mouse_coords:
                mouse_coords = _get_current_mouse_coords()
            ndc_coords = self._convert_screen_coords_to_ndc_coords(mouse_coords)

        # compute the viewports texture pixel, (not necessary a 1:1 mapping of visibility)
        pixel, valid = self._viewport_api.map_ndc_to_texture_pixel(ndc_coords)
        if not valid:
            # fallback to center of viewport
            pixel, valid = self._viewport_api.map_ndc_to_texture_pixel((0, 0))

        if valid:
            viewport_api_request_query_hdremix(
                carb.Uint2(*pixel),
                callback=self._point_picked_fn,
                query_name=f"{__name__}.mouse-point-query",
                request_query_type=RemixRequestQueryType.PATH_AND_WORLDPOS,
            )
            return True

        # trigger callback without a point picked.
        self._pick_default()
        return False


class AlwaysFalseModel(ui.AbstractValueModel):
    """Dummy model for a toolbar button that is always unpressed."""

    def set_value(self, value):
        pass

    def get_value_as_bool(self):
        return False


class TeleportButtonGroup(WidgetGroup):
    """Teleport toolbar button"""

    name = "teleport"

    def __init__(self):
        super().__init__()
        self._button = None
        self._model = AlwaysFalseModel()
        self.__button_pressed = _Event()

    def get_style(self):
        return {f"Button.Image::{self.name}": style.default[f"Button.Image::{self.name}"]}

    def _on_mouse_released(self, button):
        self._acquire_toolbar_context()
        if self._is_in_context() and self._button is not None and self._button.enabled:
            self.__button_pressed()

    def subscribe_button_pressed(self, callback: Callable[[bool], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__button_pressed, callback)

    def create(self, default_size: ui.Length):
        self._button = ui.ToolButton(
            model=self._model,
            name=self.name,
            identifier=self.name,
            tooltip=f"Teleport to Center (Use {TELEPORT_HOTKEY} to teleport under mouse)",
            width=default_size,
            height=default_size,
            mouse_released_fn=lambda x, y, b, _: self._on_mouse_released(b),
        )
        return {self.name: self._button}

    def clean(self):
        super().clean()
        self._button = None
        self.__button_pressed = None


class Teleporter:
    """Class to connect a viewport to the teleport action."""

    TELEPORT_MAX_PICK_DISTANCE_SETTING = "/app/viewport/teleport/max_pick_distance_from_camera"
    TELEPORT_DEFAULT_DISTANCE_SETTING = "/app/viewport/teleport/default_teleport_distance_from_camera"

    def __init__(self, viewport_api: ViewportAPI):
        self._viewport_api = viewport_api
        self._settings = carb.settings.get_settings()

        usd_context_name = viewport_api.usd_context_name
        self._context = _TrexContexts(usd_context_name)
        self._core = _AssetReplacementsCore(usd_context_name)

        # this will overlay viewport window since its created in factory context
        self.__viewport_frame = ui.Frame()

        # Subscribe to the Teleport Hotkey for this viewport
        hotkey_manager = _get_global_hotkey_manager()
        self._hotkey_subscription = hotkey_manager.subscribe_hotkey_event(
            TrexHotkeyEvent.CTRL_T,
            self.on_teleport_hotkey,
            context=self._context,
        )
        # Subscribe to presses from Teleport Button
        self._button_pressed_subscription = _teleport_button_group.subscribe_button_pressed(self.on_teleport_button)

    def filter_to_transform_target_fn(self, _viewport_api: ViewportAPI, selection: list[Sdf.Path]):
        """Replace path with the best target for teleport translation"""
        # redirect from path under instance root to prototype path (same way transform manipulators work)
        # from: lightspeed\trex\viewports\manipulators\custom_manipulator\prim_transform_manipulator.py
        return [Sdf.Path(path) for path in self._core.filter_transformable_prims(selection)]

    def get_picker(self, default_to_centered: bool = False):
        """Return a picker object configured with the proper teleport callbacks for this viewport."""
        filter_fn = default_filter_fn
        if self._context == _TrexContexts.STAGE_CRAFT:
            # filter_fn may return a different path to target the prototype prims if needed. This means that
            # xform will apply to all instances equally (relative to their world positions)
            filter_fn = self.filter_to_transform_target_fn

        def pick_callback(prim_path: str, position: carb.Double3 | None, _pixels: carb.Uint2):
            max_pick_distance = self._settings.get(self.TELEPORT_MAX_PICK_DISTANCE_SETTING) or MAX_PICK_DISTANCE
            default_distance = self._settings.get(self.TELEPORT_DEFAULT_DISTANCE_SETTING) or DEFAULT_TELEPORT_DISTANCE
            # Note: needs to be run async so that move command can happen in non-callback context and
            #  grab event loop.
            asyncio.run(
                teleport(
                    self._viewport_api,
                    prim_path,
                    position,
                    max_pick_distance=max_pick_distance,
                    default_distance=default_distance,
                    filter_fn=filter_fn,
                    default_to_centered=default_to_centered,
                )
            )

        return PointMousePicker(self._viewport_api, self.__viewport_frame, point_picked_callback_fn=pick_callback)

    def on_teleport_hotkey(self):
        self.get_picker().pick()

    def on_teleport_button(self):
        # If the button is hit we teleport to center screen rather than under the mouse since that would always
        # be under the toolbar button. We also want to default this behavior to center object on camera if there
        # is no object in the center of the viewport.
        self.get_picker(default_to_centered=True).pick(ndc_coords=(0, 0))

    def destroy(self):
        if self._hotkey_subscription:
            self._hotkey_subscription = None

    # Required for compatibility with "lightspeed.trex.viewports.shared.widget.scene.layer._SceneItem"
    @property
    def visible(self):
        return True


def teleporter_factory(desc: dict[str, Any]):
    teleporter = Teleporter(desc.get("viewport_api"))
    return teleporter
