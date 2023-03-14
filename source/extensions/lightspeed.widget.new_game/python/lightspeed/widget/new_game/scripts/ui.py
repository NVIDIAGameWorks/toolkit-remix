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
from pathlib import Path
from typing import List

import carb
import carb.settings
from lightspeed.common.constants import CAPTURE_FOLDER
from lightspeed.widget.content_viewer.scripts.core import ContentData, ContentDataAdd
from lightspeed.widget.content_viewer.scripts.ui import ContentItem, ContentViewer
from lightspeed.widget.content_viewer.scripts.utils import is_path_readable

if typing.TYPE_CHECKING:
    from .core import GameCore

import omni.ui as ui  # TODO: menu, switch to the new method when Kit switched

from .relink.delegate import Delegate as RelinkTreeDelegate
from .relink.model import ListModel as RelinkTreeModel
from .usd_file_picker import open_file_picker


class GameContentItem(ContentItem):
    MULTI_SELECTION = False

    @property
    def style(self):
        style = super().style
        style.update(
            {
                "Image::Background": {"border_radius": 20},
                "Rectangle.Overlay": {
                    "background_color": 0x00FFFFFF,
                    "border_width": 1.0,
                    "border_color": 0x20FFFFFF,
                    "border_radius": 20,
                },
            }
        )
        return style

    @property
    def is_usd_path_valid(self):
        """Check is the USD path exist"""
        return self.content_data.is_path_valid


class GameViewer(ContentViewer):

    GRID_COLUMN_WIDTH = 100
    GRID_ROW_HEIGHT = 128
    ENABLE_ADD_ITEM = True
    CONTENT_ITEM_TYPE = GameContentItem

    def __init__(self, core: "GameCore", extension_path: str):
        """Window to list all maps"""
        super().__init__(core, extension_path)
        self._settings = carb.settings.get_settings()
        self._relink_tree_model = RelinkTreeModel()
        self._relink_tree_delegate = RelinkTreeDelegate()

    @property
    def default_attr(self):
        result = super().default_attr
        result.update(
            {
                "_label_game": None,
                "_game_capture_folder_field": None,
                "_game_name_field": None,
                "_relink_window": None,
                "_relink_tree_model": None,
                "_relink_tree_delegate": None,
                "_relink_tree": None,
            }
        )
        return result

    @property
    def style(self):
        style = super().style
        style.update(
            {
                "Button::relink": {"background_color": 0x70C5911A},
                "Label::vehicle": {"font_size": 22},
                "Label::relink": {"font_size": 22},
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
                "TreeView": {
                    "background_color": 0xFF23211F,
                    "background_selected_color": 0x664F4D43,
                    "secondary_color": 0xFF403B3B,
                },
                "TreeView.ScrollingFrame": {"background_color": 0xFF23211F},
                "TreeView.Header": {"background_color": 0xFF343432, "color": 0xFFCCCCCC, "font_size": 13},
                "TreeView.Item": {"color": 0xFF8A8777},
                "TreeView.Item:selected": {"color": 0xFF23211F},
                "TreeView.Item::NotValid": {"color": 0xFF0000B4},
                "TreeView:selected": {"background_color": 0xFF8A8777},
            }
        )
        return style

    def _on_selection_changed(self, contents_data: List[ContentData]):
        super()._on_selection_changed(contents_data)
        if not contents_data:
            self.CONTENT_ITEM_TYPE.MULTI_SELECTION = False
            self._label_game.text = ""
            self._core.set_current_game_capture_folder(None)
            self._frame_buttons.clear()
            self._frame_buttons.height = ui.Percent(0)
            return
        if contents_data and isinstance(contents_data[0], ContentData):
            # multi selection is off, so only the first one
            game_capture_path = Path(contents_data[0].path).resolve()
            if is_path_readable(str(game_capture_path)) and str(game_capture_path.name) == CAPTURE_FOLDER:
                self.CONTENT_ITEM_TYPE.MULTI_SELECTION = False
                if len(contents_data) > 1:
                    carb.log_warn("Only the first item from the selection will be selected")
                self._label_game.text = contents_data[0].title
                self._frame_buttons.clear()
            else:  # doesnt exist. We show the relink UI
                # relink UI can relink multiple captures in 1 click
                self.CONTENT_ITEM_TYPE.MULTI_SELECTION = True
                self._label_game.text = contents_data[0].title
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
                                            with ui.HStack(height=0):
                                                ui.Spacer(width=8)
                                                ui.Label("Relinker search and replace", name="relink")
                                            ui.Spacer(height=12)
                                            with ui.HStack():
                                                ui.Spacer(width=8)
                                                with ui.VStack(spacing=8):
                                                    with ui.HStack(height=row_height, spacing=8):
                                                        ui.Spacer(width=sub_width)
                                                        ui.Label("Search", width=sub_label_width)
                                                        self._relinker_game_capture_folder_search_field = (
                                                            ui.StringField()
                                                        )
                                                        self._relinker_game_capture_folder_search_field.model.set_value(
                                                            str(game_capture_path)
                                                        )
                                                    with ui.HStack(height=row_height, spacing=8):
                                                        ui.Spacer(width=sub_width)
                                                        ui.Label("Replace", width=sub_label_width)
                                                        self._relinker_game_capture_folder_replace_field = (
                                                            ui.StringField()
                                                        )
                                                        self._relinker_game_capture_folder_replace_field.model.set_value(  # noqa E501
                                                            str(game_capture_path)
                                                        )
                                                        ui.Image(
                                                            str(
                                                                self._get_icon_path(
                                                                    "folder_open", from_base_extension=False
                                                                )
                                                            ),
                                                            width=row_height,
                                                            name="SavePath",
                                                            mouse_released_fn=lambda x, y, b, m: self._on_relink_game_capture_folder(  # noqa E501
                                                                # noqa E501
                                                                b,
                                                                m,
                                                            ),
                                                        )
                                                    with ui.HStack(height=row_height, spacing=8):
                                                        ui.Spacer(width=ui.Percent(80))
                                                        ui.Button(
                                                            "Relink",
                                                            name="relink",
                                                            clicked_fn=self._on_relink_button_clicked,
                                                        )
                                                ui.Spacer(width=8)
                                            ui.Spacer(height=8)

                                ui.Spacer(width=8)
                            ui.Spacer(height=8)
        else:
            self._label_game.text = ""
            self.CONTENT_ITEM_TYPE.MULTI_SELECTION = False
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
                                                    ui.Label("Game capture folder", width=sub_label_width)
                                                    self._game_capture_folder_field = ui.StringField()
                                                    self._game_capture_folder_field.model.add_end_edit_fn(
                                                        self._on_game_capture_folder_edit
                                                    )
                                                    ui.Image(
                                                        str(
                                                            self._get_icon_path(
                                                                "folder_open", from_base_extension=False
                                                            )
                                                        ),
                                                        width=row_height,
                                                        name="SavePath",
                                                        mouse_released_fn=lambda x, y, b, m: self._on_game_capture_folder(  # noqa E501
                                                            # noqa E501
                                                            b,
                                                            m,
                                                        ),
                                                    )
                                                with ui.HStack(height=row_height, spacing=8):
                                                    ui.Spacer(width=sub_width)
                                                    ui.Label("Name", width=sub_label_width)
                                                    self._game_name_field = ui.StringField()
                                                    self._game_name_field.model.add_end_edit_fn(self._on_game_name_edit)
                                            ui.Spacer(width=8)
                                        ui.Spacer(height=8)

                            ui.Spacer(width=8)
                        ui.Spacer(height=8)
        self._core.set_current_game_capture_folder(contents_data[0])

    def create_ui(self):
        """Create the main UI"""
        with ui.Frame(style=self.style):
            with ui.VStack():
                self._create_ui()
                self._frame_buttons = ui.Frame(height=0)

        with self.get_top_frame():
            self._label_game = ui.Label("", name="vehicle")

        self.__create_relink_ui()

    def __create_relink_ui(self):
        window_name = "Relink check window"
        self._relink_window = ui.Window(
            window_name, name=window_name, width=900, height=600, visible=False, flags=ui.WINDOW_FLAGS_MODAL
        )

        with self._relink_window.frame:
            with ui.VStack(style=self.style):
                with ui.ScrollingFrame(
                    horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                    vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_ON,
                    style_type_name_override="TreeView",
                ):
                    self._relink_tree = ui.TreeView(
                        self._relink_tree_model,
                        delegate=self._relink_tree_delegate,
                        root_visible=False,
                        header_visible=True,
                        columns_resizable=True,
                    )
                with ui.Frame(height=20):
                    with ui.HStack():
                        ui.Spacer()
                        ui.Button(
                            text="Relink",
                            height=20,
                            width=80,
                            alignment=ui.Alignment.CENTER,
                            clicked_fn=self._do_relink,
                        )
                        ui.Spacer()

    def _on_relink_game_capture_folder(self, b, m):
        if b != 0:
            return
        open_file_picker(self._relink_game_capture_folder_str_field, lambda *args: None)

    def _relink_game_capture_folder_str_field(self, path):
        if not path:
            return
        self._relinker_game_capture_folder_replace_field.model.set_value(path)

    def _on_relink_button_clicked(self):
        search_value = self._relinker_game_capture_folder_search_field.model.get_value_as_string()
        replace_value = self._relinker_game_capture_folder_replace_field.model.get_value_as_string()
        selection = self._core.get_selection()
        self._relink_tree_model.refresh(selection, search_value, replace_value)
        self._relink_window.visible = True

    def _do_relink(self):
        self._relink_tree_model.relink()
        self._relink_window.visible = False
        self._core.set_selection(None)
        self._core.refresh_content()

    def _on_game_name_edit(self, model):
        value = model.get_value_as_string()
        if not value.strip():
            carb.log_error("Please add a game name!")
            return
        game_path = self._game_capture_folder_field.model.get_value_as_string()
        if game_path.strip() and Path(game_path).exists():
            data = ContentDataAdd(title=value, path=game_path)
            self._core.set_current_game_capture_folder(data)
        else:
            self._core.set_current_game_capture_folder(None)

    def _on_game_capture_folder_edit(self, model):
        value = model.get_value_as_string()
        if not value.strip() or not Path(value).exists():
            carb.log_error("Please select a game capture folder!")
            return
        game_name = self._game_name_field.model.get_value_as_string()
        if game_name.strip():
            data = ContentDataAdd(title=game_name, path=value)
            self._core.set_current_game_capture_folder(data)
        else:
            self._core.set_current_game_capture_folder(None)

    def _on_game_capture_folder(self, b, m):
        if b != 0:
            return

        open_file_picker(self._set_game_capture_folder_str_field, lambda *args: None)

    def _set_game_capture_folder_str_field(self, path):
        if not path:
            return
        data = ContentDataAdd(title="MyGame", path=path)
        self._game_capture_folder_field.model.set_value(data.path)
        # set the game name automatically
        self._game_name_field.model.set_value(data.title)
        self._core.set_current_game_capture_folder(data)

    @property
    def calling_extension_path(self):
        current_path = Path(__file__).parent
        for _ in range(4):
            current_path = current_path.parent
        return current_path
