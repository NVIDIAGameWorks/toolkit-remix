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

from unittest.mock import Mock, call, patch

import omni.kit.test
from omni.flux.validator.plugin.check.usd.xform.apply_unit_scale import ApplyUnitScale
from pxr import UsdGeom


class TestApplyUnitScale(omni.kit.test.AsyncTestCase):
    async def test_data_non_zero_positive_number_zero_should_raise_value_error(self):
        # Arrange
        val = 0

        # Act
        with self.assertRaises(ValueError) as cm:
            ApplyUnitScale.Data.non_zero_positive_number(val)

        # Assert
        self.assertEqual("The target scale unit scale should be a non-zero positive number", str(cm.exception))

    async def test_data_non_zero_positive_number_negative_should_raise_value_error(self):
        # Arrange
        val = -10

        # Act
        with self.assertRaises(ValueError) as cm:
            ApplyUnitScale.Data.non_zero_positive_number(val)

        # Assert
        self.assertEqual("The target scale unit scale should be a non-zero positive number", str(cm.exception))

    async def test_data_non_zero_positive_number_positive_should_return_value(self):
        # Arrange
        val = 10

        # Act
        v = ApplyUnitScale.Data.non_zero_positive_number(val)

        # Assert
        self.assertEqual(val, v)

    async def test_check_no_unit_scale_metadata_should_skip_check(self):
        # Arrange
        material_shader = ApplyUnitScale()

        context_plugin_data_mock = Mock()
        context_plugin_data_mock.GetMetadata.return_value = None

        usd_context_mock = Mock()
        usd_context_mock.get_stage.return_value = context_plugin_data_mock

        with (
            patch.object(ApplyUnitScale, "on_progress") as progress_mock,
            patch(
                "omni.flux.validator.plugin.check.usd.xform.apply_unit_scale.omni.usd.get_context"
            ) as omni_usd_mockup,
        ):
            omni_usd_mockup.return_value = usd_context_mock
            # Act
            success, message, data = await material_shader._check(Mock(), Mock(), [])  # noqa PLW0212

        # Assert
        self.assertTrue(success)
        self.assertEqual("Check:\n- SKIPPED: Unable to get the layer's unit scale", message)
        self.assertIsNone(data)

        self.assertEqual(1, progress_mock.call_count)
        self.assertEqual(call(0, "Start", True), progress_mock.call_args)

    async def test_check_not_equal_target_should_return_invalid_and_message(self):
        # Arrange
        material_shader = ApplyUnitScale()

        schema_data_mock = Mock()
        schema_data_mock.meters_per_unit_target = 1

        context_plugin_data_mock = Mock()
        context_plugin_data_mock.GetMetadata.return_value = 2

        usd_context_mock = Mock()
        usd_context_mock.get_stage.return_value = context_plugin_data_mock

        with (
            patch.object(ApplyUnitScale, "on_progress") as progress_mock,
            patch(
                "omni.flux.validator.plugin.check.usd.xform.apply_unit_scale.omni.usd.get_context"
            ) as omni_usd_mockup,
        ):
            omni_usd_mockup.return_value = usd_context_mock
            # Act
            success, message, data = await material_shader._check(schema_data_mock, Mock(), [])  # noqa PLW0212

        # Assert
        self.assertFalse(success)
        self.assertEqual("Check:\n- INVALID: Layer scale needs to be applied to the asset", message)
        self.assertIsNone(data)

        self.assertEqual(1, progress_mock.call_count)
        self.assertEqual(call(0, "Start", True), progress_mock.call_args)

    async def test_check_equal_target_should_return_success_and_message(self):
        # Arrange
        material_shader = ApplyUnitScale()

        schema_data_mock = Mock()
        schema_data_mock.meters_per_unit_target = 1

        context_plugin_data_mock = Mock()
        context_plugin_data_mock.GetMetadata.return_value = 1

        usd_context_mock = Mock()
        usd_context_mock.get_stage.return_value = context_plugin_data_mock

        with (
            patch.object(ApplyUnitScale, "on_progress") as progress_mock,
            patch(
                "omni.flux.validator.plugin.check.usd.xform.apply_unit_scale.omni.usd.get_context"
            ) as omni_usd_mockup,
        ):
            omni_usd_mockup.return_value = usd_context_mock
            # Act
            success, message, data = await material_shader._check(schema_data_mock, Mock(), [])  # noqa PLW0212

        # Assert
        self.assertTrue(success)
        self.assertEqual("Check:\n- OK: Layer is using the appropriate unit scale", message)
        self.assertIsNone(data)

        self.assertEqual(1, progress_mock.call_count)
        self.assertEqual(call(0, "Start", True), progress_mock.call_args)

    async def test_fix_no_selector_plugin_data_should_fix_metadata(self):
        # Arrange
        material_shader = ApplyUnitScale()

        meters_per_unit_target = 1

        schema_data_mock = Mock()
        schema_data_mock.meters_per_unit_target = meters_per_unit_target

        context_plugin_data_mock = Mock()
        context_plugin_data_mock.GetMetadata.return_value = 0.01
        set_metadata_mock = context_plugin_data_mock.SetMetadata

        usd_context_mock = Mock()
        usd_context_mock.get_stage.return_value = context_plugin_data_mock

        with (
            patch.object(ApplyUnitScale, "on_progress") as progress_mock,
            patch(
                "omni.flux.validator.plugin.check.usd.xform.apply_unit_scale.omni.usd.get_context"
            ) as omni_usd_mockup,
        ):
            omni_usd_mockup.return_value = usd_context_mock
            # Act
            success, message, data = await material_shader._fix(schema_data_mock, Mock(), [])  # noqa PLW0212

        # Assert
        self.assertTrue(success)
        self.assertEqual("Fix:\n- FIXED: Updated layer unit scale\n", message)
        self.assertIsNone(data)

        self.assertEqual(1, progress_mock.call_count)
        self.assertEqual(call(0, "Start", True), progress_mock.call_args)

        self.assertEqual(1, set_metadata_mock.call_count)
        self.assertEqual(
            call(ApplyUnitScale._METADATA_KEY, meters_per_unit_target), set_metadata_mock.call_args  # noqa PLW0212
        )

    async def test_fix_not_an_xform_prim_should_skip(self):
        # Arrange
        material_shader = ApplyUnitScale()

        meters_per_unit_target = 1

        schema_data_mock = Mock()
        schema_data_mock.meters_per_unit_target = meters_per_unit_target

        context_plugin_data_mock = Mock()
        context_plugin_data_mock.GetMetadata.return_value = 0.01
        set_metadata_mock = context_plugin_data_mock.SetMetadata

        usd_context_mock = Mock()
        usd_context_mock.get_stage.return_value = context_plugin_data_mock

        xform_prim_path_mock = Mock()
        xform_prim_mock = Mock()
        xform_prim_mock.IsA.return_value = False
        xform_prim_mock.GetPath.return_value = xform_prim_path_mock

        selector_plugin_data_mock = [xform_prim_mock]

        with (
            patch.object(ApplyUnitScale, "on_progress") as progress_mock,
            patch(
                "omni.flux.validator.plugin.check.usd.xform.apply_unit_scale.omni.usd.get_context"
            ) as omni_usd_mockup,
        ):
            omni_usd_mockup.return_value = usd_context_mock
            # Act
            success, message, data = await material_shader._fix(  # noqa PLW0212
                schema_data_mock, Mock(), selector_plugin_data_mock
            )

        # Assert
        expected_progress_message = f"SKIPPED: {xform_prim_path_mock} is not an XForm prim"

        self.assertTrue(success)
        self.assertEqual(f"Fix:\n- {expected_progress_message}\n- FIXED: Updated layer unit scale\n", message)
        self.assertIsNone(data)

        self.assertEqual(2, progress_mock.call_count)
        self.assertEqual(call(0, "Start", True), progress_mock.call_args_list[0])
        self.assertEqual(call(1, expected_progress_message, True), progress_mock.call_args_list[1])

        self.assertEqual(1, set_metadata_mock.call_count)
        self.assertEqual(
            call(ApplyUnitScale._METADATA_KEY, meters_per_unit_target), set_metadata_mock.call_args  # noqa PLW0212
        )

    async def test_fix_should_set_transform_value_and_metadata(self):
        # Arrange
        material_shader = ApplyUnitScale()

        scale_value = 10
        meters_per_unit_target = 2
        meters_per_unit_actual = 4

        schema_data_mock = Mock()
        schema_data_mock.meters_per_unit_target = meters_per_unit_target

        context_plugin_data_mock = Mock()
        context_plugin_data_mock.GetMetadata.return_value = meters_per_unit_actual
        set_metadata_mock = context_plugin_data_mock.SetMetadata

        usd_context_mock = Mock()
        usd_context_mock.get_stage.return_value = context_plugin_data_mock

        xform_prim_path_mock = Mock()
        xform_prim_mock = Mock()
        xform_prim_mock.IsA.return_value = True
        xform_prim_mock.GetPath.return_value = xform_prim_path_mock

        selector_plugin_data_mock = [xform_prim_mock]

        xform_op_mock = Mock()
        xform_op_mock.GetOpType.return_value = UsdGeom.XformOp.TypeScale
        xform_op_mock.Get.return_value = scale_value
        set_mock = xform_op_mock.Set

        xform_mock = Mock()
        xform_mock.GetOrderedXformOps.return_value = [xform_op_mock]

        with (
            patch.object(ApplyUnitScale, "on_progress") as progress_mock,
            patch.object(UsdGeom, "Xformable") as xformable_mock,
            patch(
                "omni.flux.validator.plugin.check.usd.xform.apply_unit_scale.omni.usd.get_context"
            ) as omni_usd_mockup,
        ):
            omni_usd_mockup.return_value = usd_context_mock
            xformable_mock.return_value = xform_mock

            # Act
            success, message, data = await material_shader._fix(  # noqa PLW0212
                schema_data_mock, Mock(), selector_plugin_data_mock
            )

        # Assert
        expected_progress_message = f"FIXED: {xform_prim_path_mock}"

        self.assertTrue(success)
        self.assertEqual(f"Fix:\n- {expected_progress_message}\n- FIXED: Updated layer unit scale\n", message)
        self.assertIsNone(data)

        self.assertEqual(2, progress_mock.call_count)
        self.assertEqual(call(0, "Start", True), progress_mock.call_args_list[0])
        self.assertEqual(call(1, expected_progress_message, True), progress_mock.call_args_list[1])

        self.assertEqual(1, set_metadata_mock.call_count)
        self.assertEqual(
            call(ApplyUnitScale._METADATA_KEY, meters_per_unit_target), set_metadata_mock.call_args  # noqa PLW0212
        )

        self.assertEqual(1, xformable_mock.call_count)
        self.assertEqual(call(xform_prim_mock), xformable_mock.call_args)

        self.assertEqual(1, set_mock.call_count)
        self.assertEqual(call(scale_value * (meters_per_unit_actual / meters_per_unit_target)), set_mock.call_args)

    async def test_on_unit_scale_field_edit_end_value_error_should_update_model_value(self):
        # Arrange
        meters_per_unit_target_mock = Mock()

        schema_data_mock = Mock()
        schema_data_mock.meters_per_unit_target = meters_per_unit_target_mock

        model_mock = Mock()
        model_mock.get_value_as_float.side_effect = ValueError()
        set_value_mock = model_mock.set_value

        apply_unit_scale = ApplyUnitScale()

        # Act
        apply_unit_scale._on_unit_scale_field_edit_end(schema_data_mock, model_mock)  # noqa PLW0212

        # Assert
        self.assertEqual(1, set_value_mock.call_count)
        self.assertEqual(call(meters_per_unit_target_mock), set_value_mock.call_args)

    async def test_on_unit_scale_field_edit_end_should_update_schema_data(self):
        # Arrange
        meters_per_unit_target_mock = Mock()

        schema_data_mock = Mock()
        schema_data_mock.meters_per_unit_target = Mock()

        model_mock = Mock()
        model_mock.get_value_as_float.return_value = meters_per_unit_target_mock

        apply_unit_scale = ApplyUnitScale()

        # Act
        apply_unit_scale._on_unit_scale_field_edit_end(schema_data_mock, model_mock)  # noqa PLW0212

        # Assert
        self.assertEqual(meters_per_unit_target_mock, schema_data_mock.meters_per_unit_target)
