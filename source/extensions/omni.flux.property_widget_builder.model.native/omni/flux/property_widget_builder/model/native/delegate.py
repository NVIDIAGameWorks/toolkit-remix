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

__all__ = ("NativeDelegate",)

from omni.flux.property_widget_builder.widget import Delegate as _Delegate
from omni.flux.property_widget_builder.widget import FieldBuilder

from .field_builders import NATIVE_FIELD_BUILDERS


class NativeDelegate(_Delegate):
    """Delegate for property widgets displaying native Python-typed data.

    Parallel to ``USDDelegate`` but dispatches field builders based on
    ``item.value_type`` (a Python type like ``float``, ``bool``, ``str``)
    instead of USD attribute metadata.

    Any ``Item`` that exposes a ``value_type: type`` property will get
    type-appropriate widgets (FloatDrag, IntDrag, CheckBox, StringField).
    Items whose ``value_type`` does not match any registered builder fall back
    to a read-only ``DefaultLabelField`` showing the type name.
    """

    def _get_default_field_builders(self) -> list[FieldBuilder]:
        return NATIVE_FIELD_BUILDERS
