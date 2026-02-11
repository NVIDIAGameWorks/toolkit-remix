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

from contextlib import nullcontext
from unittest.mock import Mock, call, patch

import omni.kit.commands
import omni.kit.test
from omni.flux.validator.plugin.check.usd.xform.reset_pivot import ResetPivot
from pxr import Sdf


class TestResetPivot(omni.kit.test.AsyncTestCase):
    async def test_data_translate_format_valid_invalid_should_raise_value_error(self):
        await self.__run_test_data_translate_format_valid_(False, (0, 1, 2, 3, 4))
        await self.__run_test_data_translate_format_valid_(False, (0, 1))
        await self.__run_test_data_translate_format_valid_(False, ("a", "b", "c"))

    async def test_data_translate_format_valid_valid_should_return_value(self):
        await self.__run_test_data_translate_format_valid_(True, (0, 1, 2))
        await self.__run_test_data_translate_format_valid_(True, (0.0, 1.0, 2.0))

    async def test_check_no_pivot_and_root_value_should_skip_check(self):
        # Arrange
        reset_pivot = ResetPivot()

        schema_data_mock = Mock()
        schema_data_mock.pivot_position = (0.0, 0.0, 0.0)

        context_plugin_data_mock = Mock()

        mock_selection = Mock()
        mock_selection.GetAttribute.return_value = None

        selector_plugin_data_mock = [mock_selection]

        with patch.object(ResetPivot, "on_progress") as progress_mock:
            # Act
            success, message, data = await reset_pivot._check(
                schema_data_mock, context_plugin_data_mock, selector_plugin_data_mock
            )

        # Assert
        progress_message = "- SKIPPED: Prim has no pivot attribute. Default pivot transform is valid."

        self.assertTrue(success)
        self.assertEqual(f"Check:\n{progress_message}\n", message)
        self.assertIsNone(data)

        self.assertEqual(2, progress_mock.call_count)
        self.assertEqual(call(0, "Start", True), progress_mock.call_args_list[0])
        self.assertEqual(call(1, progress_message, True), progress_mock.call_args_list[1])

    async def test_check_invalid_pivot_should_fail_check(self):
        # Arrange
        reset_pivot = ResetPivot()

        schema_data_mock = Mock()
        schema_data_mock.pivot_position = (0.0, 0.0, 0.0)

        context_plugin_data_mock = Mock()

        mock_value = Mock()
        mock_value.Get.return_value = (1.0, 2.0, 3.0)
        mock_selection = Mock()
        mock_selection.GetAttribute.return_value = mock_value

        selector_plugin_data_mock = [mock_selection]

        with patch.object(ResetPivot, "on_progress") as progress_mock:
            # Act
            success, message, data = await reset_pivot._check(
                schema_data_mock, context_plugin_data_mock, selector_plugin_data_mock
            )

        # Assert
        progress_message = "- INVALID: Prim has an invalid pivot transform"

        self.assertFalse(success)
        self.assertEqual(f"Check:\n{progress_message}\n", message)
        self.assertIsNone(data)

        self.assertEqual(2, progress_mock.call_count)
        self.assertEqual(call(0, "Start", True), progress_mock.call_args_list[0])
        self.assertEqual(call(1, progress_message, False), progress_mock.call_args_list[1])

    async def test_check_valid_pivot_should_succeed_check(self):
        # Arrange
        reset_pivot = ResetPivot()

        target_pivot = (1.0, 1.0, 1.0)

        schema_data_mock = Mock()
        schema_data_mock.pivot_position = target_pivot

        context_plugin_data_mock = Mock()

        mock_value = Mock()
        mock_value.Get.return_value = target_pivot
        mock_selection = Mock()
        mock_selection.GetAttribute.return_value = mock_value

        selector_plugin_data_mock = [mock_selection]

        with patch.object(ResetPivot, "on_progress") as progress_mock:
            # Act
            success, message, data = await reset_pivot._check(
                schema_data_mock, context_plugin_data_mock, selector_plugin_data_mock
            )

        # Assert
        progress_message = "- OK: Prim has the proper pivot transform"

        self.assertTrue(success)
        self.assertEqual(f"Check:\n{progress_message}\n", message)
        self.assertIsNone(data)

        self.assertEqual(2, progress_mock.call_count)
        self.assertEqual(call(0, "Start", True), progress_mock.call_args_list[0])
        self.assertEqual(call(1, progress_message, True), progress_mock.call_args_list[1])

    async def test_fix_no_pivot_and_root_value_should_skip_fix(self):
        # Arrange
        reset_pivot = ResetPivot()

        schema_data_mock = Mock()
        schema_data_mock.pivot_position = (0.0, 0.0, 0.0)

        context_plugin_data_mock = Mock()

        mock_selection = Mock()
        mock_selection.GetAttribute.return_value = None
        selector_plugin_data_mock = [mock_selection]

        with (
            patch.object(ResetPivot, "on_progress") as progress_mock,
            patch.object(omni.kit.commands, "execute") as execute_mock,
        ):
            # Act
            success, message, data = await reset_pivot._fix(
                schema_data_mock, context_plugin_data_mock, selector_plugin_data_mock
            )

        # Assert
        progress_message = "- SKIPPED: Prim has no pivot attribute. Default pivot is valid."

        self.assertTrue(success)
        self.assertEqual(f"Fix:\n{progress_message}\n", message)
        self.assertIsNone(data)

        self.assertEqual(2, progress_mock.call_count)
        self.assertEqual(call(0, "Start", True), progress_mock.call_args_list[0])
        self.assertEqual(call(1, progress_message, True), progress_mock.call_args_list[1])

        self.assertEqual(0, execute_mock.call_count)

    async def test_fix_valid_pivot_should_skip_fix(self):
        # Arrange
        reset_pivot = ResetPivot()

        target_pivot = (1.0, 1.0, 1.0)

        schema_data_mock = Mock()
        schema_data_mock.pivot_position = target_pivot

        context_plugin_data_mock = Mock()

        mock_value = Mock()
        mock_value.Get.return_value = target_pivot
        mock_selection = Mock()
        mock_selection.GetAttribute.return_value = mock_value
        selector_plugin_data_mock = [mock_selection]

        with (
            patch.object(ResetPivot, "on_progress") as progress_mock,
            patch.object(omni.kit.commands, "execute") as execute_mock,
        ):
            # Act
            success, message, data = await reset_pivot._fix(
                schema_data_mock, context_plugin_data_mock, selector_plugin_data_mock
            )

        # Assert
        progress_message = "- SKIPPED: Prim has the proper pivot transform"

        self.assertTrue(success)
        self.assertEqual(f"Fix:\n{progress_message}\n", message)
        self.assertIsNone(data)

        self.assertEqual(2, progress_mock.call_count)
        self.assertEqual(call(0, "Start", True), progress_mock.call_args_list[0])
        self.assertEqual(call(1, progress_message, True), progress_mock.call_args_list[1])

        self.assertEqual(0, execute_mock.call_count)

    async def test_fix_invalid_pivot_should_change_property_and_succeed(self):
        # Arrange
        reset_pivot = ResetPivot()

        target_value = (0.0, 0.0, 0.0)
        prim_path_mock = "/Root/Test"

        schema_data_mock = Mock()
        schema_data_mock.pivot_position = target_value

        context_plugin_data_mock = Mock()

        mock_value = Mock()
        mock_value.Get.return_value = (1.0, 1.0, 1.0)
        mock_selection = Mock()
        mock_selection.GetAttribute.return_value = mock_value
        mock_selection.GetPath.return_value = Sdf.Path(prim_path_mock)
        selector_plugin_data_mock = [mock_selection]

        with (
            patch.object(ResetPivot, "on_progress") as progress_mock,
            patch.object(omni.kit.commands, "execute") as execute_mock,
        ):
            # Act
            success, message, data = await reset_pivot._fix(
                schema_data_mock, context_plugin_data_mock, selector_plugin_data_mock
            )

        # Assert
        progress_message = f"- FIXED: Prim pivot set to {target_value}"

        self.assertTrue(success)
        self.assertEqual(f"Fix:\n{progress_message}\n", message)
        self.assertIsNone(data)

        self.assertEqual(2, progress_mock.call_count)
        self.assertEqual(call(0, "Start", True), progress_mock.call_args_list[0])
        self.assertEqual(call(1, progress_message, True), progress_mock.call_args_list[1])

        self.assertEqual(1, execute_mock.call_count)
        self.assertEqual(
            call(
                "ChangePropertyCommand",
                prop_path=f"{prim_path_mock}.{ResetPivot._ATTRIBUTE_NAME}",
                value=target_value,
                prev=None,
                type_to_create_if_not_exist=Sdf.ValueTypeNames.Vector3d,
                usd_context_name=context_plugin_data_mock,
            ),
            execute_mock.call_args,
        )

    async def __run_test_data_translate_format_valid_(self, is_valid: bool, value: tuple):
        # Arrange
        pass

        # Act
        with nullcontext() if is_valid else self.assertRaises(ValueError) as cm:
            v = ResetPivot.Data.translate_format_valid(value)

        # Assert
        if is_valid:
            self.assertEqual(value, v)
        else:
            self.assertEqual(
                "The pivot position must be represented by a tuple of 3 float in the format (X,Y,Z).", str(cm.exception)
            )
