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

__all__ = (
    "BaseItemModel",
    "Serializable",
    "ItemModel",
    "ItemGroupModel",
)

import abc
from typing import Any, Callable

import omni.ui as ui

from . import clipboard


class BaseItemModel:
    """Base item that should be used with ItemModel"""

    def __init__(self):
        super().__init__()
        self._callback_pre_set_value = None
        self._callback_post_set_value = None

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
        self._callback_pre_set_value = callback

    def set_callback_post_set_value(self, callback: Callable[[Callable[[Any], Any], Any], Any]):
        """
        Set a callback that will be executed after the value is set

        Args:
            callback: callback that will be executed after the value is set. The callback will receive the
                "_set_value()" function and the value, if the callback wants to update the value manually

        Returns:
            None
        """
        self._callback_post_set_value = callback

    def set_value(self, value: Any, callback: Callable[[Any], Any]):
        if self._callback_pre_set_value is not None:
            self._callback_pre_set_value(callback, value)
            return
        callback(value)
        if self._callback_post_set_value is not None:
            self._callback_post_set_value(callback, value)


class Serializable:
    """
    Mixin class to add serialization methods.

    A single `Serializer` instance is shared for all classes that inherit from this class.
    """

    def __init__(self):
        super().__init__()
        self.register_serializer_hooks(clipboard.SERIALIZER)

    def register_serializer_hooks(self, serializer):
        """
        Register serialization hooks for clipboard copy/paste.

        Subclasses should overwrite this method if their get_value returns a type that is not natively supported by
        json. See the `Serializer` class documentation for more details.
        """
        pass

    @abc.abstractmethod
    def get_value(self):
        raise NotImplementedError

    @abc.abstractmethod
    def set_value(self, value):
        raise NotImplementedError

    def serialize(self):
        """
        Get a serialized representation of this object.

        Whatever is returned from this method should also be accepted as a value to the `de` method.

        Sometimes special handling is needed for more complex types that are not natively supported in a serialized
        format.
        """
        return self.get_value()

    def deserialize(self, value):
        self.set_value(value)


class ItemModel(Serializable, ui.AbstractValueModel):
    """The value model that handle the value of an attribute (name or value)"""

    def __init__(self, base_item_model: BaseItemModel = None):
        super().__init__()
        if base_item_model is None:
            base_item_model = BaseItemModel()
        self._base_item_model = base_item_model
        self._read_only = True
        self._multiline = (False, 0)
        self.__display_fn = None  # noqa PLW0238
        self.__block_set_value = False
        self.__cached_blocked_value = None

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

    @abc.abstractmethod
    def refresh(self):
        """Called by the watcher when something change"""
        pass

    def get_tool_tip(self):
        pass

    def get_value_as_string(self) -> str:
        value = self._get_value_as_string()
        return self.__display_fn(value, self) if self.__display_fn is not None else value

    def get_value_as_float(self) -> float:
        value = self._get_value_as_float()
        return self.__display_fn(value, self) if self.__display_fn is not None else value

    def get_value_as_bool(self) -> bool:
        value = self._get_value_as_bool()
        return self.__display_fn(value, self) if self.__display_fn is not None else value

    def get_value_as_int(self) -> int:
        value = self._get_value_as_int()
        return self.__display_fn(value, self) if self.__display_fn is not None else value

    @abc.abstractmethod
    def _get_value_as_string(self) -> str:
        return ""

    @abc.abstractmethod
    def _get_value_as_float(self) -> float:
        return 0.0

    @abc.abstractmethod
    def _get_value_as_bool(self) -> bool:
        return False

    @abc.abstractmethod
    def _get_value_as_int(self) -> int:
        return 0

    def block_set_value(self, value: bool):
        """
        Block the set value function

        Args:
            value: block or not

        Returns:
            None
        """
        self.__block_set_value = value

    def is_set_value_blocked(self) -> bool:
        """Is the set value function blocked or not"""
        return self.__block_set_value

    @property
    def cached_blocked_value(self) -> Any:
        """Return the cached value when the set value function is blocked"""
        return self.__cached_blocked_value

    def set_value(self, value: Any):
        """
        This function should NOT be overridden. Please uses `_set_value()`.
        Set the value. If "__block_set_value" is True, the value will not be set but cached into
        "__cached_blocked_value". This can be used by a custom delegate to set a value when it wants (being_edit_fn,
        end_edit_fn, etc).

        Args:
            value: the value to set

        Returns:
            None
        """
        if self.__block_set_value:
            if value != self.__cached_blocked_value:
                self.__cached_blocked_value = value
                self._value_changed()
            return
        self.__cached_blocked_value = None
        self._base_item_model.set_value(value, self._set_value)

    def _set_value(self, value: Any):
        """
        Function to override/implement to set the value of ui.AbstractValueModel

        Args:
            value: value to set
        """
        pass

    def set_display_fn(self, display_fn: Callable[[Any, "ItemModel"], Any]):
        """
        Function that will be called to filter the current value we want to show
        For example, if the value is "hello", but we want to show "Hello"
        """
        self.__display_fn = display_fn

    @property
    def read_only(self):
        """Used by the delegate to see if the item is read only or not"""
        return self._read_only

    @property
    def multiline(self):
        """Used by the delegate to see if the item is read only or not"""
        return self._multiline

    def __repr__(self):
        return f"{self.__class__.__name__}({self.get_value()!r})"


class ItemGroupModel(ItemModel):
    """The value model that handle the value of an attribute (name or value)"""

    def __init__(self, name):
        super().__init__()
        self._name = name
        self._read_only = True
        self.__display_fn = None  # noqa PLW0238

    def refresh(self):
        """Called by the watcher when something change"""
        pass

    def get_value(self):
        return self._name

    def _get_value_as_string(self) -> str:
        return self._name

    def _get_value_as_float(self) -> float:
        return 0.0

    def _get_value_as_bool(self) -> bool:
        return False

    def _get_value_as_int(self) -> int:
        return 0
