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

__all__ = ("MockValueModel",)

from typing import Any

from omni.flux.property_widget_builder.widget.tree.item_model import ItemValueModel


class MockValueModel(ItemValueModel):
    """Minimal value model for testing delegate fields."""

    def __init__(self, value: Any = 0.0, read_only: bool = False):
        super().__init__()
        self._value = value
        self._read_only = read_only
        self.begin_edit_calls = 0
        self.end_edit_calls = 0

    def begin_edit(self) -> None:
        self.begin_edit_calls += 1
        super().begin_edit()

    def end_edit(self) -> None:
        self.end_edit_calls += 1
        super().end_edit()

    def get_value(self):
        return self._value

    def _set_value(self, value):
        self._value = value
        self._value_changed()

    def _on_dirty(self):
        self._value_changed()

    def refresh(self):
        pass

    def _get_value_as_float(self) -> float:
        return float(self._value)

    def _get_value_as_int(self) -> int:
        return int(self._value)

    def _get_value_as_string(self) -> str:
        return str(self._value)

    def _get_value_as_bool(self) -> bool:
        return bool(self._value)

    def get_tool_tip(self):
        return None
