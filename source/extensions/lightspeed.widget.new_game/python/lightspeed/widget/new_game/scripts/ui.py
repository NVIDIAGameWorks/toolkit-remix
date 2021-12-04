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
from lightspeed.widget.content_viewer.scripts.core import ContentData, ContentDataAdd

if typing.TYPE_CHECKING:
    from .core import GameCore


from pathlib import Path

import omni.ui as ui  # TODO: menu, switch to the new method when Kit switched

from .usd_file_picker import open_file_picker

DEFAULT_CUSTOM_SENSOR_ENABLED = "/exts/omni.drivesim.scenario.tool.content_type_sensor/default_custom_sensor_enabled"
DEFAULT_CUSTOM_SENSOR_USD = "/exts/omni.drivesim.scenario.tool.content_type_sensor/default_custom_sensor_usd"
DEFAULT_CUSTOM_SENSOR_USD_PRIM = "/exts/omni.drivesim.scenario.tool.content_type_sensor/default_custom_sensor_usd_prim"


class GameContentItem(ContentItem):
    MULTI_SELECTION = False


class GameViewer(ContentViewer):

    GRID_COLUMN_WIDTH = 165
    GRID_ROW_HEIGHT = 165
    ENABLE_ADD_ITEM = True
    CONTENT_ITEM_TYPE = GameContentItem

    def __init__(self, core: "GameCore", extension_path: str):
        """Window to list all maps"""
        super(GameViewer, self).__init__(core, extension_path)
        self._settings = carb.settings.get_settings()

    @property
    def default_attr(self):
        result = super(GameViewer, self).default_attr
        result.update({"_label_game": None, "_game_executable_field": None, "_game_name_field": None})
        return result

    @property
    def style(self):
        style = super(GameViewer, self).style
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

    def _on_selection_changed(self, contents_data: List[ContentData]):
        super()._on_selection_changed(contents_data)
        if not contents_data:
            self._label_game.text = ""
            self._core.set_current_game(None)
            self._frame_buttons.clear()
            return
        if contents_data and isinstance(contents_data[0], ContentData):
            # multi selection is off, so only the first one
            self._label_game.text = contents_data[0].title
            self._core.set_current_game(contents_data[0])
            self._frame_buttons.clear()
        else:
            self._label_game.text = ""
            with self._frame_buttons:
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
                                                with ui.HStack(height=row_height, spacing=8):
                                                    ui.Spacer(width=sub_width)
                                                    ui.Label("Game executable", width=sub_label_width)
                                                    self._game_executable_field = ui.StringField()
                                                    ui.Image(
                                                        str(
                                                            self._get_icon_path(
                                                                "folder_open", from_base_extension=False
                                                            )
                                                        ),
                                                        width=row_height,
                                                        name="SavePath",
                                                        mouse_released_fn=lambda x, y, b, m: self._on_game_executable(
                                                            # noqa E501
                                                            b,
                                                            m,
                                                        ),
                                                    )
                                                with ui.HStack(height=row_height, spacing=8):
                                                    ui.Spacer(width=sub_width)
                                                    ui.Label("Name", width=sub_label_width)
                                                    self._game_name_field = ui.StringField()
                                            ui.Spacer(width=8)
                                        ui.Spacer(height=8)

                            ui.Spacer(width=8)
                        ui.Spacer(height=8)

    def create_ui(self):
        """Create the main UI"""
        with ui.Frame(style=self.style):
            with ui.VStack():
                self._create_ui()
                self._frame_buttons = ui.Frame(height=0)

        with self.get_top_frame():
            self._label_game = ui.Label("", name="vehicle")

    def _on_game_executable(self, b, m):
        if b != 0:
            return

        open_file_picker(self._set_game_executable_str_field, lambda *args: None)

    def _set_game_executable_str_field(self, path):
        if not path:
            return
        path_obj = Path(path)
        data = ContentDataAdd(title=path_obj.stem.capitalize(), path=path)
        self._game_executable_field.model.set_value(data.path)
        # set the game name automatically
        self._game_name_field.model.set_value(data.title)
        self._core.set_current_game(data)

    @property
    def calling_extension_path(self):
        current_path = Path(__file__).parent
        for _ in range(4):
            current_path = current_path.parent
        return current_path
