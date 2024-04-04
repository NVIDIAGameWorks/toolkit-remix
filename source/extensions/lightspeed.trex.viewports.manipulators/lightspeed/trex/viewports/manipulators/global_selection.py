"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""

import carb.settings
import omni.usd
from lightspeed.hydra.remix.core import (
    hdremix_highlight_paths,
    hdremix_objectpicking_request,
    hdremix_uselegacyselecthighlight,
)
from pxr import Gf

HDREMIX_LEGACY_OBJECT_PICKING_HIGHLIGHTING = hdremix_uselegacyselecthighlight() != 0

# NOTE: it's not clear how distance_limit in add_light_selection() is calculated
# (usually it's ~3 units further, plus depth test is again broken?)
LIGHT_SELECTION_WITH_DEPTH_TEST = False

CARB_SETTING_HIGHLIGHT_COLOR = "/persistent/app/viewport/outline/color"


def l_apply_picking_mode(old, picked, pickingmode):
    if pickingmode is omni.usd.PickingMode.RESET_AND_SELECT:
        if len(picked) > 0:
            return list(set(picked))
        return []
    if pickingmode is omni.usd.PickingMode.MERGE_SELECTION:
        return list(set(old) | set(picked))
    if pickingmode is omni.usd.PickingMode.INVERT_SELECTION:
        return list(set(old) - set(picked))
    return list(set(old))


# Omniverse Scene View doesn't currently have any good way to resolve selection between layers - in our case,
# the Hydra Delegate responsible for mesh selection, and the OpenGLSceneView with the light gizmo layers.
# to fix it, we route all selection queries through this class, manually check the OpenGLSceneView selection first,
# then the Hydra Delegate selection.  For box selection, we have to let the Hydra Delegate resolve the box selection
# first, listen for that change, then add the light selection.
class GlobalSelection:
    def __init__(self):
        self._viewport_api = None
        self._pickingmode = omni.usd.PickingMode.RESET_AND_SELECT
        self._needlight_pix = None
        self._issingleclick = True
        self._curlights = []
        self.lightmanipulators = {}

    @staticmethod
    def get_instance():
        return GlobalSelection._instance

    @staticmethod
    def g_set_lightmanipulators(ls):
        GlobalSelection.get_instance().lightmanipulators = ls

    def finalize_selection(self, pickedprims, pickedlights, pickingmode):
        usd_context = self._viewport_api.usd_context
        if usd_context:
            pickedprims = list(pickedprims)
            pickedlights = list(pickedlights)

            if self._issingleclick:
                # select single thing
                if len(pickedprims) > 1:
                    pickedprims = [pickedprims[0]]
                if len(pickedlights) > 1:
                    pickedlights = [pickedlights[0]]
                # if single click, prioritize a light source
                if len(pickedlights) > 0 and len(pickedprims) > 0:
                    pickedprims = []

            updated = l_apply_picking_mode(
                usd_context.get_selection().get_selected_prim_paths(), pickedprims + pickedlights, pickingmode
            )
            usd_context.get_selection().set_selected_prim_paths(updated, False)
        self._pickingmode = omni.usd.PickingMode.RESET_AND_SELECT
        self._curlights = []

    def fin_set_prims(self, pickedprims, pickingmode):
        self.finalize_selection(pickedprims, self._curlights, pickingmode)

    def fin_set_lights(self, pickedlights, pickingmode):
        self._curlights = pickedlights

    def get_color_from_settings(self):
        try:
            # must be same as 'OUTLINE_COLOR_INDEX' in
            # kit\source\extensions\omni.kit.viewport.menubar.settings\omni\kit\viewport\menubar\settings\setting_menu_container.py
            outline_color_index = 1020
            isettings = carb.settings.get_settings()
            r = isettings.get_as_string(CARB_SETTING_HIGHLIGHT_COLOR + "/" + str(outline_color_index + 0))
            g = isettings.get_as_string(CARB_SETTING_HIGHLIGHT_COLOR + "/" + str(outline_color_index + 1))
            b = isettings.get_as_string(CARB_SETTING_HIGHLIGHT_COLOR + "/" + str(outline_color_index + 2))
            return (float(r), float(g), float(b))
        except Exception as e:
            carb.log_warn(f"update_colors error: {e}")
            return (1.0, 1.0, 1.0)

    def objectpicking_oncomplete(self, selectedpaths):
        self.fin_set_prims(selectedpaths, self._pickingmode)

    # Called on light click (and prim click if HDREMIX_LEGACY_OBJECT_PICKING_HIGHLIGHTING)
    def __on_query_complete(self, path, pos, *args):
        if HDREMIX_LEGACY_OBJECT_PICKING_HIGHLIGHTING:
            self.fin_set_prims([path], self._pickingmode)

    # Filter lights inside the rect
    def l_lights_inside_rect(self, viewport_api, rect):
        if self.lightmanipulators is None:
            return []
        lights = []
        for light_manipulator in self.lightmanipulators.values():
            transform = light_manipulator.model.get_as_floats(light_manipulator.model.get_item("transform"))
            ndc_pos = viewport_api.world_to_ndc.Transform([transform[12], transform[13], transform[14]])
            if ndc_pos[2] > 1.0:
                # light is behind camera
                continue
            pixel_loc, ret_viewport_api = viewport_api.map_ndc_to_texture_pixel(ndc_pos)
            if (
                ret_viewport_api
                and rect[0][0] <= pixel_loc[0] <= rect[1][0]
                and rect[1][1] <= pixel_loc[1] <= rect[0][1]
            ):
                # light is inside the rect
                lights.append(light_manipulator.model.get_prim_path())
        return list(lights)

    # Request prim/light pick in the rect (can be a click)
    def add_prim_selection(self, viewport_api, args):
        self._viewport_api = viewport_api
        self._pickingmode = args[2]
        if args[0][0] != args[1][0] or args[0][1] != args[1][1]:
            # box selection
            if HDREMIX_LEGACY_OBJECT_PICKING_HIGHLIGHTING:
                self._viewport_api.request_pick(args[0], args[1], args[2], "lightspeed_selection")
            else:
                hdremix_objectpicking_request(
                    args[0][0], args[0][1], args[1][0], args[1][1], self.objectpicking_oncomplete
                )
            self._needlight_pix = None
            self._issingleclick = False
            self.fin_set_lights(self.l_lights_inside_rect(viewport_api, args), self._pickingmode)
        else:
            # click selection
            if HDREMIX_LEGACY_OBJECT_PICKING_HIGHLIGHTING:
                self._viewport_api.request_query(args[0], self.__on_query_complete, "lightspeed_selection")
            else:
                hdremix_objectpicking_request(
                    args[0][0], args[0][1], args[0][0] + 1, args[0][1] + 1, self.objectpicking_oncomplete
                )
            self._needlight_pix = (args[0][0], args[0][1])
            self._issingleclick = True
            # NOTE: call should be here, but need a refined pixel radius, than this hardcoded;
            #       'add_light_selection' is called after ray casting, so it has more inclusive check
            # self.fin_set_lights(
            #     self.l_lights_inside_rect(viewport_api, [
            #         [args[0][0] - 4, args[0][1] + 4 ],
            #         [args[0][0] + 4, args[0][1] - 4 ] ]),
            #     self._pickingmode)

    def calc_distance_to_light(self, viewport_api, light_path):
        if light_path not in self.lightmanipulators:
            return float("inf")
        manipulator = self.lightmanipulators[light_path]
        transform = manipulator.model.get_as_floats(manipulator.model.get_item("transform"))
        worldpos_light = Gf.Vec3d(transform[12], transform[13], transform[14])
        worldpos_camera = viewport_api.transform.Transform(Gf.Vec3d(0, 0, 0))
        return (worldpos_light - worldpos_camera).GetLength()

    # Request a light on a click
    def add_light_selection(self, viewport_api, pixel_loc, distance_limit, light_path):
        if self._needlight_pix is None or not self._issingleclick:
            return
        if self._needlight_pix[0] != pixel_loc[0] or self._needlight_pix[1] != pixel_loc[1]:
            return
        self._needlight_pix = None
        if (
            LIGHT_SELECTION_WITH_DEPTH_TEST
            and self.calc_distance_to_light(self._viewport_api, light_path) > distance_limit
        ):
            return
        self.fin_set_lights([light_path], self._pickingmode)

    def on_selection_changed(self, context: omni.usd.UsdContext, viewport_api, light_manipulators):
        hdremix_highlight_paths(context.get_selection().get_selected_prim_paths())


GlobalSelection._instance = GlobalSelection()  # noqa: PLW0212
