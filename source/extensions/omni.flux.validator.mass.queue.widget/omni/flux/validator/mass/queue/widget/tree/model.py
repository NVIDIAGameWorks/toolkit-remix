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

import asyncio
from datetime import datetime
from enum import Enum
from functools import partial
from typing import TYPE_CHECKING, Any, Callable, List, Optional

import omni.ui as ui
import omni.usd
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import deferred_destroy_tasks as _deferred_destroy_tasks
from omni.flux.validator.manager.widget import ValidatorManagerWidget as _ValidatorManagerWidget
from omni.ui import color as cl

if TYPE_CHECKING:
    from omni.flux.validator.manager.core import ManagerCore as _ManagerCore
    from omni.flux.validator.manager.core import ValidationSchema as _ValidationSchema

HEADER_DICT = {0: "Items", 1: "Progress", 2: "Date", 3: "Actions"}


class Actions(Enum):
    SHOW_VALIDATION = "show_validation"


class _CustomProgressValueModel(ui.AbstractValueModel):
    def __init__(self, value: float):
        super().__init__()
        self._value = value
        self._message = ui.SimpleStringModel("")

    def set_value(self, value: float):
        """Reimplemented set"""
        try:
            value = float(value)
        except ValueError:
            value = None
        value_changed = False
        if value != self._value:
            # Tell the widget that the model is changed
            self._value = value / 100
            value_changed = True
        if value_changed:
            self._value_changed()

    @property
    def message(self) -> ui.SimpleStringModel:
        return self._message

    @message.setter
    def message(self, message: str):
        self._message.set_value(message)

    def get_value_as_float(self):
        return self._value

    def get_value_as_string(self):
        return f"{self._value * 100:.2f}"


class Item(ui.AbstractItem):
    """Item of the model"""

    def __init__(self, data: "_ManagerCore"):
        super().__init__()
        self._data = data
        self._is_finished = False
        self._finish_result = False
        self._creation_date = datetime.now()
        self.progress_color_attr = f"progress_color_{id(self)}"
        self.progress_model = _CustomProgressValueModel(0.0)
        self.display_model = ui.SimpleStringModel(data.model.name)
        self._sub_run_progress = data.subscribe_run_progress(self.set_progress)
        self._sub_run_finished = data.subscribe_run_finished(self._run_finished)
        self._validation_widget = None
        self.__on_mass_queue_action_pressed = _Event()

    @property
    def schema_uuid(self):
        return self._data.model.uuid

    def update_schema(self, schema: "_ValidationSchema"):
        self._data.update_model(schema)

    def subscribe_mass_queue_action_pressed(self, callback: Callable[["Item", str, Optional[Any]], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_mass_queue_action_pressed, callback)

    def build_validation_widget_ui(self, use_global_style: bool = False):
        self._validation_widget = _ValidatorManagerWidget(core=self._data, use_global_style=use_global_style)

    def subscribe_run_finished(self, callback: Callable[[bool, Optional[str]], Any]):
        return self._data.subscribe_run_finished(callback)

    def subscribe_run_progress(self, callback: Callable[[float], Any]):
        return self._data.subscribe_run_progress(callback)

    @property
    def validation_widget(self):
        return self._validation_widget

    def build_actions_ui(self):
        """Ui that will expose controllers"""
        pass

    def set_progress(self, progress: float):
        self.progress_model.set_value(progress)
        self.progress_changed()

    def _run_finished(self, result, message: Optional[str] = None):
        if not result:
            self.progress_changed(result=False)
        if message is not None:
            self.progress_model.message = message
        self._is_finished = True
        self._finish_result = result

    @property
    def is_finished(self):
        return self._is_finished

    @property
    def finish_result(self):
        return self._finish_result

    def progress_changed(self, result: bool = True):
        progress_value = self.progress_model.get_value_as_float()
        red = (1 - progress_value) * 0.6
        green = progress_value * 0.6
        if not result:
            red = 0.6
            green = 0.0
        setattr(cl, self.progress_color_attr, cl(red, green, 0, 1.0))

    def mass_build_queue_action_ui(
        self, default_actions: List[Callable[[], Any]], callback: Callable[[str], Any]
    ) -> Any:
        """
        Default exposed action for Mass validation. The UI will be built into the delegate of the mass queue.
        """
        self._data.mass_build_queue_action_ui(default_actions, callback)

    @property
    def creation_date(self):
        return self._creation_date

    @property
    def display_name(self):
        return self._data.model.name

    @property
    def display_name_tooltip(self):
        return self._data.model.data["name_tooltip"] if self._data.model.data else self._data.model.name

    def can_item_have_children(self, item: "Item") -> bool:
        """
        Define if the item can have children or not

        Args:
            item: the item itself

        Returns:
            If the item can has a children or not
        """
        return False

    def on_mass_queue_action_pressed(self, action_name: str, **kwargs):
        """Called when the user click with the left mouse button"""
        self.__on_mass_queue_action_pressed(self, action_name, **kwargs)

    def on_mouse_hovered(self, hovered):
        """Called when the user click with the left mouse button"""
        print(f"Mouse hovered {hovered}")

    def __repr__(self):
        return self._data.model.name


class Model(ui.AbstractItemModel):
    """Basic list model"""

    def __init__(self):
        super().__init__()
        self.__items = []
        self.__all_finish_value = {}
        self.__sub_item_finish = {}
        self.__consumer_update_item_task = None
        self.__update_item_task = None
        self.__queue_update_item = asyncio.Queue()
        self.__queue_schema_update_item = {}
        self.__pause_update_item_queue = False
        self._sub_item_changed = self.subscribe_item_changed_fn(self._on_item_changed)
        self.__on_progress = _Event()

    def subscribe_progress(self, callback: Callable[[float, bool], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_progress, callback)

    def __update_all_finish_value(self, item: Item, value: bool, message: Optional[str] = None):
        self.__all_finish_value[id(item)] = value
        self._update_progress()

    def _update_progress(self):
        if not self.__items:
            self.__on_progress(0.0, True)
            return
        self.__on_progress(
            (100 / len(self.__items) * len(self.__all_finish_value.keys())) / 100, all(self.__all_finish_value.values())
        )

    def _on_item_changed(self, _model: "Model", _items: List[Item]):
        self.__sub_item_finish = {}
        self.__all_finish_value = {}
        for item in self.__items:
            self.__sub_item_finish[id(item)] = item.subscribe_run_finished(
                partial(self.__update_all_finish_value, item)
            )
            if item.is_finished:
                self.__all_finish_value[id(item)] = item.finish_result
        self._update_progress()

    def add_schema_in_update_item_queue(self, schema: "_ValidationSchema"):
        """
        Add a schema into a queue. Use the dictionary to track what was the last schema added in the queue.

        Args:
            schema: the updated schema to use for the update
        """
        if schema.uuid in self.__queue_schema_update_item:
            self.__queue_schema_update_item[schema.uuid].append(schema)
        else:
            self.__queue_schema_update_item[schema.uuid] = [schema]
        self.__queue_update_item.put_nowait(schema)

    def update_item(self):
        """
        Update an item from a given schema that has the same UUID.
        """
        if self.__update_item_task and not self.__update_item_task.done():
            return
        self.__update_item_task = asyncio.ensure_future(self.__async_update_items())

    def pause_update_item_queue(self, value: bool):
        """
        Pause the update of the item(s).
        """
        self.__pause_update_item_queue = value

    @omni.usd.handle_exception
    async def __async_update_items(self):
        """
        Run in async to be sure that the previous task is done before to start a new one.
        """
        # If the consumer task was not created, or the previous one is done, we create a new one to consume the queue
        if not self.__consumer_update_item_task or (
            self.__consumer_update_item_task and self.__consumer_update_item_task.done()
        ):
            self.__consumer_update_item_task = asyncio.create_task(self._consume_update_item())

        # wait for all items from the queue to be processed
        await self.__queue_update_item.join()

    @omni.usd.handle_exception
    async def _consume_update_item(self):
        # Run the consume loop to consume the queue
        while True:
            if self.__pause_update_item_queue:
                # we kill the consumer task
                return
            # get an item in the queue
            schema = await self.__queue_update_item.get()
            # throw away schema update we don't need to consume. Consume only the last update schema
            if (
                schema.uuid in self.__queue_schema_update_item
                and self.__queue_schema_update_item[schema.uuid][-1] == schema
            ):
                # find the item in the tree
                for item in self.__items:
                    if item.schema_uuid == schema.uuid:
                        item.update_schema(schema)
                        break
            # mark the task as done for the item
            self.__queue_update_item.task_done()

    def add_items(self, items: List[Item]):
        """Set the items to show"""
        self.__items.extend(items)
        self._item_changed(None)

    def remove_items(self, items: List[Item]):
        """Set the items to show"""
        for item in items:
            if item not in self.__items:
                continue
            self.__items.remove(item)
        self._item_changed(None)

    def get_item_children(self, item: Optional[Item]):
        """Returns all the children when the widget asks it."""
        if item is None:
            return self.__items
        return []

    def get_item_value_model_count(self, item: Item):
        """The number of columns"""
        return len(HEADER_DICT.keys())

    def get_item_value_model(self, item, column_id):
        """
        Return value model.
        It's the object that tracks the specific value.
        In our case we use ui.SimpleStringModel.
        """
        if item is None:
            return self.__items
        if column_id == 0:
            return item.display_model
        return None

    def destroy(self):
        asyncio.ensure_future(self.deferred_destroy())

    @omni.usd.handle_exception
    async def deferred_destroy(self):
        await _deferred_destroy_tasks([self.__consumer_update_item_task, self.__update_item_task])
        self.__queue_schema_update_item = {}
        self.__items = []
