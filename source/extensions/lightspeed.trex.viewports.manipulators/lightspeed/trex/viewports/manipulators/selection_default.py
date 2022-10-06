"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import omni.usd
from omni.kit.manipulator.selection import SelectionManipulator, SelectionMode

from .i_manipulator import IManipulator


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
        box_start, start_in = self.viewport_api.map_ndc_to_texture_pixel((ndc_rect[0], ndc_rect[1]))
        box_end, end_in = self.viewport_api.map_ndc_to_texture_pixel((ndc_rect[2], ndc_rect[3]))
        # If either start or end cordinates are in the Viewport, save the state
        if start_in or end_in:
            self.__selection_args = box_start, box_end, mode
        else:
            self.__selection_args = None

    def __request_pick(self, *args):
        self.viewport_api.request_pick(*args)

    def _model_changed(self, model, item) -> None:
        # We only care about rect and mode changes
        if item != model.get_item("ndc_rect") and item != model.get_item("mode"):
            return

        live_select = False
        ndc_rect = model.get_as_floats("ndc_rect")
        # when we release the mouse, we select under the mouse and reset the values
        if not ndc_rect:
            if not live_select and self.__selection_args:
                self.__request_pick(*self.__selection_args)
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

        # when we drag the mouse without to release, we select "in live"
        self.__handle_selection(ndc_rect, mode)
        if live_select and self.__selection_args:
            self.__request_pick(*self.__selection_args)
        return

    def destroy(self):
        pass
