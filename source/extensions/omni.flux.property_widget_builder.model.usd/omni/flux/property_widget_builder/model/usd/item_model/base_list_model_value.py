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

import abc
from typing import Any, Callable, List, Optional

import carb
import omni.kit.commands
import omni.ui as ui
import omni.usd
from omni.flux.property_widget_builder.widget import BaseItemModel as _BaseItemModel
from omni.flux.property_widget_builder.widget import Serializable as _Serializable
from pxr import Sdf

from ..mapping import DEFAULT_VALUE_TABLE
from ..utils import get_default_attribute_value as _get_default_attribute_value
from ..utils import get_item_attributes as _get_item_attributes
from ..utils import get_metadata as _get_metadata
from ..utils import is_item_overriden as _is_item_overriden


class UsdListModelBaseValueModel(_Serializable, ui.AbstractItemModel):
    """The value model that is reimplemented in Python to watch a USD paths.
    Paths can be either Attribute or Prim paths"""

    def __init__(
        self,
        context_name: str,
        attribute_paths: List[Sdf.Path],
        key: Optional[str],
        default: str,
        options: List[str],
        read_only: bool = False,
        not_implemented: bool = False,
        base_item_model: _BaseItemModel = None,
    ):
        super().__init__()
        if base_item_model is None:
            base_item_model = _BaseItemModel()
        self._base_item_model = base_item_model
        self._context_name = context_name
        self._stage = omni.usd.get_context(context_name).get_stage()
        self._attribute_paths = attribute_paths
        self._metadata = None
        self._key = key
        self._default_value = default
        self._read_only = read_only
        self._is_mixed = False
        self._value = None  # The value to be displayed on widget
        self._not_implemented = not_implemented
        self._ignore_refresh = False

        self._item_options = []
        self._list_options = options
        self._update_option()
        self._current_index = ui.SimpleIntModel()
        self._current_index.add_value_changed_fn(self._current_index_changed)

        self._has_index = False
        self._update_value()
        self._has_index = True

        # cache the attributes
        self._attributes = _get_item_attributes(self.stage, self.attribute_paths)

    def set_callback_pre_set_value(self, callback: Callable[[Callable[[Any], Any], Any], Any]):
        """
        Set a callback that will be executed before the value is set

        Args:
            callback: callback that will be executed before the value is set. If the callback exists, the callback
                controls if the value should be set or not. The callback will receive the "_set_value()" function and
                the value

        Returns:
            None
        """
        self._base_item_model.set_callback_pre_set_value(callback)

    def set_callback_post_set_value(self, callback: Callable[[Callable[[Any], Any], Any], Any]):
        """
        Set a callback that will be executed after the value is set

        Args:
            callback: callback that will be executed after the value is set. The callback will receive the
                "_set_value()" function and the value, if the callback wants to update the value manually

        Returns:
            None
        """
        self._base_item_model.set_callback_post_set_value(callback)

    def refresh(self):
        if self._ignore_refresh:
            return
        self._update_value()

    def get_value(self):
        return self.value

    def deserialize(self, value):
        self.set_value(self._list_options.index(value))

    def get_item_children(self, item):
        self._update_value()
        return self._item_options

    def get_item_value_model(self, item, column_id):
        if item is None:
            return self._current_index
        return item.model

    @property
    def value(self):
        return self._value

    @property
    def attribute_paths(self):
        return self._attribute_paths

    @property
    def stage(self):
        return self._stage

    @property
    def metadata(self):
        if not self._stage:
            carb.log_error("Can't find the stage")
            return {}
        return _get_metadata(self._context_name, self._attribute_paths)

    @property
    def read_only(self):
        return self._read_only

    @property
    def attributes(self):
        return self._attributes

    @property
    def is_overriden(self):
        """If the value model has an override"""
        return _is_item_overriden(self.stage, self.attributes)

    @property
    def is_default(self):
        """If the value model has the default USD value"""
        for attribute in self.attributes:
            default_value = self.__get_default_value(attribute)
            if default_value is None:
                continue
            # Attempt to find the value in the list
            if [c.model.as_string for c in self.get_item_children(None)].index(self.value) != default_value:
                return False
        return True

    def reset_default_value(self):
        """Reset the model's value back to the USD default"""
        for attribute in self.attributes:
            default_value = self.__get_default_value(attribute)
            if default_value is None:
                continue
            self.set_value(default_value)

    def __get_default_value(self, attribute):
        return (
            DEFAULT_VALUE_TABLE[attribute.GetName()]
            if attribute.GetName() in DEFAULT_VALUE_TABLE
            else _get_default_attribute_value(attribute)
        )

    def begin_edit(self):
        carb.log_warn("begin_edit not supported in MetadataObjectModel")

    def end_edit(self):
        carb.log_warn("end_edit not supported in MetadataObjectModel")

    def _current_index_changed(self, model):
        if not self._has_index:
            return

        index = model.as_int
        if self.set_value(self._item_options[index].value):
            self._item_changed(None)

    def _update_option(self):
        class OptionItem(ui.AbstractItem):
            def __init__(self, display_name: str, value: int):
                super().__init__()
                self.model = ui.SimpleStringModel(display_name)
                self.value = value

        self._item_options = []
        for index, option in enumerate(self._list_options):
            self._item_options.append(OptionItem(option, int(index)))

    def _update_value(self):
        if self._read_value_from_usd():
            index = -1
            for i, item_option in enumerate(self._item_options):
                if item_option.model.get_value_as_string() == self._value:
                    index = i

            if index not in (-1, self._current_index.as_int):
                self._current_index.set_value(index)
                self._item_changed(None)

    @abc.abstractmethod
    def _set_attribute_value(self, attr, new_value: int):
        pass

    @abc.abstractmethod
    def _get_attribute_value(self, attr) -> Any:
        pass

    def _read_value_from_usd(self):
        """
        Return:
            True if the cached value was updated; false otherwise
        """
        if not self._stage:
            assert self._value is None
            return False

        last_value = None
        values_read = 0
        value_was_set = False
        for attribute_path in self._attribute_paths:
            prim = self._stage.GetPrimAtPath(attribute_path.GetPrimPath())
            if prim.IsValid():
                attr = prim.GetAttribute(attribute_path.name)
                if attr.IsValid() and not attr.IsHidden():
                    value = self._get_attribute_value(attr)
                    if values_read == 0:
                        # If this is the first prim with this attribute, use it for the cached value.
                        last_value = value
                        if self._value is None or value != self._value:
                            self._value = value
                            value_was_set = True
                    else:
                        if last_value != value:
                            self._is_mixed = True
                    values_read += 1
        return value_was_set

    def set_value(self, value):
        """Protected. Please implement _set_value() and not this function"""
        self._base_item_model.set_value(value, self._set_value)

    def _set_value(self, value):
        """Override of ui.AbstractValueModel.set_value()"""
        if self.read_only or self._not_implemented:
            return False
        if value is None or value == "" or value == ".":
            return False
        self._value = value
        if not self._stage:
            return False
        need_refresh = False
        for attribute_path in self._attribute_paths:
            prim = self._stage.GetPrimAtPath(attribute_path.GetPrimPath())
            if prim.IsValid():
                attr = prim.GetAttribute(attribute_path.name)
                if attr.IsValid() and attr.Get() != self._value:
                    need_refresh = True
                    self._ignore_refresh = True
                    self._set_attribute_value(attr, self._value)
                    self._ignore_refresh = False
        if need_refresh:
            self._on_dirty()
            return True
        return False

    def _on_dirty(self):
        self._item_changed(None)

    def __repr__(self):
        result = "\nOptions:\n"
        result += f"    {' | '.join(self._list_options)}\n"
        result += f"Value:\n    {self._value}\n"
        return result
