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
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.collapsable_frame import (
    PropertyCollapsableFrameWithInfoPopup as _PropertyCollapsableFrameWithInfoPopup,
)
from omni.flux.utils.widget.label import create_label_with_font as _create_label_with_font


class AssetExportPane:
    def __init__(self, context_name: str):
        """Nvidia StageCraft Components Pane"""

        self._default_attr = {
            "_root_frame": None,
            "_asset_file_collapsable_frame": None,
            "_asset_file_provider": None,
            "_asset_file_field": None,
            "_overlay_file_label": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context = omni.usd.get_context(context_name)
        self.__create_ui()

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

                            self._asset_file_collapsable_frame = _PropertyCollapsableFrameWithInfoPopup(
                                "ASSET EXPORT",
                                info_text=("The asset file that you want to export"),
                            )
                            with self._asset_file_collapsable_frame:
                                with ui.VStack():
                                    ui.Spacer(height=ui.Pixel(8))
                                    with ui.HStack(height=ui.Pixel(24), spacing=ui.Pixel(8)):
                                        with ui.HStack(width=ui.Percent(40)):
                                            ui.Spacer()
                                            with ui.VStack(width=0):
                                                ui.Spacer()
                                                self._asset_file_provider, _, _ = _create_label_with_font(
                                                    "File ", "PropertiesWidgetLabel", remove_offset=False
                                                )
                                                ui.Spacer()
                                        with ui.HStack():
                                            ui.Spacer(width=ui.Pixel(4))
                                            with ui.ZStack():
                                                self._asset_file_field = ui.StringField(
                                                    height=ui.Pixel(18), style_type_name_override="Field"
                                                )
                                                with ui.HStack():
                                                    ui.Spacer(width=ui.Pixel(8))
                                                    with ui.Frame(width=ui.Pixel(134), horizontal_clipping=True):
                                                        self._overlay_file_label = ui.Label(
                                                            "File path...",
                                                            name="USDPropertiesWidgetValueOverlay",
                                                            width=0,
                                                        )
                                                # self._sub_capture_dir_field_begin_edit = (
                                                #     self._capture_dir_field.model.subscribe_begin_edit_fn(
                                                #         self._on_capture_dir_field_begin
                                                #     )
                                                # )
                                                # self._sub_capture_dir_field_end_edit = (
                                                #     self._capture_dir_field.model.subscribe_end_edit_fn(
                                                #         self._on_capture_dir_field_end
                                                #     )
                                                # )
                                                # self._sub_capture_dir_field_changed = (
                                                #     self._capture_dir_field.model.subscribe_value_changed_fn(
                                                #         self._on_capture_dir_field_changed
                                                #     )
                                                # )
                                            ui.Spacer(width=ui.Pixel(8))
                                            with ui.VStack(width=ui.Pixel(20)):
                                                ui.Spacer()
                                                ui.Image(
                                                    "",
                                                    name="OpenFolder",
                                                    height=ui.Pixel(20),
                                                    # mouse_pressed_fn=lambda x, y, b, m: self._on_capture_dir_pressed(b),  # noqa E501
                                                )
                                                ui.Spacer()

                    ui.Spacer()

    def show(self, value):
        self._root_frame.visible = value

    def destroy(self):
        _reset_default_attrs(self)
