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

import operator
from collections.abc import Iterable
from enum import Enum
from functools import partial
from typing import Any, Dict, List, Tuple

import omni.kit.app
import omni.kit.commands
from omni import ui, usd
from pydantic import BaseModel, validator

from ..base.check_base_usd import CheckBaseUSD as _CheckBaseUSD  # noqa PLE0402


class Operator(Enum):
    lt = "<"
    le = "<="
    eq = "="
    ne = "!="
    ge = ">="
    gt = ">"
    all_items = "All"
    no_items = "None"


class AttributeMapping(BaseModel):
    operator: Operator
    input_value: Any
    output_value: Any


class ValueMapping(_CheckBaseUSD):
    class Data(_CheckBaseUSD.Data):
        attributes: Dict[str, List[AttributeMapping]]

        @validator("attributes", allow_reuse=True)
        def not_empty_attribute_name(cls, v):  # noqa
            for attr_name, _ in v.items():
                if not attr_name or not attr_name.strip():
                    raise ValueError("Attribute name cannot be empty")
            return v

        @validator("attributes", allow_reuse=True)
        def input_output_same_type(cls, v):  # noqa
            for _, attr_mappings in v.items():
                for index, mapping in enumerate(attr_mappings):
                    if type(mapping.input_value) != type(mapping.output_value):  # noqa
                        raise ValueError(f"Input and Output value types do not match for mapping -> {index}")
            return v

        @validator("attributes", allow_reuse=True)
        def iterable_input_output_same_length(cls, v):  # noqa
            for _, attr_mappings in v.items():
                for index, mapping in enumerate(attr_mappings):
                    if not isinstance(mapping.input_value, Iterable) or isinstance(mapping.input_value, str):
                        continue
                    if len(mapping.input_value) != len(mapping.output_value):  # noqa
                        raise ValueError(f"Input and Output values do not have the same number of items -> {index}")
            return v

        class Config(_CheckBaseUSD.Data.Config):
            validate_assignment = True

    name = "ValueMapping"
    tooltip = "This plugin will remap any value to a different target value for any specified attribute"
    data_type = Data
    display_name = "Update Attribute Values"

    def __init__(self):
        super().__init__()

        self._fixed = False
        self._field_validate_subs = []

        self.__OPERATOR_MAP = {
            Operator.lt: operator.lt,
            Operator.le: operator.le,
            Operator.eq: operator.eq,
            Operator.ne: operator.ne,
            Operator.ge: operator.ge,
            Operator.gt: operator.gt,
            Operator.all_items: lambda x, y: not self._fixed,
            Operator.no_items: lambda x, y: False,
        }

    @usd.handle_exception
    async def _check(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to check the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns:
            bool: True if the check passed, False if not. If the check is True, it will NOT run the fix
            str: the message you want to show, like "Succeeded to check this"
            any: data that you want to pass. For now this is used no where. So you can pass whatever you want (None)
        """
        message = "Check:\n"
        progress = 0
        success = True

        self.on_progress(progress, "Start", success)

        if selector_plugin_data:  # noqa PLR1702
            progress_delta = 1 / len(selector_plugin_data)

            for prim in selector_plugin_data:
                is_valid = True
                progress_message = f"SKIP: The prim ({prim.GetPath()}) does not have mappable attributes"

                for attr_name, attr_mappings in schema_data.attributes.items():
                    attribute = prim.GetAttribute(attr_name)
                    if not attribute:
                        continue
                    for mapping in attr_mappings:
                        input_value = attribute.Get()
                        input_type = type(input_value)
                        if self.__OPERATOR_MAP[mapping.operator](input_value, input_type(mapping.input_value)):
                            is_valid = False
                            progress_message = (
                                f"FAIL: The prim ({prim.GetPath()}) has the attribute '{attr_name}' "
                                f"that must to be mapped"
                            )
                            break
                    if is_valid:
                        progress_message = (
                            f"SKIP: The prim ({prim.GetPath()}) has the attribute '{attr_name}' "
                            f"but does not match a mapping predicate"
                        )
                    else:
                        break

                message += f"- {progress_message}\n"
                progress += progress_delta
                success &= is_valid
                self.on_progress(progress, progress_message, success)
        else:
            message += "- SKIP: No selected prims"

        return success, message, None

    @usd.handle_exception
    async def _fix(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to fix the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns:
            bool: True if the check passed, False if not. If the check is True, it will NOT run the fix
            str: the message you want to show, like "Succeeded to check this"
            any: data that you want to pass. For now this is used no where. So you can pass whatever you want (None)
        """
        message = "Fix:\n"
        progress = 0
        success = True

        self.on_progress(progress, "Start", success)

        if selector_plugin_data:  # noqa PLR1702
            progress_delta = 1 / len(selector_plugin_data)

            for prim in selector_plugin_data:
                is_valid = True
                progress_message = f"SKIP: The prim ({prim.GetPath()}) does not have mappable attributes"

                for attr_name, attr_mappings in schema_data.attributes.items():
                    attribute = prim.GetAttribute(attr_name)
                    if not attribute:
                        continue
                    was_mapped = False
                    for mapping in attr_mappings:
                        input_value = attribute.Get()
                        input_type = type(input_value)
                        if self.__OPERATOR_MAP[mapping.operator](input_value, input_type(mapping.input_value)):
                            omni.kit.commands.execute(
                                "ChangeProperty",
                                prop_path=prim.GetProperty(attr_name).GetPath(),
                                value=input_type(mapping.output_value),
                                prev=None,
                                usd_context_name=context_plugin_data,
                            )
                            was_mapped = True
                    progress_message = (
                        f"SUCCESS: The attribute '{attr_name}' for the prim ({prim.GetPath()}) was mapped"
                        if was_mapped
                        else (
                            f"SKIP: The prim ({prim.GetPath()}) has the attribute '{attr_name}' "
                            f"but does not match a mapping predicate"
                        )
                    )

                message += f"- {progress_message}\n"
                progress += progress_delta
                success &= is_valid
                self.on_progress(progress, progress_message, success)
        else:
            message += "- SKIP: No selected prims"

        self._fixed = True
        return success, message, None

    def _on_operator_field_edit_end(self, schema_data: Data, attr_name: str, mapping_index: int, model, _):
        new_attributes = schema_data.attributes.copy()
        new_attributes[attr_name][mapping_index].operator = list(Operator)[
            model.get_item_value_model().get_value_as_int()
        ]
        try:
            schema_data.attributes = new_attributes
        except ValueError:
            model.set_value(schema_data.attributes[attr_name][mapping_index].operator)

    def _on_input_field_edit_end(
        self, schema_data: Data, attr_name: str, mapping_index: int, model, value_index: int = None
    ):
        new_attributes = schema_data.attributes.copy()
        input_value = new_attributes[attr_name][mapping_index].input_value
        original_type = type(input_value[value_index]) if value_index is not None else type(input_value)
        try:
            if value_index is not None:
                new_attributes[attr_name][mapping_index].input_value[value_index] = original_type(
                    model.get_value_as_string()
                )
            else:
                new_attributes[attr_name][mapping_index].input_value = original_type(model.get_value_as_string())
            schema_data.attributes = new_attributes
        except ValueError:
            if value_index is not None:
                model.set_value(schema_data.attributes[attr_name][mapping_index].input_value[value_index])
            else:
                model.set_value(schema_data.attributes[attr_name][mapping_index].input_value)

    def _on_output_field_edit_end(
        self, schema_data: Data, attr_name: str, mapping_index: int, model, value_index: int = None
    ):
        new_attributes = schema_data.attributes.copy()
        output_value = new_attributes[attr_name][mapping_index].output_value
        original_type = type(output_value[value_index]) if value_index is not None else type(output_value)
        try:
            if value_index is not None:
                new_attributes[attr_name][mapping_index].output_value[value_index] = original_type(
                    model.get_value_as_string()
                )
            else:
                new_attributes[attr_name][mapping_index].output_value = original_type(model.get_value_as_string())
            schema_data.attributes = new_attributes
        except ValueError:
            if value_index is not None:
                model.set_value(schema_data.attributes[attr_name][mapping_index].output_value[value_index])
            else:
                model.set_value(schema_data.attributes[attr_name][mapping_index].output_value)

    @usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        operators = [op.value for op in Operator]
        self._field_validate_subs.clear()

        labels = []

        with ui.VStack():
            for attr_name, attr_mappings in schema_data.attributes.items():
                with ui.HStack():
                    labels.append(ui.Label(f'"{attr_name}" Mapping', width=0, alignment=ui.Alignment.LEFT_TOP))
                    ui.Spacer(height=0, width=ui.Pixel(16))
                    with ui.VStack():
                        for index, mapping in enumerate(attr_mappings):
                            with ui.HStack(spacing=ui.Pixel(8)):
                                operator_field = ui.ComboBox(
                                    operators.index(mapping.operator.value),
                                    *operators,
                                    width=ui.Pixel(64),
                                    identifier="OperatorField",
                                )
                                self._field_validate_subs.append(
                                    operator_field.model.subscribe_item_changed_fn(
                                        partial(self._on_operator_field_edit_end, schema_data, attr_name, index)
                                    )
                                )

                                input_values = mapping.input_value
                                output_values = mapping.output_value
                                if not isinstance(mapping.input_value, Iterable) or isinstance(
                                    mapping.input_value, str
                                ):
                                    input_values = [mapping.input_value]
                                    output_values = [mapping.output_value]

                                for value_index, value in enumerate(input_values):
                                    input_value_field = ui.StringField(identifier="InputField")
                                    input_value_field.model.set_value(value)
                                    self._field_validate_subs.append(
                                        input_value_field.model.subscribe_end_edit_fn(
                                            partial(
                                                self._on_input_field_edit_end,
                                                schema_data,
                                                attr_name,
                                                index,
                                                value_index=value_index if len(input_values) > 1 else None,
                                            )
                                        )
                                    )
                                ui.Image("", name="ArrowRight", width=ui.Pixel(18))
                                for value_index, value in enumerate(output_values):
                                    output_value_field = ui.StringField(identifier="OutputField")
                                    output_value_field.model.set_value(value)
                                    self._field_validate_subs.append(
                                        output_value_field.model.subscribe_end_edit_fn(
                                            partial(
                                                self._on_output_field_edit_end,
                                                schema_data,
                                                attr_name,
                                                index,
                                                value_index=value_index if len(output_values) > 1 else None,
                                            )
                                        )
                                    )
                            ui.Spacer(height=ui.Pixel(4), width=0)

        await self._deferred_update_label_widths(labels)

    @usd.handle_exception
    async def _deferred_update_label_widths(self, labels: List[ui.Label]):
        await omni.kit.app.get_app().next_update_async()

        max_width = 0
        for label in labels:
            max_width = max(max_width, label.computed_width)
        for label in labels:
            label.width = ui.Pixel(max_width)

    def destroy(self):
        self._fixed = None
        self._field_validate_subs = None
