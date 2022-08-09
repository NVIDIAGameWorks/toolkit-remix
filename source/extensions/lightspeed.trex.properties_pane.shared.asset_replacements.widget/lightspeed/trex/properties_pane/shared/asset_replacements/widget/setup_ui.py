"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import omni.ui as ui
import omni.usd
from lightspeed.trex.selection_tree.shared.widget import SetupUI as _SelectionTreeWidget
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.collapsable_frame import (
    PropertyCollapsableFrameWithInfoPopup as _PropertyCollapsableFrameWithInfoPopup,
)
from omni.flux.utils.widget.resources import get_fonts as _get_fonts


class AssetReplacementsPane:

    DEFAULT_CAPTURE_TREE_FRAME_HEIGHT = 200
    SIZE_PERCENT_MANIPULATOR_WIDTH = 50

    def __init__(self, context: omni.usd.UsdContext):
        """Nvidia StageCraft Components Pane"""

        self._default_attr = {
            "_root_frame": None,
            "_selection_tree_widget": None,
            "_mod_file_details_collapsable_frame": None,
            "_mesh_properties_collapsable_frame": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context = context
        self.__update_default_style()
        self.__create_ui()

    def __update_default_style(self):
        """
        This widget generate image from text. It needs to read keys from a the global style.
        If those keys doesn't exist, we add them here (or it will crash). With this, the widget will work even without
        global style that sets those keys
        """
        style = ui.Style.get_instance()
        current_dict = style.default
        if "ImageWithProvider::PropertiesPaneSectionTitle" not in current_dict:
            current_dict["ImageWithProvider::PropertiesPaneSectionTitle"] = {
                "color": 0xB3FFFFFF,
                "font_size": 13,
                "image_url": _get_fonts("Barlow-Bold"),
            }
        style.default = current_dict

    def __create_ui(self):
        self._root_frame = ui.Frame()
        with self._root_frame:
            with ui.ScrollingFrame(
                name="PropertiesPaneSection",
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
            ):
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(56))

                    with ui.HStack():
                        ui.Spacer(width=ui.Pixel(8), height=ui.Pixel(0))
                        with ui.VStack():
                            ui.Spacer(height=ui.Pixel(8))
                            self._mod_file_details_collapsable_frame = _PropertyCollapsableFrameWithInfoPopup(
                                "SELECTION",
                                info_text="Tree that will shows your current selection\n",
                                collapsed=False,
                            )
                            with self._mod_file_details_collapsable_frame:
                                self._selection_tree_widget = _SelectionTreeWidget(self._context)

                            ui.Spacer(height=ui.Pixel(16))

                            self._mesh_properties_collapsable_frame = _PropertyCollapsableFrameWithInfoPopup(
                                "MESH PROPERTIES",
                                info_text="Mesh properties of the selected mesh(es)",
                                collapsed=False,
                            )

    def show(self, value):
        self._root_frame.visible = value

    def destroy(self):
        _reset_default_attrs(self)
