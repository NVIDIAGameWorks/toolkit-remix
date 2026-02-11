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
from collections.abc import Callable

import carb
import omni.ui as ui
from omni.flux.property_widget_builder.widget import ItemModel as _ItemModel
from pxr import Sdf

from ..utils import get_default_attribute_value as _get_default_attribute_value
from .attr_value import UsdAttributeBase as _UsdAttributeBase


class OptionItem(ui.AbstractItem):
    def __init__(self, display_name: str, value: int):
        super().__init__()
        self.model = ui.SimpleStringModel(display_name)
        self.value = value


class UsdListModelBaseValueModel(_UsdAttributeBase, _ItemModel, abc.ABC):
    """
    Represent a value that has multiple value choices like enums.
    """

    def __init__(
        self,
        context_name: str,
        attribute_paths: list[Sdf.Path],
        default_value: str,
        options: list[str],
        read_only: bool = False,
        value_type_name: Sdf.ValueTypeName | None = None,
        metadata: dict | None = None,
        metadata_key: str | None = None,
    ):
        super().__init__(
            context_name,
            attribute_paths,
            read_only=read_only,
            value_type_name=value_type_name,
        )
        # Clear out guessed value type, we leave it as str and handle it ourselves for better serialization.
        self._override_value_type = None
        # Guard to avoid inf loop and skip _current_index_changed when updating value in code
        self.__block_set_value = False
        # Whether to save the value in USD as the integer index of options or as the value itself
        self._use_index_in_usd = self._value_type_name == Sdf.ValueTypeNames.Int

        self._default_value = default_value
        self._item_options = []
        self._list_options = options
        self._update_options()
        self._current_index = ui.SimpleIntModel()
        self._current_index.add_value_changed_fn(self._current_index_changed)
        self._metadata = metadata
        self._metadata_key = metadata_key

        self.init_attributes()

    def get_value(self):
        return self._value

    def deserialize(self, value):
        self.set_value(self._list_options.index(value))

    def get_item_children(
        self,
        parentItem: OptionItem = None,  # noqa: N803 (intentional match for parent kwarg)
    ) -> list[OptionItem]:
        return self._item_options

    def get_item_value_model(self, item: OptionItem = None, column_id: int = 0):
        if item is None:
            return self._current_index
        return item.model

    def _get_default_value(self, attr) -> str | None:
        if self._default_value is None:
            default_value_index = _get_default_attribute_value(attr)
            if default_value_index:
                return self._list_options[default_value_index]
            return None
        return self._default_value

    @property
    def is_default(self):
        """If the value model has the default USD value"""
        for attribute in self.attributes:
            default_value = self._get_default_value(attribute)
            if default_value is None:
                continue
            if self.get_value() != default_value:
                return False
        return True

    def reset_default_value(self):
        """Reset the model's value back to the USD default"""
        for attribute in self.attributes:
            default_value = self._get_default_value(attribute)
            if default_value is None:
                continue
            self.set_value(default_value)

    def begin_edit(self, item: OptionItem):
        carb.log_warn(f"begin_edit not supported in {self.__class__.__name__}")

    def end_edit(self, item: OptionItem):
        carb.log_warn(f"begin_edit not supported in {self.__class__.__name__}")

    def subscribe_value_changed_fn(self, func: Callable[[ui.SimpleIntModel], None]):
        # redirect subscription on to value model
        return self._current_index.subscribe_value_changed_fn(func)

    def _current_index_changed(self, model):
        if not self._item_options or self.__block_set_value:
            return

        index = model.as_int
        self.set_value(self._list_options[self._item_options[index].value])

    def _update_options(self):
        self._item_options = []
        for index, option in enumerate(self._list_options):
            self._item_options.append(OptionItem(option, int(index)))

    def _update_value(self):
        index = -1
        for i, item_option in enumerate(self._item_options):
            if item_option.model.get_value_as_string() == self._value:
                index = i
                break

        # update the widget value, but do not trigger a set_value
        self.__block_set_value = True
        if index not in (-1, self._current_index.as_int):
            self._current_index.set_value(index)
        else:
            # Trigger value changed callbacks for underlying widget when the value does not
            #  change. Mixed state may change even if widget is already at index.
            self._current_index._value_changed()  # noqa: SLF001
        self.__block_set_value = False

    def _on_dirty(self):
        # set combo box to match self._value and then trigger item changed
        self._update_value()
        self._item_changed(None)

    def __repr__(self):
        result = "\nOptions:\n"
        result += f"    {' | '.join(self._list_options)}\n"
        result += f"Value:\n    {self._value}\n"
        return result
