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

import functools
import re
from typing import TYPE_CHECKING, Any, Dict, Optional

import omni.ui as ui
from omni.flux.info_icon.widget import SelectableToolTipWidget as _SelectableToolTipWidget
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.ui import color as cl

from .model import HEADER_DICT, Actions  # noqa PLE0402

if TYPE_CHECKING:
    from .model import Item as _Item


class Delegate(ui.AbstractItemDelegate):
    """Delegate of the tree"""

    def __init__(self, use_global_style: bool = False, style: Dict[str, Any] = None):
        super().__init__()
        self._default_attrs = {
            "_show_validation_buttons": None,
            "_progress_message_widget": None,
            "_sub_progress_message_widget": None,
            "_sub_run_finished": None,
            "_show_validation_button_widget": None,
        }
        for attr, value in self._default_attrs.items():
            setattr(self, attr, value)
        self._use_global_style = use_global_style
        self._style = style
        self._sub_run_finished = {}
        self._show_validation_buttons = {}
        self._show_validation_button_widget = {}
        self._progress_message_widget = {}
        self._sub_progress_message_widget = {}

    def build_branch(self, model, item, column_id, level, expanded):
        """Create a branch widget that opens or closes subtree"""
        pass

    def build_widget(self, model, item: "_Item", column_id, level, expanded):
        """Create a widget per item"""
        if item is None:
            return
        frame = ui.Frame()
        if not self._use_global_style:
            if self._style is None:
                self._style = {}
            frame.set_style(self._style)
        with frame:
            if column_id == 0:
                with ui.VStack(
                    height=ui.Pixel(24),
                ):
                    ui.Spacer(height=ui.Pixel(4))
                    # regex that remove anything that is not a number or alphabet at the end of the string
                    ui.Label(
                        re.sub("_?[^a-zA-Z0-9]+$", "", item.display_name),
                        style_type_name_override="TreeView.Item",
                        tooltip=item.display_name_tooltip,
                        identifier="QueueJobLabel",
                    )
                    ui.Spacer(height=ui.Pixel(4))
            elif column_id == 1:
                with ui.HStack():
                    ui.Spacer(width=ui.Pixel(4))
                    setattr(
                        cl,
                        item.progress_color_attr,
                        getattr(cl, item.progress_color_attr) or cl(0.0, 0, 0, 1.0),
                    )
                    progress_bar_widget = ui.ProgressBar(
                        item.progress_model,
                        style={"border_radius": 5, "color": getattr(cl, item.progress_color_attr)},
                    )
                    self._progress_message_widget[id(item)] = _SelectableToolTipWidget(
                        progress_bar_widget, "Progress...", follow_mouse_pointer=True
                    )
                    self._sub_progress_message_widget[id(item)] = (
                        item.progress_model.message.subscribe_value_changed_fn(
                            functools.partial(self._on_progress_message_value_changed, item)
                        )
                    )
                    ui.Spacer(width=ui.Pixel(4))
            elif column_id == 2:
                with ui.HStack():
                    ui.Spacer(width=ui.Pixel(4))
                    ui.Label(item.creation_date.strftime("%d/%m/%Y %H:%M:%S"))
                    ui.Spacer(width=ui.Pixel(4))
            elif column_id == 3:
                with ui.HStack():
                    ui.Spacer(width=ui.Pixel(4))
                    with ui.HStack(height=ui.Pixel(16), spacing=4):
                        button = ui.ToolButton(
                            name="ShowValidation",
                            width=ui.Pixel(16),
                            height=ui.Pixel(16),
                            image_width=ui.Pixel(16),
                            image_height=ui.Pixel(16),
                            tooltip="Toggle in validation tab",
                            identifier="ToggleInValidationTab",
                        )
                        self._sub_run_finished[id(item)] = item.subscribe_run_finished(
                            functools.partial(self._on_run_finished, item)
                        )
                        button.set_clicked_fn(
                            functools.partial(
                                self._on_show_validation_widget, Actions.SHOW_VALIDATION.value, item, button
                            )
                        )
                        self._show_validation_buttons[button] = False
                        self._show_validation_button_widget[id(item)] = button
                        item.mass_build_queue_action_ui(
                            [
                                functools.partial(
                                    self._on_show_validation_widget,
                                    Actions.SHOW_VALIDATION.value,
                                    item,
                                    button,
                                    disable_toggle=True,
                                )
                            ],
                            functools.partial(self._on_mass_queue_action_pressed, item),
                        )
                        ui.Spacer()
                    ui.Spacer(width=ui.Pixel(4))

    def _on_progress_message_value_changed(self, item: "_Item", model: ui.AbstractValueModel) -> None:
        self._progress_message_widget[id(item)].set_message(model.get_value_as_string())

    def _on_item_hovered(self, hovered, item):
        item.on_mouse_hovered(hovered)

    def _on_mass_queue_action_pressed(self, item, action_name: str):
        item.on_mass_queue_action_pressed(action_name)

    def _on_show_validation_widget(self, action_name: str, item, button, disable_toggle: bool = False):
        if action_name == Actions.SHOW_VALIDATION.value:
            any_checked = False
            for _button, value in self._show_validation_buttons.items():
                if _button == button:
                    result = not value if not disable_toggle else True
                    _button.checked = result
                    any_checked = result
                    self._show_validation_buttons[_button] = result
                    continue
                _button.checked = False
                self._show_validation_buttons[_button] = False
            item.on_mass_queue_action_pressed(
                action_name, show_validation_checked=any_checked, force_show_frame=disable_toggle
            )

    def _on_run_finished(self, item: "_Item", value, message: Optional[str] = None):
        if id(item) not in self._show_validation_button_widget:
            return
        self._show_validation_button_widget[id(item)].name = "ShowValidation" if value else "ShowValidationFailed"

    def build_header(self, column_id):
        """Build the header"""
        style_type_name = "TreeView.Header"
        with ui.HStack():
            ui.Label(HEADER_DICT[column_id], style_type_name_override=style_type_name)

    def destroy(self):
        _reset_default_attrs(self)
