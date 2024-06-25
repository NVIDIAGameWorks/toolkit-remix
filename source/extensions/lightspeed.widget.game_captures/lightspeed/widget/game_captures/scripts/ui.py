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

import typing
from pathlib import Path
from typing import List

from lightspeed.widget.content_viewer.scripts.ui import ContentItem, ContentViewer

if typing.TYPE_CHECKING:
    from .core import GameCapturesCore
    from lightspeed.widget.content_viewer.scripts.core import ContentData

import omni.ui as ui  # TODO: menu, switch to the new method when Kit switched


class ContentItemCapture(ContentItem):
    MULTI_SELECTION = False


class GameCapturesViewer(ContentViewer):

    GRID_COLUMN_WIDTH = 165
    GRID_ROW_HEIGHT = 165
    CONTENT_ITEM_TYPE = ContentItemCapture

    def __init__(self, core: "GameCapturesCore", extension_path: str):
        """Window to list all maps"""
        super().__init__(core, extension_path)
        self._subcription_current_game_changed = self._core.subscribe_current_game_capture_folder_changed(
            self._on_current_game_changed
        )

    @property
    def default_attr(self):
        result = super().default_attr
        result.update({"_label_game": None})
        return result

    @property
    def style(self):
        style = super().style
        style.update(
            {
                "Label::vehicle": {"font_size": 22},
                "Rectangle::SubBackground0": {
                    "background_color": 0x60333333,
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

        with self.get_top_frame():
            with ui.HStack():
                self._label_game = ui.Label("", name="vehicle")

    @property
    def calling_extension_path(self):
        current_path = Path(__file__).parent
        for _ in range(4):
            current_path = current_path.parent
        return current_path
