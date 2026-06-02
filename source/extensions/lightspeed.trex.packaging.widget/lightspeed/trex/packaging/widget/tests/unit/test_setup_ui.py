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
import tempfile
import threading
from pathlib import Path
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

import carb.settings
import omni.client
import omni.kit.app
import omni.ui as ui
from lightspeed.trex.packaging.core.enum import ModPackagingMode
from lightspeed.trex.packaging.widget import setup_ui as _setup_ui
from lightspeed.trex.packaging.widget.setup_ui import PackagingPane
from lightspeed.trex.rtxio.core import RtxIoSplitSizePreset
from omni.flux.asset_importer.core.data_models import UsdExtensions as _UsdExtensions
from omni.flux.utils.common.progress import INDETERMINATE_PROGRESS_TOTAL
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

    async def test_packaging_mode_dropdown_uses_persisted_import(self):
        self._settings.set(_setup_ui._SETTINGS_PACKAGING_MODE, ModPackagingMode.IMPORT.value)
        window, widget = await _create_widget("test_packaging_mode_uses_persisted_import")

        try:
            # Act
            selected_mode = widget._get_selected_packaging_mode()

            # Assert
            self.assertEqual(ModPackagingMode.IMPORT, selected_mode)
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
            self.assertEqual(ModPackagingMode.IMPORT.value, self._settings.get(_setup_ui._SETTINGS_PACKAGING_MODE))
        finally:
            widget.destroy()
            window.destroy()

    async def test_packaging_mode_dropdown_flatten_value_maps_to_enum(self):
        window, widget = await _create_widget("test_packaging_mode_flatten")

        try:
            # Arrange
            value_model = widget._packaging_mode_combo.model.get_item_value_model()
            value_model.set_value(0)
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
            widget._packaging_mode_combo.model.get_item_value_model().set_value(1)
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
            widget._packaging_mode_combo.model.get_item_value_model().set_value(1)
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

    async def test_packaging_output_format_dropdown_legacy_usdc_setting_maps_to_usd(self):
        self._settings.set(_setup_ui._SETTINGS_OUTPUT_FORMAT, "usdc")
        window, widget = await _create_widget("test_packaging_output_format_legacy_usdc")

        try:
            # Arrange
            widget._packaging_mode_combo.model.get_item_value_model().set_value(1)
            await omni.kit.app.get_app().next_update_async()

            # Act
            selected_format = widget._get_selected_packaging_output_format()

            # Assert
            self.assertEqual(_UsdExtensions.USD, selected_format)
        finally:
            widget.destroy()
            window.destroy()

    async def test_flatten_mode_disables_output_format_dropdown_and_forces_usd(self):
        window, widget = await _create_widget("test_packaging_flatten_forces_usd")

        try:
            # Arrange
            mode_model = widget._packaging_mode_combo.model.get_item_value_model()
            format_model = widget._packaging_output_format_combo.model.get_item_value_model()
            mode_model.set_value(1)
            format_model.set_value(2)
            await omni.kit.app.get_app().next_update_async()

            # Act
            mode_model.set_value(0)
            await omni.kit.app.get_app().next_update_async()

            # Assert
            self.assertEqual(ModPackagingMode.FLATTEN, widget._get_selected_packaging_mode())
            self.assertEqual(_UsdExtensions.USD, widget._get_selected_packaging_output_format())
            self.assertFalse(widget._packaging_output_format_combo.enabled)
            self.assertIn("USDA text output is disabled", widget._packaging_output_format_combo.tooltip)
        finally:
            widget.destroy()
            window.destroy()

    async def test_packaging_options_tooltip_explains_modes_and_output_formats(self):
        # Arrange

        # Act
        tooltip = PackagingPane._get_packaging_options_tooltip()

        # Assert
        self.assertIn("Flatten into one layer", tooltip)
        self.assertIn("Import dependencies", tooltip)
        self.assertLess(tooltip.index("Flatten into one layer"), tooltip.index("Import dependencies"))
        self.assertNotIn("Redirect dependencies", tooltip)
        self.assertIn("only keeps assets still referenced by the flattened output", tooltip)
        self.assertIn("Preserve Extensions", tooltip)
        self.assertIn("usd", tooltip)
        self.assertIn("usda", tooltip)
        self.assertNotIn("usdc", tooltip)

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

    async def test_rtxio_option_indexes_map_to_named_options(self):
        # Arrange
        split_size_option = PackagingPane._get_rtxio_split_size_option_from_index(2)

        # Act
        disabled_mode = PackagingPane._get_rtxio_mode_from_index(0)
        pack_mode = PackagingPane._get_rtxio_mode_from_index(1)
        disabled_split = PackagingPane._get_rtxio_split_size_option_from_index(0)

        # Assert
        self.assertIs(_setup_ui._RtxIoMode.DISABLED, disabled_mode)
        self.assertIs(_setup_ui._RtxIoMode.PACK, pack_mode)
        self.assertIs(_setup_ui._RtxIoSplitSizeOption.DISABLED, disabled_split)
        self.assertIs(_setup_ui._RtxIoSplitSizeOption.SIZE_2_GB, split_size_option)
        self.assertEqual("2 GB", split_size_option.label)
        self.assertIs(RtxIoSplitSizePreset.SIZE_2_GB, split_size_option.preset)


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

    async def test_package_pressed_without_replacement_layer_should_show_invalid_project_message(self):
        window, widget = await _create_widget("test_packaging_invalid_project")

        try:
            # Arrange
            widget._layer_manager.get_layers_of_type = Mock(return_value=[])
            widget._packaging_core.package = Mock()

            with patch("lightspeed.trex.packaging.widget.setup_ui._TrexMessageDialog") as message_dialog_mock:
                # Act
                widget._on_package_pressed()

            # Assert
            widget._packaging_core.package.assert_not_called()
            message_dialog_mock.assert_called_once_with(
                "The current project does not contain a valid mod layer and cannot be packaged.",
                "Invalid Project",
                disable_cancel_button=True,
            )

        finally:
            widget.destroy()
            window.destroy()

    async def test_package_pressed_with_pending_edits_should_save_before_packaging(self):
        window, widget = await _create_widget("test_packaging_pending_edits_save")

        try:
            # Arrange
            widget._context = Mock()
            widget._context.has_pending_edit.return_value = False
            widget._layer_manager.get_layers_of_type = Mock(
                return_value=[Mock(realPath="C:/projects/MainProject/mod.usda")]
            )

            with tempfile.TemporaryDirectory() as tmp_dir:
                output_directory = Path(tmp_dir) / "package"
                widget._package_output_widget._output_field.model.set_value(output_directory.as_posix())

                package_started = asyncio.Event()

                def package_side_effect(_):
                    package_started.set()

                widget._packaging_core.package = Mock(side_effect=package_side_effect)
                layers_state_mock = Mock()
                layers_state_mock.get_dirty_layer_identifiers.return_value = ["C:/projects/MainProject/mod.usda"]
                layers_mock = Mock()
                layers_mock.get_layers_state.return_value = layers_state_mock

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
                    patch("lightspeed.trex.packaging.widget.setup_ui.omni.kit.window.file.save") as save_mock,
                    patch(
                        "lightspeed.trex.packaging.widget.setup_ui._layers.get_layers", return_value=layers_mock
                    ) as get_layers_mock,
                    patch("lightspeed.trex.packaging.widget.setup_ui._TrexMessageDialog") as message_dialog_mock,
                ):
                    # Act
                    widget._on_package_pressed()
                    for _ in range(30):
                        if save_mock.called:
                            break
                        await omni.kit.app.get_app().next_update_async()

                    # Assert
                    save_mock.assert_called_once()
                    get_layers_mock.assert_called_once_with(widget._context)
                    message_dialog_mock.assert_not_called()
                    widget._packaging_core.package.assert_not_called()

                    save_done = save_mock.call_args.kwargs["on_save_done"]
                    save_done(True, "")
                    await asyncio.wait_for(package_started.wait(), timeout=1)

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
                        "rtxio_pack": False,
                        "rtxio_delete_dds_after_pack": False,
                        "rtxio_split_size_mb": None,
                    }
                )
        finally:
            widget.destroy()
            window.destroy()

    async def test_package_pressed_with_cancelled_save_should_not_package(self):
        window, widget = await _create_widget("test_packaging_cancelled_save")

        try:
            # Arrange
            widget._context = Mock()
            widget._context.has_pending_edit.return_value = True
            widget._layer_manager.get_layers_of_type = Mock(
                return_value=[Mock(realPath="C:/projects/MainProject/mod.usda")]
            )
            widget._packaging_core.package = Mock()
            widget._on_packaging_completed = AsyncMock()

            with tempfile.TemporaryDirectory() as tmp_dir:
                output_directory = Path(tmp_dir) / "package"
                widget._package_output_widget._output_field.model.set_value(output_directory.as_posix())

                with patch("lightspeed.trex.packaging.widget.setup_ui.omni.kit.window.file.save") as save_mock:
                    # Act
                    widget._on_package_pressed()
                    for _ in range(30):
                        if save_mock.called:
                            break
                        await omni.kit.app.get_app().next_update_async()

                    save_done = save_mock.call_args.kwargs["on_save_done"]
                    save_done(False, "cancelled")
                    for _ in range(5):
                        if widget._on_packaging_completed.await_count:
                            break
                        await omni.kit.app.get_app().next_update_async()

                # Assert
                save_mock.assert_called_once()
                widget._packaging_core.package.assert_not_called()
                widget._on_packaging_completed.assert_awaited_once_with(["cancelled"], [], False)
        finally:
            widget.destroy()
            window.destroy()

    async def test_retry_packaging_flatten_with_ignored_errors_should_stop_and_show_message(self):
        window, widget = await _create_widget("test_retry_flatten_ignored_errors")

        try:
            # Arrange
            ignored_errors = [("C:/projects/MainProject/mod.usda", "/Root/BadRef", "C:/missing/ref.usda")]
            widget._on_package_pressed = Mock()

            with (
                patch.object(PackagingPane, "_get_selected_packaging_mode", return_value=ModPackagingMode.FLATTEN),
                patch("lightspeed.trex.packaging.widget.setup_ui._TrexMessageDialog") as message_dialog_mock,
            ):
                # Act
                await widget._retry_packaging(ignored_errors)

            # Assert
            widget._on_package_pressed.assert_not_called()
            message_dialog_mock.assert_called_once_with(
                "Ignoring unresolved reference errors will stop the packaging process. This project cannot be flattened "
                "while references are missing.",
                "Packaging Cannot Continue",
                disable_cancel_button=True,
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

                main_thread_id = threading.get_ident()
                delete_thread_id = None

                def delete_side_effect(_output_url):
                    nonlocal delete_thread_id
                    callback_order.append("delete")
                    delete_thread_id = threading.get_ident()
                    self.assertTrue(package_file.exists())
                    return omni.client.Result.OK

                def package_side_effect(_):
                    callback_order.append("package")
                    package_started.set()

                def show_progress_side_effect(current, total, status, cancel_enabled):
                    callback_order.append("progress")
                    self.assertEqual(0, current)
                    self.assertEqual(INDETERMINATE_PROGRESS_TOTAL, total)
                    self.assertEqual("Deleting existing package...", status)
                    self.assertFalse(cancel_enabled)

                widget._packaging_core.package = Mock(side_effect=package_side_effect)
                widget._show_packaging_progress = Mock(side_effect=show_progress_side_effect)

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
                        "lightspeed.trex.packaging.widget.setup_ui._OmniUrl.delete",
                        autospec=True,
                        side_effect=delete_side_effect,
                    ) as delete_mock,
                    patch("lightspeed.trex.packaging.widget.setup_ui._TrexMessageDialog") as message_dialog_mock,
                ):
                    # Act
                    widget._on_package_pressed()
                    delete_handler = message_dialog_mock.call_args.kwargs["ok_handler"]
                    delete_handler()
                    await asyncio.wait_for(package_started.wait(), timeout=1)

                # Assert
                delete_mock.assert_called_once()
                self.assertNotEqual(main_thread_id, delete_thread_id)
                widget._show_packaging_progress.assert_called_once_with(
                    0, INDETERMINATE_PROGRESS_TOTAL, "Deleting existing package...", False
                )
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
                        "rtxio_pack": False,
                        "rtxio_delete_dds_after_pack": False,
                        "rtxio_split_size_mb": None,
                    }
                )
                self.assertEqual(["progress", "delete", "package"], callback_order)
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


class TestPackagingPaneProgress(AsyncTestCase):
    async def test_on_packaging_progress_with_measurable_stage_should_show_count_and_fraction(self):
        # Arrange
        widget = PackagingPane.__new__(PackagingPane)
        popup_mock = Mock()
        popup_mock.status_text = ""
        popup_mock.is_visible.return_value = True
        widget._progress_popup = popup_mock
        widget._packaging_cancel_requested = False
        widget._cancel_packaging = Mock()
        widget._packaging_core = Mock(can_cancel=True)

        # Act
        widget._on_packaging_progress(5, 10, "Collecting assets...")

        # Assert
        popup_mock.set_status_text.assert_called_once_with("Collecting assets...\n5 / 10")
        popup_mock.set_progress.assert_called_once_with(0.5)

    async def test_on_packaging_progress_with_indeterminate_stage_should_show_half_progress(self):
        # Arrange
        widget = PackagingPane.__new__(PackagingPane)
        popup_mock = Mock()
        popup_mock.status_text = ""
        popup_mock.is_visible.return_value = True
        widget._progress_popup = popup_mock
        widget._packaging_cancel_requested = False
        widget._cancel_packaging = Mock()
        widget._packaging_core = Mock(can_cancel=True)

        # Act
        widget._on_packaging_progress(0, INDETERMINATE_PROGRESS_TOTAL, "Indeterminate stage...")

        # Assert
        popup_mock.set_status_text.assert_called_once_with("Indeterminate stage...")
        popup_mock.set_progress.assert_called_once_with(0.5)
