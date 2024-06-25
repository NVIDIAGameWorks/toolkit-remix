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

from typing import List, Optional, Union

import omni.ui as ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.validator.factory import CheckSchema as _CheckSchema
from omni.flux.validator.factory import ContextSchema as _ContextSchema
from omni.flux.validator.factory import ResultorSchema as _ResultorSchema
from omni.flux.validator.factory import SelectorSchema as _SelectorSchema
from omni.ui import color as cl

HEADER_DICT = {0: "Items"}


class CustomProgressValueModel(ui.AbstractValueModel):
    """An example of custom float model that can be used for progress bar"""

    def __init__(self, value: float, message: str, result: bool):
        super().__init__()
        self._value = value
        self._message = ui.SimpleStringModel(message)
        self._result = result

    def set_value(self, value, message, result):
        """Reimplemented set"""
        try:
            value = float(value)
        except ValueError:
            value = None
        value_changed = False
        if value != self._value:
            # Tell the widget that the model is changed
            self._value = value
            value_changed = True
        if message != self._message:
            self._message.set_value(message)
            value_changed = True
        if result != self._result:
            self._result = result
            value_changed = True
        if value_changed:
            self._value_changed()

    @property
    def message(self) -> ui.SimpleStringModel:
        return self._message

    @message.setter
    def message(self, message: str):
        self._message.set_value(message)

    def get_value_as_bool(self):
        return self._result

    def get_value_as_float(self):
        return self._value

    def get_value_as_string(self):
        return f"{self._message.get_value_as_string(): >10000}"  # 10000 to align right


class BaseItem(ui.AbstractItem):
    """Item of the model"""

    def __init__(self, plugin: _CheckSchema):
        super().__init__()
        self._plugin = plugin
        self._title = plugin.instance.display_name or plugin.name
        self.title_model = ui.SimpleStringModel(self._title)
        self.progress_color_attr = f"progress_color_{id(self)}"
        value, message, result = plugin.instance.get_progress()
        self.progress_model = CustomProgressValueModel(value, message, result)
        self.set_progress(value, message, result)
        self.__sub_progress = plugin.instance.subscribe_progress(self.set_progress)  # noqa

    @property
    def plugin(self):
        """The plugin that the item hold"""
        return self._plugin

    def set_progress(self, progress: float, message: str, result: bool):
        self.progress_model.set_value(progress, message, result)
        self.progress_changed()

    def progress_changed(self):
        progress_value = self.progress_model.get_value_as_float()
        red = (1 - progress_value) * 0.6
        green = progress_value * 0.6
        result = self.progress_model.get_value_as_bool()
        if not result:
            red = 0.6
            green = 0.0
        setattr(cl, self.progress_color_attr, cl(red, green, 0, 1.0))
        if not result and hasattr(self, "parent"):
            self.parent.set_progress(1.0, "Failed", result)

    @property
    def title(self):
        """Label to show on the UI"""
        return self._title

    def destroy(self):
        self.progress_model = None
        self.__sub_progress = None  # noqa
        self.title_model = None

    def __repr__(self):
        return f'"{self._title}"'


class UIItem(ui.AbstractItem):
    """Item of the model"""

    def __init__(
        self, plugin: Union[_CheckSchema, _SelectorSchema], parent: Union["SelectorItem", "CheckerItem", "ResultorItem"]
    ):
        super().__init__()
        self._plugin = plugin
        self.parent = parent

    @property
    def plugin(self):
        """The plugin that the item hold"""
        return self._plugin


class ContextItem(BaseItem):
    """Item of the model"""

    def __init__(self, plugin: _ContextSchema, parent: "CheckerItem" = None):
        super().__init__(plugin)
        self._title = f"Context: {plugin.instance.display_name or plugin.name}"
        self.parent = parent
        self._ui_items = [UIItem(plugin, self)]

    @property
    def ui_items(self):
        """The UI item to show for this item"""
        return self._ui_items

    def destroy(self):
        self._ui_items = None
        super().destroy()


class SelectorItem(BaseItem):
    """Item of the model"""

    def __init__(self, plugin: _SelectorSchema, parent: "CheckerItem"):
        super().__init__(plugin)
        self._title = f"Selector: {plugin.instance.display_name or plugin.name}"
        self.parent = parent
        self._ui_items = [UIItem(plugin, self)]

    @property
    def ui_items(self):
        """The UI item to show for this item"""
        return self._ui_items

    def destroy(self):
        self._ui_items = None
        super().destroy()


class CheckerItem(BaseItem):
    """Item of the model"""

    def __init__(self, plugin: _CheckSchema):
        super().__init__(plugin)
        child_items = [ContextItem(plugin.context_plugin, parent=self)]
        child_items += [SelectorItem(selector_plugin, self) for selector_plugin in plugin.selector_plugins]
        child_items += [ResultorItem(resultor_plugin) for resultor_plugin in plugin.resultor_plugins or []]
        # we add a check UI item
        child_items.append(UIItem(plugin, self))
        self.child_items = child_items

    def destroy(self):
        self.child_items = None
        super().destroy()


class ResultorItem(BaseItem):
    """Item of the model"""

    def __init__(self, plugin: _ResultorSchema):
        super().__init__(plugin)
        self._ui_items = [UIItem(plugin, self)]

    @property
    def ui_items(self):
        """The UI item to show for this item"""
        return self._ui_items

    def destroy(self):
        self._ui_items = None
        super().destroy()


class Model(ui.AbstractItemModel):
    """Basic list model"""

    def __init__(self):
        super().__init__()
        self._default_attrs = {"_items": None}
        for attr, value in self._default_attrs.items():
            setattr(self, attr, value)
        self._items = []

    def set_items(self, items: List[CheckerItem]):
        """Set the items to show"""
        self._items = items
        self._item_changed(None)

    def get_item_children(self, item: Optional[CheckerItem]):
        """Returns all the children when the widget asks it."""
        if item is None:
            return self._items
        if isinstance(item, CheckerItem):
            return item.child_items
        if isinstance(item, (SelectorItem, ResultorItem, ContextItem)):
            return item.ui_items
        return []

    def get_item_value_model_count(self, item: CheckerItem):
        """The number of columns"""
        return len(HEADER_DICT.keys())

    def get_item_value_model(self, item, column_id):
        """
        Return value model.
        It's the object that tracks the specific value.
        In our case we use ui.SimpleStringModel.
        """
        if item is None:
            return self._items
        if column_id == 0:
            return item.title_model
        return None

    def destroy(self):
        _reset_default_attrs(self)
