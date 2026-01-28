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

from typing import TYPE_CHECKING

import omni.usd
from lightspeed.hydra.remix.core import (
    hdremix_highlight_paths,
    hdremix_objectpicking_request,
    hdremix_uselegacyselecthighlight,
)
from pxr import Gf

if TYPE_CHECKING:
    from omni.ui import scene as sc

HDREMIX_LEGACY_OBJECT_PICKING_HIGHLIGHTING = hdremix_uselegacyselecthighlight() != 0

# NOTE: it's not clear how distance_limit in add_manipulator_selection() is calculated
# (usually it's ~3 units further, plus depth test is again broken?)
LIGHT_SELECTION_WITH_DEPTH_TEST = False


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
        self._picking_mode = omni.usd.PickingMode.RESET_AND_SELECT
        self._need_manipulator_pix = None
        self._is_single_click = True
        self._cur_manipulators = []
        self._manipulators_by_category: dict[str, dict[str, sc.Manipulator]] = {}
        self._manipulators: dict[str, sc.Manipulator] = {}

    @staticmethod
    def get_instance():
        return GlobalSelection._instance

    def set_manipulators(self, manipulators, category="lights"):
        """Replace the manipulators for the given category and update the cache of all manipulators"""
        self._manipulators_by_category[category] = manipulators
        all_manipulators = {}
        for manipulators_ in self._manipulators_by_category.values():
            all_manipulators.update(manipulators_)
        self._manipulators = all_manipulators

    def finalize_selection(self, picked_prims, picked_manipulators, picking_mode):
        """Finalize selection by setting the selected prims in the USD context"""
        usd_context = self._viewport_api.usd_context
        if usd_context:
            picked_prims = list(picked_prims)
            picked_manipulators = list(picked_manipulators)

            if self._is_single_click:
                # select single thing
                if len(picked_prims) > 1:
                    picked_prims = [picked_prims[0]]
                if len(picked_manipulators) > 1:
                    picked_manipulators = [picked_manipulators[0]]
                # if single click, prioritize a manipulator
                if len(picked_manipulators) > 0 and len(picked_prims) > 0:
                    picked_prims = []

            updated = l_apply_picking_mode(
                usd_context.get_selection().get_selected_prim_paths(), picked_prims + picked_manipulators, picking_mode
            )
            usd_context.get_selection().set_selected_prim_paths(updated, False)
        self._picking_mode = omni.usd.PickingMode.RESET_AND_SELECT
        self._cur_manipulators = []

    def fin_set_prims(self, pickedprims, pickingmode):
        self.finalize_selection(pickedprims, self._cur_manipulators, pickingmode)

    def fin_set_manipulator_paths(self, picked_manipulators):
        self._cur_manipulators = picked_manipulators

    # Called by HdRemix, when object picking request has been completed
    def objectpicking_oncomplete(self, selectedpaths):
        self.fin_set_prims(selectedpaths, self._picking_mode)

    # Called on manipulator click (and prim click if HDREMIX_LEGACY_OBJECT_PICKING_HIGHLIGHTING)
    def __on_query_complete(self, path, pos, *args):
        if HDREMIX_LEGACY_OBJECT_PICKING_HIGHLIGHTING:
            self.fin_set_prims([path], self._picking_mode)

    # Filter manipulators inside the rect
    def get_manipulators_inside_rect(self, viewport_api, rect):
        if self._manipulators is None:
            return []
        prim_paths = []
        for manipulator in self._manipulators.values():
            transform = manipulator.model.get_as_floats(manipulator.model.get_item("transform"))
            ndc_pos = viewport_api.world_to_ndc.Transform([transform[12], transform[13], transform[14]])
            if ndc_pos[2] > 1.0:
                # manipulator is behind camera
                continue
            pixel_loc, ret_viewport_api = viewport_api.map_ndc_to_texture_pixel(ndc_pos)
            if (
                ret_viewport_api
                and rect[0][0] <= pixel_loc[0] <= rect[1][0]
                and rect[1][1] <= pixel_loc[1] <= rect[0][1]
            ):
                # manipulator is inside the rect
                prim_paths.append(manipulator.model.get_prim_path())
        return list(prim_paths)

    # Request prim/manipulator pick in the rect (can be a click)
    def add_prim_selection(self, viewport_api, args):
        self._viewport_api = viewport_api
        self._picking_mode = args[2]
        if args[0][0] != args[1][0] or args[0][1] != args[1][1]:
            # box selection
            if HDREMIX_LEGACY_OBJECT_PICKING_HIGHLIGHTING:
                self._viewport_api.request_pick(args[0], args[1], args[2], "lightspeed_selection")
            else:
                hdremix_objectpicking_request(
                    args[0][0], args[0][1], args[1][0], args[1][1], self.objectpicking_oncomplete
                )
            self._need_manipulator_pix = None
            self._is_single_click = False
            self.fin_set_manipulator_paths(self.get_manipulators_inside_rect(viewport_api, args))
        else:
            # click selection
            if HDREMIX_LEGACY_OBJECT_PICKING_HIGHLIGHTING:
                self._viewport_api.request_query(args[0], self.__on_query_complete, "lightspeed_selection")
            else:
                hdremix_objectpicking_request(
                    args[0][0], args[0][1], args[0][0] + 1, args[0][1] + 1, self.objectpicking_oncomplete
                )
            self._need_manipulator_pix = (args[0][0], args[0][1])
            self._is_single_click = True
            # NOTE: call should be here, but need a refined pixel radius, than this hardcoded;
            #       'add_manipulator_selection' is called after ray casting, so it has more inclusive check
            # self.fin_set_manipulator_paths(
            #     self.get_manipulators_inside_rect(viewport_api, [
            #         [args[0][0] - 4, args[0][1] + 4 ],
            #         [args[0][0] + 4, args[0][1] - 4 ] ]),
            #     )

    def calc_distance_to_manipulator(self, viewport_api, manipulator_path):
        """
        Calculate the distance from the camera to the manipulator
        """
        if manipulator_path not in self._manipulators:
            return float("inf")
        manipulator = self._manipulators[manipulator_path]
        transform = manipulator.model.get_as_floats(manipulator.model.get_item("transform"))
        worldpos_manipulator = Gf.Vec3d(transform[12], transform[13], transform[14])
        worldpos_camera = viewport_api.transform.Transform(Gf.Vec3d(0, 0, 0))
        return (worldpos_manipulator - worldpos_camera).GetLength()

    # Request a manipulator on a click
    def add_manipulator_selection(self, viewport_api, pixel_loc, distance_limit, manipulator_path):
        if self._need_manipulator_pix is None or not self._is_single_click:
            return
        if self._need_manipulator_pix[0] != pixel_loc[0] or self._need_manipulator_pix[1] != pixel_loc[1]:
            return
        self._need_manipulator_pix = None
        if (
            LIGHT_SELECTION_WITH_DEPTH_TEST
            and self.calc_distance_to_manipulator(self._viewport_api, manipulator_path) > distance_limit
        ):
            return
        self.fin_set_manipulator_paths([manipulator_path])

    # TODO: This event may not need to be routed through this class
    def on_selection_changed(self, context: omni.usd.UsdContext, viewport_api, manipulators):
        hdremix_highlight_paths(context.get_selection().get_selected_prim_paths())


GlobalSelection._instance = GlobalSelection()  # noqa: SLF001
