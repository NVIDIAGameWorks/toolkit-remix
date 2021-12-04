"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import typing
from typing import List

import carb.settings
from lightspeed.widget.content_viewer.scripts.ui import ContentItem, ContentViewer

if typing.TYPE_CHECKING:
    from .core import GameWorkspaceCore
    from lightspeed.widget.content_viewer.scripts.core import ContentData

from pathlib import Path

import omni.ui as ui  # TODO: menu, switch to the new method when Kit switched

from .usd_file_picker import open_file_picker

DEFAULT_CUSTOM_SENSOR_ENABLED = "/exts/omni.drivesim.scenario.tool.content_type_sensor/default_custom_sensor_enabled"
DEFAULT_CUSTOM_SENSOR_USD = "/exts/omni.drivesim.scenario.tool.content_type_sensor/default_custom_sensor_usd"
DEFAULT_CUSTOM_SENSOR_USD_PRIM = "/exts/omni.drivesim.scenario.tool.content_type_sensor/default_custom_sensor_usd_prim"


class ContentItemRig(ContentItem):
    MULTI_SELECTION = False


class GameWorkspaceViewer(ContentViewer):

    GRID_COLUMN_WIDTH = 165
    GRID_ROW_HEIGHT = 165
    CONTENT_ITEM_TYPE = ContentItemRig

    def __init__(self, core: "GameWorkspaceCore", extension_path: str):
        """Window to list all maps"""
        super(GameWorkspaceViewer, self).__init__(core, extension_path)
        self._settings = carb.settings.get_settings()
        self._subcription_current_game_changed = self._core.subscribe_current_game_changed(
            self._on_current_game_changed
        )

    @property
    def default_attr(self):
        result = super(GameWorkspaceViewer, self).default_attr
        result.update({"_label_game": None, "_use_existing_layer": None, "_replacement_layer_usd_field": None})
        return result

    @property
    def style(self):
        style = super(GameWorkspaceViewer, self).style
        style.update(
            {
                "Label::vehicle": {"font_size": 22},
                "Image::SavePath": {"color": 0x90FFFFFF},
                "Image::SavePath:hovered": {"color": 0xFFFFFFFF},
                "Rectangle::SubBackground0": {
                    "background_color": 0x60333333,
                    "border_width": 1.0,
                    "border_color": 0x20FFFFFF,
                },
                "Rectangle::SubBackground1": {
                    "background_color": 0x00333333,
                    "border_width": 1.0,
                    "border_color": 0x20FFFFFF,
                },
            }
        )
        return style

    def _on_selection_changed(self, contents_data: List["ContentData"]):
        super()._on_selection_changed(contents_data)
        if not contents_data:
            self._core.set_current_capture(None)
            return
        self._core.set_current_capture(contents_data[0])

    def _on_current_game_changed(self, data):
        self._label_game.text = f"{data.title} game capture(s):"

    def create_ui(self):
        """Create the main UI"""
        with ui.Frame(style=self.style):
            with ui.VStack():
                self._create_ui()
                with ui.ZStack(height=0):
                    ui.Rectangle(name="SubBackground0")
                    with ui.VStack():
                        ui.Spacer(height=8)
                        with ui.HStack():
                            ui.Spacer(width=8)
                            with ui.VStack(spacing=8):
                                row_height = 24
                                sub_width = ui.Pixel(50)
                                sub_label_width = ui.Pixel(100)
                                with ui.ZStack(height=0):
                                    ui.Rectangle(name="SubBackground1")
                                    with ui.VStack():
                                        ui.Spacer(height=8)
                                        with ui.HStack():
                                            ui.Spacer(width=8)
                                            with ui.VStack(spacing=8):
                                                with ui.HStack(height=row_height):
                                                    ui.Label(
                                                        "Use existing enhancements layer",
                                                        tooltip="If true, you can import an existing enhancements layer.",
                                                    )
                                                    self._use_existing_layer = ui.RadioCollection(width=36)
                                                    ui.RadioButton(radio_collection=self._use_existing_layer, text="No")
                                                    ui.RadioButton(
                                                        radio_collection=self._use_existing_layer, text="Yes"
                                                    )
                                                    self._use_existing_layer.model.add_value_changed_fn(
                                                        self.__update_use_existing_layer
                                                    )

                                                with ui.VStack(spacing=8):
                                                    with ui.HStack(height=row_height, spacing=8):
                                                        ui.Spacer(width=sub_width)
                                                        ui.Label("USD Path", width=sub_label_width)
                                                        self._replacement_layer_usd_field = ui.StringField()
                                                        self._replacement_layer_usd_field.model.add_value_changed_fn(
                                                            self.__update_replacement_layer_usd_field
                                                        )
                                                        ui.Image(
                                                            str(
                                                                self._get_icon_path(
                                                                    "folder_open", from_base_extension=False
                                                                )
                                                            ),
                                                            width=row_height,
                                                            name="SavePath",
                                                            mouse_released_fn=lambda x, y, b, m: self._on_existing_layer_usd_file(  # noqa E501
                                                                b, m
                                                            ),
                                                        )

                                            ui.Spacer(width=8)
                                        ui.Spacer(height=8)

                            ui.Spacer(width=8)
                        ui.Spacer(height=8)

        with self.get_top_frame():
            with ui.HStack():
                self._label_game = ui.Label("", name="vehicle")

    def __update_use_existing_layer(self, value_model):
        value = self._use_existing_layer.model.get_value_as_bool()
        self._core.set_current_use_existing_layer(value)

    def __update_replacement_layer_usd_field(self, value_model):
        value = self._replacement_layer_usd_field.model.get_value_as_string()
        self._core.set_current_replacement_layer_usd_path(value if value else None)

    def _on_existing_layer_usd_file(self, b, m):
        if b != 0:
            return

        open_file_picker(self._set_existing_layer_usd_str_field, lambda *args: None)

    def _set_existing_layer_usd_str_field(self, path):
        if not path:
            return
        self._replacement_layer_usd_field.model.set_value(path)

    @property
    def calling_extension_path(self):
        current_path = Path(__file__).parent
        for _ in range(4):
            current_path = current_path.parent
        return current_path
