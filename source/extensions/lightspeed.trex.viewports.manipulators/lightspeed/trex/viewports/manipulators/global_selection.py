"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""

import omni.usd
from pxr import Gf


# Omniverse Scene View doesn't currently have any good way to resolve selection between layers - in our case,
# the Hydra Delegate responsible for mesh selection, and the OpenGLSceneView with the light gizmo layers.
# to fix it, we route all selection queries through this class, manually check the OpenGLSceneView selection first,
# then the Hydra Delegate selection.  For box selection, we have to let the Hydra Delegate resolve the box selection
# first, listen for that change, then add the light selection.
class GlobalSelection:
    def __init__(self):
        self._light_selection = None
        self._box_args = None
        self._viewport_api = None
        self._selection_mode = omni.usd.PickingMode.RESET_AND_SELECT

    @staticmethod
    def get_instance():
        return GlobalSelection._instance

    def __on_query_complete(self, path, pos, *args):
        world_space_camera = self._viewport_api.transform.Transform(Gf.Vec3d(0, 0, 0))
        distance = (Gf.Vec3d(*pos) - world_space_camera).GetLength()

        if self._light_selection and self._light_selection[0] < distance:
            path = self._light_selection[1]

        self._box_args = None

        usd_context = self._viewport_api.usd_context
        if usd_context:
            selection = usd_context.get_selection().get_selected_prim_paths()
            if self._selection_mode is omni.usd.PickingMode.RESET_AND_SELECT:
                if path:
                    selection = [path]
                else:
                    selection = []
            elif self._selection_mode is omni.usd.PickingMode.MERGE_SELECTION:
                if path not in selection:
                    selection.append(path)
            elif self._selection_mode is omni.usd.PickingMode.INVERT_SELECTION:
                if path in selection:
                    selection.remove(path)
                else:
                    selection.append(path)
            usd_context.get_selection().set_selected_prim_paths(selection, False)
        self._light_selection = None
        self._selection_mode = omni.usd.PickingMode.RESET_AND_SELECT

    def add_prim_selection(self, viewport_api, args):
        self._viewport_api = viewport_api
        self._selection_mode = args[2]
        if args[0][0] != args[1][0] or args[0][1] != args[1][1]:
            # box selection
            self._box_args = args
            self._viewport_api.request_pick(args[0], args[1], args[2], "lightspeed_selection")
        else:
            # click selection
            self._box_args = None
            self._viewport_api.request_query(args[0], self.__on_query_complete, "lightspeed_selection")

    def add_light_selection(self, viewport_api, pixel_loc, light_dist, light_path):
        if self._box_args is None:
            self._light_selection = (light_dist, light_path)
            self._viewport_api = viewport_api
            viewport_api.request_query(pixel_loc, self.__on_query_complete, "lightspeed_selection")

    def on_selection_changed(self, context: omni.usd.UsdContext, viewport_api, light_manipulators):
        if self._box_args is not None:
            # Filter lights to the ones inside the box
            lights = []
            for manipulator in light_manipulators:
                transform = manipulator.model.get_as_floats(manipulator.model.get_item("transform"))
                ndc_pos = viewport_api.world_to_ndc.Transform([transform[12], transform[13], transform[14]])
                if ndc_pos[2] > 1.0:
                    # light is behind camera
                    continue
                pixel_loc, ret_viewport_api = viewport_api.map_ndc_to_texture_pixel(ndc_pos)
                if (
                    ret_viewport_api
                    and self._box_args[0][0] <= pixel_loc[0] <= self._box_args[1][0]
                    and self._box_args[1][1] <= pixel_loc[1] <= self._box_args[0][1]
                ):
                    # light is inside the selection box
                    lights.append(manipulator.model.get_prim_path())

            # Add lights to selection
            selection = context.get_selection().get_selected_prim_paths()
            if (
                self._selection_mode is omni.usd.PickingMode.RESET_AND_SELECT
                or self._selection_mode is omni.usd.PickingMode.MERGE_SELECTION
            ):
                selection = selection + lights
            elif self._selection_mode is omni.usd.PickingMode.INVERT_SELECTION:
                for light in lights:
                    if light in selection:
                        selection.remove(light)
                    else:
                        selection.append(light)
            context.get_selection().set_selected_prim_paths(selection, False)
            self._box_args = None
            self._selection_mode = omni.usd.PickingMode.RESET_AND_SELECT


GlobalSelection._instance = GlobalSelection()  # noqa: PLW0212
