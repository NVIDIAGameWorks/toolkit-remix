"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["CallbackValueModel"]

import pathlib
from collections.abc import Callable
from typing import Any

from .item_model import ItemValueModel


class CallbackValueModel(ItemValueModel):
    """Edit one typed value that the owner reads and writes through callbacks.

    The owner keeps its storage and validation in the callbacks. A path value accepts text from a string field and
    shows an empty path as an empty string. A value that does not convert to a number shows as zero.
    """

    def __init__(self, value_type: type, get_value_fn: Callable[[], Any], set_value_fn: Callable[[Any], None]):
        """Bind the model to one value.

        Args:
            value_type: Declared value type, used to convert edited text.
            get_value_fn: Returns the current value.
            set_value_fn: Stores an edited value.
        """
        super().__init__()
        self._value_type = value_type
        self._get_value_fn = get_value_fn
        self._set_value_fn = set_value_fn
        self._read_only = False

    def get_value(self) -> Any:
        """Return the current value."""
        return self._get_value_fn()

    def refresh(self) -> None:
        """Re-read the value and notify the field widgets."""
        self._value_changed()

    def _set_value(self, value: Any) -> None:
        """Store an edited value when it changed."""
        if self._value_type is pathlib.Path and isinstance(value, str):
            value = pathlib.Path(value)
        if value != self.get_value():
            self._set_value_fn(value)
            self._value_changed()

    def _on_dirty(self) -> None:
        """Notify the field widgets after a change."""
        self._value_changed()

    def _get_value_as_string(self) -> str:
        """Return the value as text, with an empty path as an empty string."""
        value = self.get_value()
        return "" if self._value_type is pathlib.Path and value == pathlib.Path() else str(value)

    def _get_value_as_float(self) -> float:
        """Return the value as a float, or zero when it does not convert."""
        try:
            return float(self.get_value())
        except (TypeError, ValueError):
            return 0.0

    def _get_value_as_bool(self) -> bool:
        """Return the truth value."""
        return bool(self.get_value())

    def _get_value_as_int(self) -> int:
        """Return the value as an integer, or zero when it does not convert."""
        try:
            return int(self.get_value())
        except (TypeError, ValueError):
            return 0
