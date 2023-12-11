"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from typing import Any, Dict

import omni.usd
from omni.kit.manipulator.selection import SelectionManipulator, SelectionMode

from .global_selection import GlobalSelection
from .interface.i_manipulator import IManipulator


class SelectionDefault(IManipulator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__selection_args = None

    def __reset_state(self):
        self.__selection_args = None

    def _create_manipulator(self):
        return SelectionManipulator()

    def __handle_selection(self, ndc_rect, mode):
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
        # If not selection state (pick is 100% outside of the viewport); clear the UsdContext's selection
        if self.__selection_args is None:
            usd_context = self.viewport_api.usd_context
            if usd_context:
                usd_context.get_selection().set_selected_prim_paths([], False)
            return

        args = self.__selection_args
        GlobalSelection.get_instance().add_prim_selection(self.viewport_api, args)

    def _model_changed(self, model, item):
        # https://gitlab-master.nvidia.com/omniverse/kit/-/merge_requests/13725
        if not hasattr(omni.usd, "PickingMode"):
            import carb

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
        }.get(mode[0], None)
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


def selection_default_factory(desc: Dict[str, Any]):
    manip = SelectionDefault(desc.get("viewport_api"))
    return manip
