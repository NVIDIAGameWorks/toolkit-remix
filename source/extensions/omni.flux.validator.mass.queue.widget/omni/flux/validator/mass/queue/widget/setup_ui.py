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

from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

import carb.input
import omni.ui as ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.validator.mass.queue.core import get_mass_validation_queue_instance as _get_mass_ingestion_queue_instance
from omni.ui import color as cl

from .tree.delegate import Delegate as _Delegate
from .tree.model import Item as _Item
from .tree.model import Model as _Model

if TYPE_CHECKING:
    from omni.flux.validator.manager.core import ManagerCore as _ManagerCore
    from omni.flux.validator.manager.core import ValidationSchema as _ValidationSchema


class MassQueueTreeWidget:
    def __init__(
        self,
        tree_model: Optional[_Model] = None,
        tree_delegate: Optional[_Delegate] = None,
        use_global_style: bool = False,
        style: Dict[str, Any] = None,
    ):
        """
        Panel outliner widget

        Args:
            tree_model: model that will feed the outliner (that is already initialized)
            tree_delegate: custom delegate (that should not be initialized)
            use_global_style: use the global style or the one from the extension
            style: if use_global_style is False, we use this dict
        """

        self._default_attr = {
            "_tree_model": None,
            "_tree_delegate": None,
            "_tree_view": None,
            "_subscribe_item_changed": None,
            "_sub_progress": None,
            "_progress_bar_widget": None,
            "_mass_queue_core": None,
            "_sub_update_item": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self.__queue_id = str(id(self))
        self._tree_model = _Model() if tree_model is None else tree_model
        self._tree_delegate = (
            _Delegate(use_global_style=use_global_style, style=style) if tree_delegate is None else tree_delegate
        )

        self.__create_ui()
        self._mass_queue_core = _get_mass_ingestion_queue_instance()
        self._sub_update_item = self._mass_queue_core.subscribe_on_update_item(self._update_items)

        self._sub_progress = self._tree_model.subscribe_progress(self._on_progress)

        self._tree_model.update_item()

    def get_queue_id(self):
        return self.__queue_id

    def _update_items(self, schema: "_ValidationSchema", queue_id: str | None = None):
        if queue_id is not None and queue_id != self.__queue_id:
            return
        # we add the schema into a queue
        self._tree_model.add_schema_in_update_item_queue(schema)

    def show(self, value: bool):
        """
        This function tell us if the widget is shown or not. When not, we pause any update of the items in the tree.
        When widget is shown, we update the items

        Args:
            value: value that tell us if we see the widget or not
        """
        self._tree_model.pause_update_item_queue(not value)
        if value:
            self._tree_model.update_item()

    def _on_progress(self, value: float, result: bool):
        self._progress_bar_widget.model.set_value(value)
        cl.mass_progress_bar_color = cl.validation_result_ok if result else cl.validation_result_failed

    def subscribe_selection_changed(self, callback: Callable[[List[_Item]], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Subscription that will let the plugin re-run a validation by itself.
        """
        return self._tree_view.set_selection_changed_fn(callback)

    def subscribe_item_changed(self, function: Callable[[_Model, List[_Item]], Any]):
        return self._tree_model.subscribe_item_changed_fn(function)

    @property
    def tree_model(self) -> _Model:
        return self._tree_model

    def add_items(self, cores: List["_ManagerCore"]):
        items = [_Item(core) for core in cores]
        self._tree_model.add_items(items)

    def _remove_selected_items(self):
        selection = self._tree_view.selection
        if not selection:
            return
        self._tree_model.remove_items(selection)

    def __create_ui(self):
        with ui.ZStack():
            with ui.VStack():
                with ui.ScrollingFrame(
                    name="PropertiesPaneSection",
                    horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                ):
                    with ui.ZStack():
                        ui.Rectangle(name="TreePanelBackground")
                        with ui.VStack(content_clipping=True):
                            ui.Spacer(height=ui.Pixel(4))
                            with ui.HStack():
                                ui.Spacer(width=ui.Pixel(4))
                                with ui.Frame(key_pressed_fn=self.__on_key_pressed):
                                    self._tree_view = ui.TreeView(
                                        self._tree_model,
                                        delegate=self._tree_delegate,
                                        root_visible=False,
                                        header_visible=True,
                                        columns_resizable=True,
                                        column_widths=[ui.Fraction(1), ui.Pixel(100), ui.Pixel(150), ui.Pixel(130)],
                                    )
                            ui.Spacer(height=ui.Pixel(20))
                ui.Spacer(height=ui.Pixel(8))
                with ui.HStack(height=ui.Pixel(24)):
                    ui.Spacer()
                    ui.Button("Remove Selection", clicked_fn=self._remove_selected_items, identifier="RemoveSelection")
                    ui.Spacer(width=ui.Percent(30))
                    cl.mass_progress_bar_color = cl.validation_result_default
                    self._progress_bar_widget = ui.ProgressBar(
                        width=ui.Percent(10), style={"color": cl.mass_progress_bar_color}
                    )
                    ui.Spacer(width=ui.Pixel(12))

    def __on_key_pressed(self, key, modifiers, is_down):
        if (
            key == int(carb.input.KeyboardInput.A)
            and modifiers == carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL
            and is_down
        ):
            self._tree_view.selection = self._tree_model.get_item_children(None)
        elif key == int(carb.input.KeyboardInput.DEL) and not is_down:
            self._remove_selected_items()

    def destroy(self):
        _reset_default_attrs(self)
