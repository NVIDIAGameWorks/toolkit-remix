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

from typing import Any

import omni.usd
from omni.kit.manipulator.selection import SelectionManipulator, SelectionMode

from .global_selection import GlobalSelection
from .interface.i_manipulator import IManipulator


class SelectionDefault(IManipulator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__selection_args = None
        self.__selection_start_paths = None
        self.__selection_start_manipulator_token = None

    def __reset_state(self):
        self.__selection_args = None
        self.__selection_start_paths = None
        self.__selection_start_manipulator_token = None

    def _create_manipulator(self):
        return SelectionManipulator()

    def __get_selected_paths(self):
        usd_context = self.viewport_api.usd_context
        if not usd_context:
            return []
        return list(usd_context.get_selection().get_selected_prim_paths())

    def __is_single_click(self, args):
        return args[0][0] == args[1][0] and args[0][1] == args[1][1]

    def __was_consumed_by_another_layer(self, args):
        selection_manager = GlobalSelection.get_instance()
        if not self.__is_single_click(args) or self.__selection_start_paths is None:
            return False
        paths_changed = self.__get_selected_paths() != self.__selection_start_paths
        manipulator_consumed = selection_manager.consume_manipulator_selection(
            self.__selection_start_manipulator_token, args
        )
        return paths_changed or manipulator_consumed

    def __handle_selection(self, ndc_rect, mode):
        if self.__selection_start_paths is None:
            self.__selection_start_paths = self.__get_selected_paths()
            self.__selection_start_manipulator_token = GlobalSelection.get_instance().manipulator_selection_token
        # Map the NDC screen coordinates into texture space
        box_start, _start_in = self.viewport_api.map_ndc_to_texture_pixel((ndc_rect[0], ndc_rect[1]))
        box_end, _end_in = self.viewport_api.map_ndc_to_texture_pixel((ndc_rect[2], ndc_rect[3]))
        # Clamp selection box to texture in pixel-space
        resolution = self.viewport_api.resolution
        box_start = (max(0, min(resolution[0], box_start[0])), max(0, min(resolution[1], box_start[1])))
        box_end = (max(0, min(resolution[0], box_end[0])), max(0, min(resolution[1], box_end[1])))
        # If the selection box overlaps the Viewport, save the state; otherwise clear it
        if (box_start[0] < resolution[0]) and (box_end[0] > 0) and (box_start[1] > 0) and (box_end[1] < resolution[1]):
            self.__selection_args = box_start, box_end, mode
        else:
            self.__selection_args = None

    def __request_pick(self):
        if self.__selection_start_paths is None:
            return

        # If not selection state (pick is 100% outside of the viewport); clear the UsdContext's selection
        if self.__selection_args is None:
            usd_context = self.viewport_api.usd_context
            if usd_context:
                usd_context.get_selection().set_selected_prim_paths([], False)
            return

        args = self.__selection_args
        consumed = self.__was_consumed_by_another_layer(args)
        if consumed:
            return
        GlobalSelection.get_instance().add_prim_selection(self.viewport_api, args)

    def _model_changed(self, model, item):
        # https://gitlab-master.nvidia.com/omniverse/kit/-/merge_requests/13725
        if not hasattr(omni.usd, "PickingMode"):
            import carb  # noqa: PLC0415

            carb.log_error("No picking support in omni.hydratexture")
            return

        # We only care about rect and mode changes
        if item != model.get_item("ndc_rect") and item != model.get_item("mode"):
            return

        live_select = False
        ndc_rect = model.get_as_floats("ndc_rect")
        if not ndc_rect:
            if not live_select:
                self.__request_pick()
            self.__reset_state()
            return

        # Convert the mode into an omni.usd.PickingMode
        mode = model.get_as_ints("mode")
        if not mode:
            self.__reset_state()
            return
        mode = {
            SelectionMode.REPLACE: omni.usd.PickingMode.RESET_AND_SELECT,
            SelectionMode.APPEND: omni.usd.PickingMode.MERGE_SELECTION,
            SelectionMode.REMOVE: omni.usd.PickingMode.INVERT_SELECTION,
        }.get(mode[0])
        if mode is None:
            self.__reset_state()
            return

        self.__handle_selection(ndc_rect, mode)

        # For reset selection, we can live-select as the drag occurs
        # live_select = mode == omni.usd.PickingMode.RESET_AND_SELECT
        if live_select:
            self.__request_pick()
        return

    @property
    def categories(self):
        return ["manipulator"]

    @property
    def name(self):
        return "Selection"


def selection_default_factory(desc: dict[str, Any]):
    return SelectionDefault(desc.get("viewport_api"))
