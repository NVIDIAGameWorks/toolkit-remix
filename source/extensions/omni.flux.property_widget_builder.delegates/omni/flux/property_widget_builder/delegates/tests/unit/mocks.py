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

import omni.ui as ui


class MockValueModel(ui.AbstractValueModel):
    """Minimal value model for testing delegate fields."""

    def __init__(self, value: float | int = 0.0, read_only: bool = False):
        super().__init__()
        self._value = value
        self._read_only = read_only
        self._pre_set_callback = None

    @property
    def read_only(self) -> bool:
        return self._read_only

    @property
    def supports_batch_edit(self) -> bool:
        return False

    @property
    def is_batch_editing(self) -> bool:
        return False

    def begin_batch_edit(self) -> None:
        pass

    def end_batch_edit(self) -> None:
        pass

    def get_value(self):
        return self._value

    def get_value_as_float(self) -> float:
        return float(self._value)

    def get_value_as_int(self) -> int:
        return int(self._value)

    def set_callback_pre_set_value(self, callback):
        """Mirror the real ItemModelBase pre_set_value hook used by AbstractDragFieldGroup."""
        self._pre_set_callback = callback

    def set_value(self, value):
        """Set the model value, routing through the ``pre_set_value`` callback when registered.

        If a callback has been registered via :meth:`set_callback_pre_set_value`, the callback
        receives a ``_do_set`` closure (the actual writer) and the incoming value; the callback
        is responsible for calling ``_do_set`` with the (optionally clamped) value.
        If no callback is registered the value is written directly.
        """
        if self._pre_set_callback is not None:

            def _do_set(v):
                self._value = v
                self._value_changed()

            self._pre_set_callback(_do_set, value)
        else:
            self._value = value
            self._value_changed()

    def get_tool_tip(self):
        return None
