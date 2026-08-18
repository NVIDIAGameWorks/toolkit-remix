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

__all__ = (
    "NATIVE_FIELD_BUILDERS",
    "NativeBuilderList",
)

import pathlib
from collections.abc import Callable
import omni.ui as ui
from omni.flux.property_widget_builder.delegates import ComboboxField, FilePicker
from omni.flux.property_widget_builder.delegates.default import DefaultField
from omni.flux.property_widget_builder.delegates.string_value.default_label import DefaultLabelField
from omni.flux.property_widget_builder.widget import FieldBuilder, FieldBuilderList, Item, claim_each

from .choice_model import NativeChoiceModel
from .item import NativeItem


class NativeBuilderList(FieldBuilderList):
    """Extension of FieldBuilderList with registration helpers for native Python types.

    Parallel to ``USDBuilderList`` but dispatches by ``item.value_type``
    (a Python type) instead of USD attribute metadata.
    """

    def _build_func_decorator(self, claim_func: Callable[[Item], bool]) -> Callable:
        """Register a native property builder for a claim predicate.

        Args:
            claim_func: Predicate deciding whether one property item uses the builder.

        Returns:
            Decorator that registers and returns the supplied build function.
        """

        def _decorator(
            build_func: Callable[[NativeItem], ui.Widget | list[ui.Widget] | None],
        ) -> Callable[[NativeItem], ui.Widget | list[ui.Widget] | None]:
            self.append(FieldBuilder(claim_func=claim_each(claim_func), build_func=build_func))
            return build_func

        return _decorator

    def register_by_value_type(self, *value_types: type) -> Callable:
        """Register a builder for one or more exact native value types.

        Args:
            value_types: Exact Python types handled by the registered builder.

        Returns:
            Decorator that registers the supplied build function.
        """

        def _claim(item: Item) -> bool:
            return isinstance(item, NativeItem) and item.value_type in value_types

        return self._build_func_decorator(_claim)


NATIVE_FIELD_BUILDERS = NativeBuilderList()

_VALUE_IDENTIFIER = "NativePropertyValue"
_FILE_PICKER_IDENTIFIER = "NativePropertyFilePicker"


# Registered first means lowest priority; Delegate.resolve_claims iterates reversed(field_builders).
@NATIVE_FIELD_BUILDERS.register_build(lambda _: True)
def _fallback_builder(item) -> list[ui.Widget]:
    """Build a read-only type label when no editable native delegate exists.

    Args:
        item: Native property item with an unsupported value type.

    Returns:
        Built fallback field widgets.
    """
    builder = DefaultLabelField(str(item.value_type) if isinstance(item, NativeItem) else "Unsupported property")
    return builder(item)


@NATIVE_FIELD_BUILDERS.register_by_value_type(bool)
def _bool_builder(item) -> list[ui.Widget]:
    builder = DefaultField(ui.CheckBox, style_name="PropertiesWidgetFieldBool", identifier=_VALUE_IDENTIFIER)
    return builder(item)


@NATIVE_FIELD_BUILDERS.register_by_value_type(int)
def _integer_builder(item) -> list[ui.Widget]:
    builder = DefaultField(ui.IntDrag, identifier=_VALUE_IDENTIFIER)
    return builder(item)


@NATIVE_FIELD_BUILDERS.register_by_value_type(float)
def _float_builder(item) -> list[ui.Widget]:
    builder = DefaultField(ui.FloatDrag, identifier=_VALUE_IDENTIFIER)
    return builder(item)


@NATIVE_FIELD_BUILDERS.register_by_value_type(str)
def _string_builder(item) -> list[ui.Widget]:
    builder = DefaultField(ui.StringField, identifier=_VALUE_IDENTIFIER)
    return builder(item)


@NATIVE_FIELD_BUILDERS.register_by_value_type(pathlib.Path)
def _path_builder(item) -> list[ui.Widget]:
    builder = FilePicker(identifier=_VALUE_IDENTIFIER, picker_identifier=_FILE_PICKER_IDENTIFIER)
    return builder(item)


@NATIVE_FIELD_BUILDERS.register_build(
    lambda item: (
        isinstance(item, NativeItem) and bool(item.value_models) and isinstance(item.value_models[0], NativeChoiceModel)
    )
)
def _choice_builder(item) -> list[ui.Widget]:
    builder = ComboboxField(identifier=_VALUE_IDENTIFIER)
    return builder(item)
