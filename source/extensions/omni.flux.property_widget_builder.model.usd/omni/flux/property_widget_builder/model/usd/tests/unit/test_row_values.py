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

from unittest.mock import Mock, call, patch

import omni.kit.commands
import omni.kit.test
import omni.kit.undo
import omni.usd
from omni.flux.property_widget_builder.model.usd import USDLogicalGroupOutletItem
from omni.flux.property_widget_builder.model.usd import items
from omni.flux.property_widget_builder.model.usd.item_model.attr_list_model_value import UsdListModelAttrValueModel
from omni.flux.property_widget_builder.model.usd.item_model.metadata_list_model_value import (
    UsdListModelAttrMetadataValueModel,
)
from omni.flux.property_widget_builder.model.usd.logical_row import LogicalGroupDefinition
from omni.flux.utils.common import interactive_usd_notices
from pxr import Sdf, Vt

__all__ = ["TestRowValues"]


class TestRowValues(omni.kit.test.AsyncTestCase):
    """Exercise logical row dispatch and USD dropdown policy without native writes."""

    async def test_logical_outlet_declaration_preserves_group_suffix_and_legacy_order(self):
        """Expand logical groups and legacy companions in their declared order."""
        # Arrange
        row = USDLogicalGroupOutletItem({"curve_map": {"second": {}, "first": {}}}, "", ["/Target"])
        row.logical_group_definition = LogicalGroupDefinition(suffixes=("values", "times"), widget_kind="curve")
        row.logical_group_extra_attribute_names = ("legacyMax", "legacyMin")
        self.addCleanup(row.destroy)

        # Act
        names = row.get_logical_row_attribute_names()

        # Assert
        self.assertEqual(
            names, ["second:values", "second:times", "first:values", "first:times", "legacyMax", "legacyMin"]
        )

    async def test_logical_outlet_read_only_honors_owned_models_without_display_models(self):
        """Derive outlet editability from owned models rather than empty display models."""
        for owned_models, expected in (([], False), ([Mock(read_only=False)], False), ([Mock(read_only=True)], True)):
            with self.subTest(expected=expected, owned_models=owned_models):
                # Arrange
                row = USDLogicalGroupOutletItem({"curve_map": {"curve": {}}}, "", ["/Target"])
                row.logical_group_items = [Mock(value_models=owned_models)]
                self.addCleanup(row.destroy)

                # Act
                read_only = row.read_only

                # Assert
                self.assertEqual(row.value_models, [])
                self.assertEqual(read_only, expected)

    async def test_set_logical_row_values_wrong_cardinality_executes_no_commands(self):
        """Reject incomplete logical values before executing authoring commands."""
        # Arrange
        row = USDLogicalGroupOutletItem({"curve_map": {"curve": {}}}, "", ["/Target"])
        row.logical_group_definition = LogicalGroupDefinition(suffixes=("times", "values"), widget_kind="curve")
        self.addCleanup(row.destroy)

        # Act
        with patch.object(omni.kit.commands, "execute") as execute, self.assertRaises(ValueError):
            row.set_row_values(([0.0],))

        # Assert
        execute.assert_not_called()

    async def test_set_logical_row_values_reported_failure_stops_later_attributes_and_targets(self):
        """Stop logical and legacy writes on reported failure without requesting rollback."""
        for result in ((False, None), (True, False)):
            for failure_index in (1, 8, 9):
                with self.subTest(result=result, failure_index=failure_index):
                    # Arrange
                    row = USDLogicalGroupOutletItem({"curve_map": {"first": {}, "second": {}}}, "", ["/A", "/B"])
                    row.logical_group_definition = LogicalGroupDefinition(
                        suffixes=("times", "values"), widget_kind="curve"
                    )
                    row.logical_group_extra_attribute_names = ("legacy",)
                    self.addCleanup(row.destroy)
                    results = [(True, None)] * failure_index + [result]
                    stage = Mock()
                    stage.GetAttributeAtPath.return_value.Get.return_value = [-1.0]

                    with (
                        patch.object(omni.kit.commands, "execute", side_effect=results) as execute,
                        patch.object(omni.kit.undo, "undo") as undo,
                        patch.object(omni.usd, "get_context") as context,
                        patch.object(interactive_usd_notices, "begin_interaction"),
                        patch.object(interactive_usd_notices, "end_interaction"),
                    ):
                        context.return_value.get_stage.return_value = stage

                        # Act
                        with self.assertRaises(RuntimeError):
                            row.set_row_values(([0.0], [1.0], [0.0], [2.0], 3.0))

                    # Assert
                    self.assertEqual(execute.call_count, failure_index + 1)
                    undo.assert_not_called()

    async def test_set_logical_row_values_uses_native_commands_in_canonical_target_order(self):
        """Skip unchanged animated values while preserving clears, empty arrays, and legacy writes."""
        for title, prepared, previous, expected_names, expected_normalizations in (
            ("changed", ([0.0], [2.0], 3.0), ([-1.0], [-2.0], 3.0), ("curve:times", "curve:values", "legacy"), 6),
            ("unchanged", ([0.0], [2.0], 3.0), (Vt.DoubleArray([0.0]), Vt.FloatArray([2.0]), 3.0), ("legacy",), 6),
            ("clear", (None, None, 3.0), (None, None, 3.0), ("curve:times", "curve:values", "legacy"), 0),
            ("empty", ([], [], 3.0), ([0.0], [2.0], 3.0), ("curve:times", "curve:values", "legacy"), 6),
        ):
            with self.subTest(title=title):
                # Arrange
                row = USDLogicalGroupOutletItem({"curve_map": {"curve": {}}}, "row_context", ["/A", "/B"])
                row.logical_group_definition = LogicalGroupDefinition(suffixes=("times", "values"), widget_kind="curve")
                row.logical_group_extra_attribute_names = ("legacy",)
                self.addCleanup(row.destroy)
                values = dict(zip(("curve:times", "curve:values", "legacy"), prepared))
                attributes = {}
                for name, value in zip(("curve:times", "curve:values", "legacy"), previous):
                    attribute = Mock()
                    attribute.Get.return_value = value
                    attribute.GetTypeName.return_value = (
                        Sdf.ValueTypeNames.Float if name == "legacy" else Sdf.ValueTypeNames.FloatArray
                    )
                    attributes[name] = attribute
                stage = Mock()
                stage.GetAttributeAtPath.side_effect = lambda path, attributes=attributes: attributes[path.name]
                with (
                    patch.object(row, "get_target_paths", wraps=row.get_target_paths) as get_target_paths,
                    patch.object(
                        items, "normalize_value_for_signature", wraps=items.normalize_value_for_signature
                    ) as normalize,
                    patch.object(omni.kit.commands, "execute", return_value=(True, None)) as execute,
                    patch.object(omni.kit.undo, "group") as group,
                    patch.object(omni.usd, "get_context") as context,
                    patch.object(interactive_usd_notices, "begin_interaction") as begin,
                    patch.object(interactive_usd_notices, "end_interaction") as end,
                ):
                    context.return_value.get_stage.return_value = stage

                    # Act
                    row.set_row_values(prepared)

                # Assert
                get_target_paths.assert_called_once_with()
                self.assertEqual(normalize.call_count, expected_normalizations)
                self.assertEqual(
                    execute.call_args_list,
                    [
                        call(
                            "ChangeProperty",
                            prop_path=Sdf.Path(target).AppendProperty(name),
                            value=values[name],
                            prev=None,
                            usd_context_name="row_context",
                        )
                        for name in expected_names
                        for target in ("/A", "/B")
                    ],
                )
                group.assert_not_called()
                begin.assert_called_once_with(stage)
                end.assert_called_once_with(begin.return_value)

    async def test_numeric_dropdown_labels_reach_existing_authoring_without_conversion(self):
        """Preserve numeric-looking labels until the existing dropdown authoring policy handles them."""
        for model_class in (UsdListModelAttrValueModel, UsdListModelAttrMetadataValueModel):
            for index, label in enumerate(("0", "01", "1.5")):
                with self.subTest(model_class=model_class, label=label):
                    # Arrange
                    with patch.object(model_class, "init_attributes"):
                        model = model_class(
                            "",
                            [Sdf.Path("/Target.mode")],
                            "0",
                            ["0", "01", "1.5"],
                            value_type_name=Sdf.ValueTypeNames.Int,
                            metadata_key="customData",
                        )
                    model._stage = Mock()
                    model.refresh = Mock()
                    self.addCleanup(model.destroy)
                    attribute = Mock()
                    attribute.GetPath.return_value = Sdf.Path("/Target.mode")
                    model._write_value_to_usd = lambda model=model, attribute=attribute: (
                        model._set_attribute_value(attribute, model.get_value(), Mock()),
                        True,
                    )

                    # Act
                    with patch.object(omni.kit.commands, "execute", return_value=(True, None)) as execute:
                        model.set_value(label)

                    # Assert
                    self.assertEqual(model.get_value(), label)
                    self.assertEqual(model.default_value, "0")
                    self.assertEqual(
                        execute.call_args.kwargs["value"], index if model_class is UsdListModelAttrValueModel else label
                    )
