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

import asyncio
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

import carb.settings
import omni.kit.app
import omni.ui as ui
from lightspeed.trex.packaging.core.enum import ModPackagingMode
from lightspeed.trex.packaging.widget import setup_ui as _setup_ui
from lightspeed.trex.packaging.widget.setup_ui import PackagingPane
from omni.flux.asset_importer.core.data_models import UsdExtensions as _UsdExtensions
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows


async def _create_widget(window_name: str) -> tuple[ui.Window, PackagingPane]:
    window = ui.Window(window_name, width=600, height=800)
    with window.frame:
        widget = PackagingPane("")
    await omni.kit.app.get_app().next_update_async()
    return window, widget


class TestPackagingPaneMode(AsyncTestCase):
    async def setUp(self):
        self._settings = carb.settings.get_settings()
        self._clear_packaging_settings()
        await arrange_windows()

    async def tearDown(self):
        self._clear_packaging_settings()

    def _clear_packaging_settings(self):
        self._settings.destroy_item(_setup_ui._SETTINGS_PACKAGING_MODE)
        self._settings.destroy_item(_setup_ui._SETTINGS_OUTPUT_FORMAT)

    async def test_packaging_mode_dropdown_defaults_to_flatten(self):
        window, widget = await _create_widget("test_packaging_mode_default")

        try:
            # Arrange

            # Act
            selected_mode = widget._get_selected_packaging_mode()

            # Assert
            self.assertEqual(ModPackagingMode.FLATTEN, selected_mode)
        finally:
            widget.destroy()
            window.destroy()

    async def test_packaging_options_should_persist_across_widget_recreation(self):
        first_window, first_widget = await _create_widget("test_packaging_options_persist_first")

        try:
            # Arrange
            first_widget._packaging_mode_combo.model.get_item_value_model().set_value(1)
            first_widget._packaging_output_format_combo.model.get_item_value_model().set_value(3)
            await omni.kit.app.get_app().next_update_async()
        finally:
            first_widget.destroy()
            first_window.destroy()

        second_window, second_widget = await _create_widget("test_packaging_options_persist_second")

        try:
            # Act
            selected_mode = second_widget._get_selected_packaging_mode()
            selected_format = second_widget._get_selected_packaging_output_format()

            # Assert
            self.assertEqual(ModPackagingMode.IMPORT, selected_mode)
            self.assertEqual(_UsdExtensions.USDC, selected_format)
        finally:
            second_widget.destroy()
            second_window.destroy()

    async def test_packaging_mode_dropdown_redirect_value_maps_to_enum(self):
        window, widget = await _create_widget("test_packaging_mode_redirect")

        try:
            # Arrange
            value_model = widget._packaging_mode_combo.model.get_item_value_model()
            value_model.set_value(0)
            await omni.kit.app.get_app().next_update_async()

            # Act
            selected_mode = widget._get_selected_packaging_mode()

            # Assert
            self.assertEqual(ModPackagingMode.REDIRECT, selected_mode)
        finally:
            widget.destroy()
            window.destroy()

    async def test_packaging_mode_dropdown_import_value_maps_to_enum(self):
        window, widget = await _create_widget("test_packaging_mode_import")

        try:
            # Arrange
            value_model = widget._packaging_mode_combo.model.get_item_value_model()
            value_model.set_value(1)
            await omni.kit.app.get_app().next_update_async()

            # Act
            selected_mode = widget._get_selected_packaging_mode()

            # Assert
            self.assertEqual(ModPackagingMode.IMPORT, selected_mode)
        finally:
            widget.destroy()
            window.destroy()

    async def test_packaging_mode_dropdown_flatten_value_maps_to_enum(self):
        window, widget = await _create_widget("test_packaging_mode_flatten")

        try:
            # Arrange
            value_model = widget._packaging_mode_combo.model.get_item_value_model()
            value_model.set_value(2)
            await omni.kit.app.get_app().next_update_async()

            # Act
            selected_mode = widget._get_selected_packaging_mode()

            # Assert
            self.assertEqual(ModPackagingMode.FLATTEN, selected_mode)
        finally:
            widget.destroy()
            window.destroy()

    async def test_packaging_output_format_dropdown_defaults_to_usd(self):
        window, widget = await _create_widget("test_packaging_output_format_default")

        try:
            # Arrange

            # Act
            selected_format = widget._get_selected_packaging_output_format()

            # Assert
            self.assertEqual(_UsdExtensions.USD, selected_format)
        finally:
            widget.destroy()
            window.destroy()

    async def test_packaging_output_format_dropdown_preserve_value_maps_to_enum(self):
        window, widget = await _create_widget("test_packaging_output_format_preserve")

        try:
            # Arrange
            value_model = widget._packaging_output_format_combo.model.get_item_value_model()
            value_model.set_value(0)
            await omni.kit.app.get_app().next_update_async()

            # Act
            selected_format = widget._get_selected_packaging_output_format()

            # Assert
            self.assertIsNone(selected_format)
        finally:
            widget.destroy()
            window.destroy()

    async def test_packaging_output_format_dropdown_usda_value_maps_to_enum(self):
        window, widget = await _create_widget("test_packaging_output_format_usda")

        try:
            # Arrange
            value_model = widget._packaging_output_format_combo.model.get_item_value_model()
            value_model.set_value(2)
            await omni.kit.app.get_app().next_update_async()

            # Act
            selected_format = widget._get_selected_packaging_output_format()

            # Assert
            self.assertEqual(_UsdExtensions.USDA, selected_format)
        finally:
            widget.destroy()
            window.destroy()

    async def test_packaging_output_format_dropdown_usdc_value_maps_to_enum(self):
        window, widget = await _create_widget("test_packaging_output_format_usdc")

        try:
            # Arrange
            value_model = widget._packaging_output_format_combo.model.get_item_value_model()
            value_model.set_value(3)
            await omni.kit.app.get_app().next_update_async()

            # Act
            selected_format = widget._get_selected_packaging_output_format()

            # Assert
            self.assertEqual(_UsdExtensions.USDC, selected_format)
        finally:
            widget.destroy()
            window.destroy()

    async def test_packaging_options_tooltip_explains_modes_and_output_formats(self):
        # Arrange

        # Act
        tooltip = PackagingPane._get_packaging_options_tooltip()

        # Assert
        self.assertIn("Redirect dependencies", tooltip)
        self.assertIn("Import dependencies", tooltip)
        self.assertIn("Flatten into one layer", tooltip)
        self.assertIn("only keeps assets still referenced by the flattened output", tooltip)
        self.assertIn("Preserve Extensions", tooltip)
        self.assertIn("usd", tooltip)
        self.assertIn("usda", tooltip)
        self.assertIn("usdc", tooltip)

    async def test_packaging_options_section_info_icon_is_created(self):
        window, widget = await _create_widget("test_packaging_mode_info_icon")

        try:
            # Arrange

            # Act
            info_widget = widget._package_mode_collapsable_frame.get_info_widget()

            # Assert
            self.assertIsNotNone(info_widget)
        finally:
            widget.destroy()
            window.destroy()


class TestPackagingPaneCompletion(AsyncTestCase):
    async def setUp(self):
        await arrange_windows()

    async def test_successful_packaging_opens_output_directory(self):
        window, widget = await _create_widget("test_packaging_completion_success")

        try:
            # Arrange
            widget._package_output_widget.refresh_output_directory_state = Mock()
            widget._package_output_widget.open_output_path = Mock()

            with patch("lightspeed.trex.packaging.widget.setup_ui._TrexMessageDialog") as message_dialog_mock:
                # Act
                await widget._on_packaging_completed([], [], False)

            # Assert
            widget._package_output_widget.refresh_output_directory_state.assert_called_once_with()
            widget._package_output_widget.open_output_path.assert_called_once_with()
            message_dialog_mock.assert_called_once_with(
                "The mod was successfully packaged.", "Mod Packaging Successful", disable_cancel_button=True
            )
        finally:
            widget.destroy()
            window.destroy()

    async def test_cancelled_packaging_does_not_open_output_directory(self):
        window, widget = await _create_widget("test_packaging_completion_cancelled")

        try:
            # Arrange
            widget._package_output_widget.refresh_output_directory_state = Mock()
            widget._package_output_widget.open_output_path = Mock()

            with patch("lightspeed.trex.packaging.widget.setup_ui._TrexMessageDialog") as message_dialog_mock:
                # Act
                await widget._on_packaging_completed([], [], True)

            # Assert
            widget._package_output_widget.refresh_output_directory_state.assert_not_called()
            widget._package_output_widget.open_output_path.assert_not_called()
            message_dialog_mock.assert_called_once_with(
                "The mod packaging process was cancelled.", "Mod Packaging Cancelled", disable_cancel_button=True
            )
        finally:
            widget.destroy()
            window.destroy()

    async def test_delete_existing_output_directory_should_happen_before_packaging_starts(self):
        window, widget = await _create_widget("test_packaging_delete_existing_output")

        try:
            # Arrange
            widget._context = None
            widget._layer_manager.get_layers_of_type = Mock(
                return_value=[Mock(realPath="C:/projects/MainProject/mod.usda")]
            )
            widget._package_output_widget.refresh_output_directory_state = Mock(return_value=False)

            with tempfile.TemporaryDirectory() as tmp_dir:
                output_directory = Path(tmp_dir) / "package"
                output_directory.mkdir()
                package_file = output_directory / "mod.usd"
                package_file.write_text("existing package", encoding="utf-8")
                widget._package_output_widget._output_field.model.set_value(output_directory.as_posix())

                callback_order = []
                package_started = asyncio.Event()

                async def delete_side_effect(path: str):
                    callback_order.append("delete")
                    self.assertEqual(output_directory.as_posix(), path.replace("\\", "/"))
                    self.assertTrue(package_file.exists())
                    shutil.rmtree(output_directory)

                def package_side_effect(_):
                    callback_order.append("package")
                    self.assertFalse(output_directory.exists())
                    package_started.set()

                widget._packaging_core.package = Mock(side_effect=package_side_effect)

                with (
                    patch.object(
                        type(widget._package_layers_widget),
                        "packaged_layers",
                        new_callable=PropertyMock,
                        return_value=["C:/projects/MainProject/mod.usda"],
                    ),
                    patch.object(
                        type(widget._package_details_widget),
                        "mod_name",
                        new_callable=PropertyMock,
                        return_value="Test Mod",
                    ),
                    patch.object(
                        type(widget._package_details_widget),
                        "mod_version",
                        new_callable=PropertyMock,
                        return_value="1.0.0",
                    ),
                    patch.object(
                        type(widget._package_details_widget),
                        "mod_details",
                        new_callable=PropertyMock,
                        return_value="",
                    ),
                    patch(
                        "lightspeed.trex.packaging.widget.setup_ui._OmniClientWrapper.delete",
                        new=AsyncMock(side_effect=delete_side_effect),
                    ) as delete_mock,
                    patch("lightspeed.trex.packaging.widget.setup_ui._TrexMessageDialog") as message_dialog_mock,
                ):
                    # Act
                    widget._on_package_pressed()
                    delete_handler = message_dialog_mock.call_args.kwargs["ok_handler"]
                    delete_handler()
                    await asyncio.wait_for(package_started.wait(), timeout=1)

                # Assert
                delete_mock.assert_called_once_with(output_directory.as_posix())
                widget._package_output_widget.refresh_output_directory_state.assert_called_once_with()
                widget._packaging_core.package.assert_called_once_with(
                    {
                        "context_name": widget._MOD_PACKAGING_CONTEXT,
                        "mod_layer_paths": ["C:/projects/MainProject/mod.usda"],
                        "selected_layer_paths": ["C:/projects/MainProject/mod.usda"],
                        "output_directory": output_directory.as_posix(),
                        "packaging_mode": widget._get_selected_packaging_mode(),
                        "output_format": widget._get_selected_packaging_output_format(),
                        "mod_name": "Test Mod",
                        "mod_version": "1.0.0",
                        "mod_details": "",
                        "ignored_errors": None,
                    }
                )
                self.assertEqual(["delete", "package"], callback_order)
        finally:
            widget.destroy()
            window.destroy()


class TestPackagingPaneSubscriptionLifecycle(AsyncTestCase):
    async def setUp(self):
        await arrange_windows()

    async def test_subscriptions_none_initially(self):
        window, widget = await _create_widget("test_subscriptions")

        try:
            # Arrange

            # Act
            packaging_progress_sub = widget._packaging_progress_sub
            packaging_completed_sub = widget._packaging_completed_sub

            # Assert
            self.assertIsNone(packaging_progress_sub)
            self.assertIsNone(packaging_completed_sub)
        finally:
            widget.destroy()
            window.destroy()
