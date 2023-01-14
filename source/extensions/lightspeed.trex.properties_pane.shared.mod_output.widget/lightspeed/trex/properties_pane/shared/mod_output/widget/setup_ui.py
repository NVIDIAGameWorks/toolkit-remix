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
from lightspeed.trex.mod_output_details.shared.widget import SetupUI as _ModOutputDetailsWidget
from lightspeed.trex.mod_output_file.shared.widget import SetupUI as _ModOutputFileWidget
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.collapsable_frame import (
    PropertyCollapsableFrameWithInfoPopup as _PropertyCollapsableFrameWithInfoPopup,
)


class ModOutputPane:
    def __init__(self, context_name: str = ""):
        """Nvidia StageCraft Components Pane"""

        self._default_attr = {
            "_context_name": None,
            "_root_frame": None,
            "_export_widget": None,
            "_export_collapsable_frame": None,
            "_export_details_widget": None,
            "_export_details_collapsable_frame": None,
            "_sub_directory_changed": None,
            "_stage_event": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name

        self.__create_ui()

        self._sub_directory_changed = self._export_widget.subscribe_directory_changed(
            self._export_details_widget.set_selected_directory
        )

        self._stage_event = (
            omni.usd.get_context()
            .get_stage_event_stream()
            .create_subscription_to_pop(self._on_stage_event, name="[lightspeed.lock_xform] Stage Event")
        )

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
                            self._export_collapsable_frame = _PropertyCollapsableFrameWithInfoPopup(
                                "MOD DIRECTORY",
                                info_text="File information for the mod to export.\n",
                                collapsed=False,
                            )
                            with self._export_collapsable_frame:
                                self._export_widget = _ModOutputFileWidget(self._context_name)

                            ui.Spacer(height=ui.Pixel(16))

                            self._export_details_collapsable_frame = _PropertyCollapsableFrameWithInfoPopup(
                                "EXISTING MOD FILE DETAILS",
                                info_text="Detailed information on the mod file located in the game ready assets "
                                "directory if it exists.\n",
                                collapsed=False,
                            )
                            with self._export_details_collapsable_frame:
                                self._export_details_widget = _ModOutputDetailsWidget()

    def _on_stage_event(self, event):
        if event.type in [
            int(omni.usd.StageEventType.SAVED),
            int(omni.usd.StageEventType.OPENED),
            int(omni.usd.StageEventType.CLOSED),
        ]:
            self.refresh()

    def refresh(self):
        self._export_widget.refresh()
        self._export_details_widget.refresh()

    def show(self, value):
        self._root_frame.visible = value
        if value:
            self.refresh()

    def destroy(self):
        _reset_default_attrs(self)
