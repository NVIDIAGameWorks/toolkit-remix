"""
* Copyright (c) 2024, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import asyncio
import math
from typing import TYPE_CHECKING, Callable, Optional, Sequence

import carb.settings
import omni.appwindow
import omni.flux.utils.widget.resources
import omni.kit.app
import omni.kit.commands
import omni.kit.undo
import omni.timeline
import omni.ui as ui
from lightspeed.hydra.remix.core import RemixRequestQueryType, viewport_api_request_query_hdremix
from omni.kit.widget.toolbar.hotkey import Hotkey
from omni.kit.widget.toolbar.widget_group import WidgetGroup
from pxr import Gf, Usd, UsdGeom

if TYPE_CHECKING:
    from omni.kit.widget.viewport.api import ViewportAPI
    from pxr import Sdf


# distance to teleport in front of camera if no objects are hit
DEFAULT_TELEPORT_DISTANCE = 10
MAX_PICK_DISTANCE = 1.0e5
TELEPORT_TOOL_NAME = "Teleport"


class TeleportUserError(Exception):
    """Raised when we are unable to carry out teleport operation."""


def _get_current_mouse_coords() -> tuple[float, float]:
    """Get current mouse position in screen space"""
    app_window = omni.appwindow.get_default_app_window()
    interface = carb.input.acquire_input_interface()
    dpi_scale = ui.Workspace.get_dpi_scale()
    pos_x, pos_y = interface.get_mouse_coords_pixel(app_window.get_mouse())
    return pos_x / dpi_scale, pos_y / dpi_scale


def _filter_non_teleportable(viewport_api: "ViewportAPI", selection: list["Sdf.Path"]):
    """Filter out prim paths that shouldn't be teleported"""
    # filter out game objects that do not show a tranform manipulator
    # from: lightspeed\trex\viewports\manipulators\custom_manipulator\prim_transform_manipulator.py
    from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementsCore

    _core = _AssetReplacementsCore(viewport_api.usd_context_name)
    return _core.filter_transformable_prims(selection)


async def _teleport(
    viewport_api: "ViewportAPI",
    prim_path: str,
    position: Optional[carb.Double3],
    max_pick_distance: int = MAX_PICK_DISTANCE,
    default_distance: float = DEFAULT_TELEPORT_DISTANCE,
    filter_fn: Callable[["ViewportAPI", list["Sdf.Path"]], list["Sdf.Path"]] = None,
):
    """
    Move the currently selected object to the picked position.
    """

    # Get current selection
    prim_paths = viewport_api.usd_context.get_selection().get_selected_prim_paths()
    if not prim_paths:
        raise TeleportUserError("Nothing selected.")

    if filter_fn:
        prim_paths = filter_fn(viewport_api, prim_paths)
    else:
        # default check to filter down to xformable types
        prims = [viewport_api.stage.GetPrimAtPath(path) for path in prim_paths]
        prims = [prim for prim in prims if prim.IsA(UsdGeom.Xformable)]
        prim_paths = [prim.GetPath() for prim in prims]

    if not prim_paths:
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
    if cam_xform:
        cam_position = cam_xform.ExtractTranslation()
        distance_between = math.dist(cam_position, position)
        if distance_between > max_pick_distance:
            # pretend we didn't hit anything so that default behaviour is used
            prim_path = None

    if not prim_path:
        # If there are no objects under mouse we shoot a ray from camera out to
        # default distance away and use that position
        offset = Gf.Vec3d(0.0, 0.0, -default_distance)
        position = cam_xform.Transform(offset)

    with omni.kit.undo.group():
        # Note: We also have "TransformPrimsSRT" command, but it's no more efficient and this
        # loop allows us to catch any failures.
        for path in prim_paths:
            prim = viewport_api.stage.GetPrimAtPath(path)
            parent_xform = UsdGeom.Xformable(prim).ComputeParentToWorldTransform(Usd.TimeCode.Default()).GetInverse()
            local_translation = parent_xform.Transform(Gf.Vec3d(*position))

            success, _result = omni.kit.commands.execute(
                "TransformPrimSRT",
                path=path,
                new_translation=Gf.Vec3d(*local_translation),
                usd_context_name=viewport_api.usd_context_name,
            )
            if not success:
                raise RuntimeError("Teleport command failed.")

    return True


class PointMousePicker:
    """Class to help provide the 3d point under the mouse in the viewport."""

    def __init__(
        self,
        viewport_api: "ViewportAPI",
        viewport_frame: ui.Frame,
        point_picked_callback_fn: Callable[[str, Sequence[float], Sequence[int]], None],
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
        self._point_picked_fn("", (0.0, 0.0, 0.0), (int(0), int(0)))

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
    """Teleport button"""

    name = "teleport"

    TELEPORT_MAX_PICK_DISTANCE_SETTING = "/app/viewport/teleport/max_pick_distance_from_camera"
    TELEPORT_DEFAULT_DISTANCE_SETTING = "/app/viewport/teleport/default_teleport_distance_from_camera"

    def __init__(self):
        super().__init__()
        self._button = None
        self._hotkey = None
        self._icon_path = None

        self._model = AlwaysFalseModel()
        self._settings = carb.settings.get_settings()

        def on_hotkey_changed(hotkey: str):
            if self._button:
                self._button.tooltip = f"{TELEPORT_TOOL_NAME} ({hotkey})"

        # Assign Teleport button Hotkey
        self._hotkey = Hotkey(
            "toolbar::teleport",
            "Ctrl+T",
            self.on_teleport_hotkey,
            lambda: self._button is not None and self._button.enabled and self._is_in_context(),
            on_hotkey_changed_fn=on_hotkey_changed,
        )

    @property
    def icon_path(self):
        if not self._icon_path:
            # delay, until after init
            self._icon_path = omni.flux.utils.widget.resources.get_icons(
                "teleport", "lightspeed.trex.viewports.shared.widget"
            )
            assert self.icon_path, "icon not found."
        return self._icon_path

    def get_picker(self):
        from lightspeed.trex.viewports.shared.widget.extension import get_active_viewport

        # grab the current viewport live...
        viewport = get_active_viewport()
        if not viewport:
            raise RuntimeError("No active viewport!")
        viewport_api = viewport.viewport_api
        viewport_frame = viewport.viewport_frame()

        def pick_callback(prim_path, position, _pixels):
            max_pick_distance = self._settings.get(self.TELEPORT_MAX_PICK_DISTANCE_SETTING) or MAX_PICK_DISTANCE
            default_distance = self._settings.get(self.TELEPORT_DEFAULT_DISTANCE_SETTING) or DEFAULT_TELEPORT_DISTANCE
            # Note: needs to be run async so that move command can happen in non-callback context and
            #  grab event loop.
            asyncio.run(
                _teleport(
                    viewport_api,
                    prim_path,
                    position,
                    max_pick_distance=max_pick_distance,
                    default_distance=default_distance,
                    filter_fn=_filter_non_teleportable,
                )
            )

        return PointMousePicker(viewport_api, viewport_frame, point_picked_callback_fn=pick_callback)

    def clean(self):
        super().clean()
        if self._hotkey:
            self._hotkey.clean()
            self._hotkey = None

    def get_style(self):
        style = {
            "Button.Image::teleport": {"image_url": self.icon_path},
        }
        return style

    def _on_mouse_released(self, button):
        # if the button is hit we teleport to center screen rather than under toolbar button
        self.get_picker().pick(ndc_coords=(0, 0))

    def on_teleport_hotkey(self):
        self._acquire_toolbar_context()
        self.get_picker().pick()

    def create(self, default_size):
        self._button = ui.ToolButton(
            model=self._model,
            name="teleport",
            identifier="teleport",
            tooltip=f"{TELEPORT_TOOL_NAME} (T)",
            width=default_size,
            height=default_size,
            mouse_released_fn=lambda x, y, b, _: self._on_mouse_released(b),
        )
        return {self.name: self._button}
