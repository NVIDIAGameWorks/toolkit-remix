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

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import carb.settings
import omni.appwindow
import omni.kit.app
import omni.kit.renderer_capture
import omni.usd
import omni.ui as ui
from carb.input import KeyboardInput
from lightspeed.trex.packaging.core.enum import ModPackagingMode
from lightspeed.trex.packaging.widget import setup_ui as _setup_ui
from lightspeed.trex.packaging.widget.setup_ui import PackagingPane
from lightspeed.trex.packaging.window.tree.item import PackagingActions
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows
from omni.flux.utils.common import path_utils as _path_utils
from omni.flux.utils.widget.file_pickers import destroy_file_picker as _destroy_file_picker
from pxr import Sdf

_FILE_PICKER_LAST_SELECTED_DIRECTORY_SETTING = "/persistent/ext/omni.flux.utils.widget/last_selected_directory"


async def _create_widget(window_name: str, width: int = 600, height: int = 800) -> tuple[ui.Window, PackagingPane]:
    window = ui.Window(window_name, width=width, height=height)
    with window.frame:
        widget = PackagingPane("")
    await omni.kit.app.get_app().next_update_async()
    return window, widget


async def _wait_for_widget(selector: str, max_frames: int = 600):
    widget = None
    for _ in range(max_frames):
        widget = _find_visible_widget(selector)
        if widget is not None:
            return widget
        await omni.kit.app.get_app().next_update_async()
    return widget


def _find_visible_widget(selector: str):
    for widget in ui_test.find_all(selector) or []:
        if _is_visible_widget(widget):
            return widget

    widget = ui_test.find(selector)
    if widget is not None and _is_visible_widget(widget):
        return widget
    return None


def _is_visible_widget(widget_ref) -> bool:
    widget = getattr(widget_ref, "widget", None)
    if widget is not None and not getattr(widget, "visible", True):
        return False

    window = getattr(widget_ref, "window", None)
    return window is None or getattr(window, "visible", True)


def _get_extension_path(extension_name: str) -> Path:
    ext_manager = omni.kit.app.get_app().get_extension_manager()
    ext_path = ext_manager.get_extension_path_by_module(extension_name)
    if not ext_path:
        ext_id = ext_manager.get_enabled_extension_id(extension_name)
        ext_path = ext_manager.get_extension_path(ext_id)
    return Path(ext_path)


class TestPackagingPaneProgressE2E(AsyncTestCase):
    async def setUp(self):
        await arrange_windows()

    async def test_cancelled_packaging_should_show_disabled_cleanup_progress(self):
        window, widget = await _create_widget("test_cancelled_packaging_late_progress")

        try:
            # Show the real progress popup from a packaging progress event.
            widget._packaging_core = Mock()

            widget._on_packaging_progress(0, 1, "Filtering the selected layers...")
            await omni.kit.app.get_app().next_update_async()

            popup = widget._progress_popup
            self.assertIsNotNone(popup)
            self.assertTrue(popup.is_visible())

            # Click Cancel and verify the popup immediately shows the disabled cancellation state.
            popup._on_cancel_button_fn()
            await omni.kit.app.get_app().next_update_async()

            widget._packaging_core.cancel.assert_called_once()
            self.assertTrue(widget._packaging_cancel_requested)
            self.assertTrue(popup.is_visible())
            self.assertEqual("Cancelling packaging...", popup.status_text)
            self.assertEqual(0.5, popup.progress)

            # Click Cancel again to confirm the disabled button no longer forwards cancellation.
            popup._on_cancel_button_fn()
            await omni.kit.app.get_app().next_update_async()

            widget._packaging_core.cancel.assert_called_once()
            self.assertTrue(popup.is_visible())

            # Send the normal cleanup progress event and verify the same popup stays visible with Cancel disabled.
            widget._on_packaging_progress(1, 1, "Cleaning up temporary layers...")
            await omni.kit.app.get_app().next_update_async()

            self.assertTrue(popup.is_visible())
            self.assertEqual("Cleaning up temporary layers...\n1 / 1", popup.status_text)
            self.assertEqual(1, popup.progress)

            # Click Cancel during cleanup to make sure cleanup cannot be interrupted through the dialog.
            popup._on_cancel_button_fn()
            await omni.kit.app.get_app().next_update_async()

            widget._packaging_core.cancel.assert_called_once()
            self.assertTrue(popup.is_visible())
        finally:
            widget.destroy()
            window.destroy()


class TestPackagingPaneReferenceRepairE2E(AsyncTestCase):
    _TEST_WINDOW_TITLE = "test_packaging_reference_repair"
    _ERROR_WINDOW_TITLE = "Mod Packaging Errors"
    _RETRY_DIALOG_TITLE = "Retry Packaging the Mod"
    _SAVE_FILES_DIALOG_TITLE = "Select Files to Save##file.py"
    _SUCCESS_DIALOG_TITLE = "Mod Packaging Successful"
    _MISSING_REMOVE_ASSET = "missing_remove.usda"
    _MISSING_REPLACE_ASSET = "missing_replace.usda"

    async def setUp(self):
        await self._destroy_reference_repair_windows()
        self._settings = carb.settings.get_settings()
        self._settings.destroy_item(_setup_ui._SETTINGS_PACKAGING_MODE)
        self._settings.destroy_item(_setup_ui._SETTINGS_OUTPUT_FORMAT)
        self._settings.destroy_item(_FILE_PICKER_LAST_SELECTED_DIRECTORY_SETTING)
        temp_root = Path.cwd() / "_testoutput" / "packaging_widget_reference_repair"
        temp_root.mkdir(parents=True, exist_ok=True)
        self._temp_dir = tempfile.TemporaryDirectory(dir=str(temp_root))
        await arrange_windows()

    async def tearDown(self):
        default_context = omni.usd.get_context()
        if default_context and default_context.get_stage():
            await default_context.close_stage_async()

        packaging_context = omni.usd.get_context(PackagingPane._MOD_PACKAGING_CONTEXT)
        if packaging_context and packaging_context.get_stage():
            await packaging_context.close_stage_async()

        self._settings.destroy_item(_setup_ui._SETTINGS_PACKAGING_MODE)
        self._settings.destroy_item(_setup_ui._SETTINGS_OUTPUT_FORMAT)
        self._settings.destroy_item(_FILE_PICKER_LAST_SELECTED_DIRECTORY_SETTING)
        self._temp_dir.cleanup()
        self._temp_dir = None
        await self._destroy_reference_repair_windows()

    async def test_flatten_package_cancel_from_error_window_should_close_without_packaging(self):
        # Copy the real packaging project fixture and author two unresolved USD references in its source sublayer.
        project_root, root_path, _, _ = self._prepare_project_with_broken_refs()
        output_file = project_root / "package" / "mod.usd"

        # Open the real project stage and create a tall Packaging pane so the mode dropdown and Package button fit.
        await self._open_project(root_path)
        window, widget = await _create_widget(f"{self._TEST_WINDOW_TITLE}_cancel", width=900, height=1600)

        try:
            widget.show(True)
            # Click the real Package button in flatten mode and wait for the invalid-reference UI.
            await self._package_until_error_window(widget, window)

            # Click the real Cancel button and verify packaging does not produce an output.
            await self._click_button(self._ERROR_WINDOW_TITLE, "Cancel")
            await self._wait_for_packaging_error_window_hidden(widget)
            self.assertFalse(output_file.exists())
        finally:
            widget.destroy()
            window.destroy()
            await self._destroy_reference_repair_windows()

    async def test_flatten_package_ignore_all_retry_should_stop_and_retry_cancel_should_return_to_errors(self):
        # Copy the real packaging project fixture and author two unresolved USD references in its source sublayer.
        project_root, root_path, _, _ = self._prepare_project_with_broken_refs()
        output_file = project_root / "package" / "mod.usd"

        # Open the real project stage and create a tall Packaging pane so the mode dropdown and Package button fit.
        await self._open_project(root_path)
        window, widget = await _create_widget(f"{self._TEST_WINDOW_TITLE}_ignore_all", width=900, height=1600)

        try:
            widget.show(True)
            # Click the real Package button in flatten mode and wait for the invalid-reference UI.
            await self._package_until_error_window(widget, window)

            # Start a real retry with pending removals, cancel the confirmation, and verify the error window returns.
            await self._click_button(self._ERROR_WINDOW_TITLE, "Remove All")
            await self._click_button(self._ERROR_WINDOW_TITLE, "Retry Packaging")
            await self._click_button(self._RETRY_DIALOG_TITLE, "Cancel")
            await self._wait_for_packaging_error_window_visible(widget)
            await self._wait_for_error_window_actions(
                {
                    self._MISSING_REMOVE_ASSET: PackagingActions.REMOVE_REFERENCE,
                    self._MISSING_REPLACE_ASSET: PackagingActions.REMOVE_REFERENCE,
                },
                widget,
            )

            # Retry with all rows ignored and verify flatten packaging blocks instead of producing a package.
            await self._click_button(self._ERROR_WINDOW_TITLE, "Ignore All")
            await self._wait_for_error_window_actions(
                {
                    self._MISSING_REMOVE_ASSET: PackagingActions.IGNORE,
                    self._MISSING_REPLACE_ASSET: PackagingActions.IGNORE,
                },
                widget,
            )
            await self._click_button(self._ERROR_WINDOW_TITLE, "Retry Packaging")
            await self._click_button("Packaging Cannot Continue", "Okay")
            self.assertFalse(output_file.exists())
        finally:
            widget.destroy()
            window.destroy()
            await self._destroy_reference_repair_windows()

    async def test_flatten_package_remove_all_broken_refs_from_error_window_should_retry_and_package(self):
        # Copy the real packaging project fixture and author two unresolved USD references in its source sublayer.
        project_root, root_path, sublayer_path, _ = self._prepare_project_with_broken_refs()
        output_file = project_root / "package" / "mod.usd"

        # Open the real project stage and create a tall Packaging pane so the mode dropdown and Package button fit.
        await self._open_project(root_path)
        window, widget = await _create_widget(f"{self._TEST_WINDOW_TITLE}_remove_all", width=900, height=1600)

        try:
            widget.show(True)
            # Click the real Package button in flatten mode and wait for the invalid-reference UI.
            await self._package_until_error_window(widget, window)

            # Drive the real error window controls: remove every broken reference, retry, and save the edited stage.
            await self._click_button(self._ERROR_WINDOW_TITLE, "Remove All")
            await self._click_button(self._ERROR_WINDOW_TITLE, "Retry Packaging")
            await self._click_button(self._RETRY_DIALOG_TITLE, "Save and Retry")
            await self._save_selected_files_if_present()

            # The retry must produce a flattened package and request to open Explorer without launching it in CI.
            with patch.object(_path_utils.subprocess, "call") as open_directory_mock:
                await self._assert_package_succeeded(widget, output_file)
            self._assert_output_directory_opened(open_directory_mock, output_file.parent)
            self._assert_flattened_output_matches_repaired_refs(output_file, expect_replacement_asset=False)

            # The remove-all repair must persist both reference removals in the source sublayer.
            sublayer = Sdf.Layer.FindOrOpen(str(sublayer_path))
            self.assertIsNotNone(sublayer)
            self._assert_reference_count(sublayer, self._missing_remove_prim_path(), 0)
            self._assert_reference_count(sublayer, self._missing_replace_prim_path(), 0)
        finally:
            widget.destroy()
            window.destroy()
            await self._destroy_reference_repair_windows()

    async def test_flatten_package_scan_directory_replaces_matching_refs_from_error_window_should_retry_and_package(
        self,
    ):
        # Copy the real packaging project fixture and add one broken ref to remove plus one broken ref to replace.
        project_root, root_path, sublayer_path, replacement_path = self._prepare_project_with_broken_refs()
        output_file = project_root / "package" / "mod.usd"

        # Open the real project stage and create a tall Packaging pane so the mode dropdown and Package button fit.
        await self._open_project(root_path)
        window, widget = await _create_widget(f"{self._TEST_WINDOW_TITLE}_scan_directory", width=900, height=1600)

        try:
            widget.show(True)
            # Click the real Package button in flatten mode and wait for the invalid-reference UI.
            await self._package_until_error_window(widget, window)

            # Verify the bulk Ignore All control, then mark all rows for removal before scanning for replacements.
            await self._click_button(self._ERROR_WINDOW_TITLE, "Remove All")
            await self._click_button(self._ERROR_WINDOW_TITLE, "Ignore All")
            await self._wait_for_error_window_actions(
                {
                    self._MISSING_REMOVE_ASSET: PackagingActions.IGNORE,
                    self._MISSING_REPLACE_ASSET: PackagingActions.IGNORE,
                },
                widget,
            )
            await self._click_button(self._ERROR_WINDOW_TITLE, "Remove All")

            # Use the real Scan Directory picker to resolve the matching file.
            # Start the real directory picker in the fixture folder so the test does not burn time walking the tree.
            self._settings.set(_FILE_PICKER_LAST_SELECTED_DIRECTORY_SETTING, str(replacement_path.parent.resolve()))
            await self._click_button(self._ERROR_WINDOW_TITLE, "Scan Directory")
            await self._select_scan_directory(replacement_path.parent)
            await self._wait_for_error_window_actions(
                {
                    self._MISSING_REMOVE_ASSET: PackagingActions.REMOVE_REFERENCE,
                    self._MISSING_REPLACE_ASSET: PackagingActions.REPLACE_ASSET,
                },
                widget,
            )

            # Retry through the real confirmation dialog and save-selection dialog so packaging resumes from disk.
            await self._click_button(self._ERROR_WINDOW_TITLE, "Retry Packaging")
            await self._click_button(self._RETRY_DIALOG_TITLE, "Save and Retry")
            await self._save_selected_files_if_present()

            # The retry must produce a flattened package and request to open Explorer without launching it in CI.
            with patch.object(_path_utils.subprocess, "call") as open_directory_mock:
                await self._assert_package_succeeded(widget, output_file)
            self._assert_output_directory_opened(open_directory_mock, output_file.parent)
            self._assert_flattened_output_matches_repaired_refs(output_file, expect_replacement_asset=True)

            # The scan-directory repair must persist one removal and one replacement in the source sublayer.
            sublayer = Sdf.Layer.FindOrOpen(str(sublayer_path))
            self.assertIsNotNone(sublayer)
            self._assert_reference_count(sublayer, self._missing_remove_prim_path(), 0)
            refs = self._get_reference_assets(sublayer, self._missing_replace_prim_path())
            resolved_refs = [Path(Sdf.ComputeAssetPathRelativeToLayer(sublayer, ref)).as_posix() for ref in refs]
            self.assertEqual([replacement_path.as_posix()], resolved_refs)
        finally:
            widget.destroy()
            window.destroy()
            await self._destroy_reference_repair_windows()

    async def test_flatten_package_mixed_remove_and_replace_refs_from_error_window_should_retry_and_package(self):
        # Copy the real packaging project fixture and add one broken ref to remove plus one broken ref to replace.
        project_root, root_path, sublayer_path, replacement_path = self._prepare_project_with_broken_refs()
        output_file = project_root / "package" / "mod.usd"

        # Open the real project stage and create a tall Packaging pane so the mode dropdown and Package button fit.
        await self._open_project(root_path)
        window, widget = await _create_widget(f"{self._TEST_WINDOW_TITLE}_mixed", width=900, height=1600)

        try:
            widget.show(True)
            # Click the real Package button in flatten mode and wait for the invalid-reference UI.
            await self._package_until_error_window(widget, window)

            # Use the row action ComboBox Ignore option, then switch the same row back to Remove Reference.
            await self._select_row_action(self._MISSING_REMOVE_ASSET, PackagingActions.REMOVE_REFERENCE)
            await self._select_row_action(self._MISSING_REMOVE_ASSET, PackagingActions.IGNORE)
            await self._wait_for_error_window_actions(
                {
                    self._MISSING_REMOVE_ASSET: PackagingActions.IGNORE,
                    self._MISSING_REPLACE_ASSET: PackagingActions.IGNORE,
                },
                widget,
            )
            await self._select_row_action(self._MISSING_REMOVE_ASSET, PackagingActions.REMOVE_REFERENCE)

            # Cancel the replacement file picker once, then select Replace Asset again and choose a real USD asset.
            self._settings.set(_FILE_PICKER_LAST_SELECTED_DIRECTORY_SETTING, str(replacement_path.parent.resolve()))
            await self._select_row_action(self._MISSING_REPLACE_ASSET, PackagingActions.REPLACE_ASSET)
            await self._cancel_replacement_asset(self._MISSING_REPLACE_ASSET)
            await self._wait_for_error_window_actions(
                {
                    self._MISSING_REMOVE_ASSET: PackagingActions.REMOVE_REFERENCE,
                    self._MISSING_REPLACE_ASSET: PackagingActions.IGNORE,
                },
                widget,
            )
            self._settings.set(_FILE_PICKER_LAST_SELECTED_DIRECTORY_SETTING, str(replacement_path.parent.resolve()))
            await self._select_row_action(self._MISSING_REPLACE_ASSET, PackagingActions.REPLACE_ASSET)
            await self._select_replacement_asset(self._MISSING_REPLACE_ASSET, replacement_path)
            await self._wait_for_error_window_actions(
                {
                    self._MISSING_REMOVE_ASSET: PackagingActions.REMOVE_REFERENCE,
                    self._MISSING_REPLACE_ASSET: PackagingActions.REPLACE_ASSET,
                },
                widget,
            )
            # Retry through the real confirmation dialog and save-selection dialog so packaging resumes from disk.
            await self._click_button(self._ERROR_WINDOW_TITLE, "Retry Packaging")
            await self._click_button(self._RETRY_DIALOG_TITLE, "Save and Retry")
            await self._save_selected_files_if_present()

            # The retry must produce a flattened package and request to open Explorer without launching it in CI.
            with patch.object(_path_utils.subprocess, "call") as open_directory_mock:
                await self._assert_package_succeeded(widget, output_file)
            self._assert_output_directory_opened(open_directory_mock, output_file.parent)
            self._assert_flattened_output_matches_repaired_refs(output_file, expect_replacement_asset=True)

            # The mixed remove/replace repair must persist in the source sublayer.
            sublayer = Sdf.Layer.FindOrOpen(str(sublayer_path))
            self.assertIsNotNone(sublayer)
            self._assert_reference_count(sublayer, self._missing_remove_prim_path(), 0)
            refs = self._get_reference_assets(sublayer, self._missing_replace_prim_path())
            resolved_refs = [Path(Sdf.ComputeAssetPathRelativeToLayer(sublayer, ref)).as_posix() for ref in refs]
            self.assertEqual([replacement_path.as_posix()], resolved_refs)
        finally:
            widget.destroy()
            window.destroy()
            await self._destroy_reference_repair_windows()

    def _prepare_project_with_broken_refs(self) -> tuple[Path, Path, Path, Path]:
        temp_projects = Path(self._temp_dir.name) / "projects"
        source_projects = _get_extension_path("lightspeed.trex.packaging.core") / "data" / "tests" / "projects"
        shutil.copytree(source_projects, temp_projects)

        project_root = temp_projects / "MainProject"
        root_path = project_root / "main_project.usda"
        sublayer_path = project_root / "sublayer.usda"
        replacement_path = self._copy_valid_replacement_asset(project_root)
        self._copy_resolved_shader_assets(project_root)

        self._author_missing_reference(sublayer_path, self._missing_remove_prim_path(), self._MISSING_REMOVE_ASSET)
        self._author_missing_reference(sublayer_path, self._missing_replace_prim_path(), self._MISSING_REPLACE_ASSET)

        return project_root, root_path, sublayer_path, replacement_path

    @staticmethod
    def _copy_valid_replacement_asset(project_root: Path) -> Path:
        app_resources = _get_extension_path("lightspeed.trex.app.resources")
        source_asset = (
            app_resources / "data" / "tests" / "usd" / "project_example" / "ingested_assets" / "output" / "good"
        )
        replacement_dir = project_root / "assets" / "ingested"
        replacement_dir.mkdir(parents=True, exist_ok=True)

        replacement_path = replacement_dir / TestPackagingPaneReferenceRepairE2E._MISSING_REPLACE_ASSET
        shutil.copyfile(source_asset / "nested_lighting.usda", replacement_path)
        shutil.copyfile(source_asset / "nested_lighting.usda.meta", replacement_path.with_suffix(".usda.meta"))
        return replacement_path

    @staticmethod
    def _copy_resolved_shader_assets(project_root: Path):
        shader_source = (
            _get_extension_path("omni.flux.utils.material_converter")
            / "data"
            / "tests"
            / "omni_core_materials"
            / "Base"
        )
        shutil.copyfile(
            shader_source / "AperturePBR_Translucent.mdl",
            project_root / "materials" / "AperturePBR_Translucent.mdl",
        )
        shutil.copyfile(
            shader_source / "AperturePBR_Opacity.mdl",
            project_root / "deps" / "captures" / "materials" / "AperturePBR_Opacity.mdl",
        )

    @staticmethod
    def _author_missing_reference(layer_path: Path, prim_path: str, asset_name: str):
        layer = Sdf.Layer.FindOrOpen(str(layer_path))
        if not layer:
            raise RuntimeError(f"Unable to open fixture layer: {layer_path}")

        prim_spec = Sdf.CreatePrimInLayer(layer, prim_path)
        prim_spec.specifier = Sdf.SpecifierDef
        prim_spec.typeName = "Xform"
        prim_spec.referenceList.Append(Sdf.Reference(f"./{asset_name}"))
        layer.Save()
        layer = None

    @staticmethod
    def _missing_remove_prim_path() -> str:
        return "/RootNode/meshes/mesh_ZB98945ABC2E27F5/ref_missing_remove"

    @staticmethod
    def _missing_replace_prim_path() -> str:
        return "/RootNode/meshes/mesh_ZB98945ABC2E27F5/ref_missing_replace"

    async def _open_project(self, root_path: Path):
        context = omni.usd.get_context()
        success, _ = await context.open_stage_async(str(root_path))
        self.assertTrue(success)
        stage = context.get_stage()
        self.assertIsNotNone(stage)

    async def _package_until_error_window(self, widget: PackagingPane, window: ui.Window):
        self.assertEqual(ModPackagingMode.FLATTEN, widget._get_selected_packaging_mode())

        package_button = await _wait_for_widget(f"{window.title}//Frame/**/Button[*].text=='Package'")
        self.assertIsNotNone(package_button)
        for _ in range(300):
            if package_button.widget.enabled:
                break
            await omni.kit.app.get_app().next_update_async()
        self.assertTrue(package_button.widget.enabled)

        await package_button.click()
        await self._click_pre_package_prompt_if_present()
        await self._wait_for_packaging_error_window(widget)

        self._assert_error_window_contains_assets(widget, {self._MISSING_REMOVE_ASSET, self._MISSING_REPLACE_ASSET})
        await self._wait_for_error_window_actions(
            {
                self._MISSING_REMOVE_ASSET: PackagingActions.IGNORE,
                self._MISSING_REPLACE_ASSET: PackagingActions.IGNORE,
            },
            widget,
        )

    async def _wait_for_packaging_error_window(self, widget: PackagingPane):
        for _ in range(3600):
            if widget._packaging_window is not None:
                return
            await omni.kit.app.get_app().next_update_async()
        package_task = widget._packaging_core._package_task
        task_state = "none" if package_task is None else f"done={package_task.done()}"
        self.fail(
            "Timed out waiting for the real packaging error window "
            f"(package task: {task_state}, visible windows: {self._visible_window_titles()}, "
            f"screenshot: {await self._capture_debug_screenshot('packaging_error_window_timeout')})"
        )

    async def _wait_for_packaging_error_window_hidden(self, widget: PackagingPane):
        for _ in range(300):
            packaging_window = widget._packaging_window
            window = None if packaging_window is None else packaging_window._window
            if window is None or not window.visible:
                return
            await omni.kit.app.get_app().next_update_async()
        self.fail(
            "Timed out waiting for the real packaging error window to close "
            f"(visible windows: {self._visible_window_titles()}, "
            f"screenshot: {await self._capture_debug_screenshot('packaging_error_window_close_timeout')})"
        )

    async def _wait_for_packaging_error_window_visible(self, widget: PackagingPane):
        for _ in range(300):
            packaging_window = widget._packaging_window
            window = None if packaging_window is None else packaging_window._window
            if window is not None and window.visible:
                return
            await omni.kit.app.get_app().next_update_async()
        self.fail(
            "Timed out waiting for the real packaging error window to become visible "
            f"(visible windows: {self._visible_window_titles()}, "
            f"screenshot: {await self._capture_debug_screenshot('packaging_error_window_visible_timeout')})"
        )

    @staticmethod
    def _assert_error_window_contains_assets(widget: PackagingPane, asset_names: set[str]):
        items = widget._packaging_window._model.get_item_children(None)
        item_names = {Path(item.asset_path).name for item in items}
        missing_names = asset_names - item_names
        if missing_names:
            raise AssertionError(f"Missing invalid reference rows: {sorted(missing_names)}")

    @staticmethod
    def _assert_error_window_has_actions(expected_actions: dict[str, PackagingActions], widget: PackagingPane):
        items = widget._packaging_window._model.get_item_children(None)
        actual_actions = {Path(item.asset_path).name: item.action for item in items}
        for asset_name, expected_action in expected_actions.items():
            if actual_actions.get(asset_name) != expected_action:
                item_details = [
                    {
                        "asset": Path(item.asset_path).name,
                        "action": item.action.value,
                        "fixed_asset_path": item.fixed_asset_path,
                        "layer_identifier": item.layer_identifier,
                    }
                    for item in items
                ]
                raise AssertionError(
                    f"Expected {asset_name} action {expected_action}, got {actual_actions.get(asset_name)}. "
                    f"Rows: {item_details}"
                )

    async def _wait_for_error_window_actions(
        self, expected_actions: dict[str, PackagingActions], widget: PackagingPane
    ):
        last_error = None
        for _ in range(300):
            try:
                self._assert_error_window_has_actions(expected_actions, widget)
                return
            except AssertionError as exc:
                last_error = exc
            await omni.kit.app.get_app().next_update_async()

        self.fail(
            f"Timed out waiting for packaging repair actions to update. Last state: {last_error} "
            f"(visible windows: {self._visible_window_titles()}, "
            f"screenshot: {await self._capture_debug_screenshot('repair_action_update_timeout')})"
        )

    async def _select_row_action(self, asset_name: str, action: PackagingActions):
        action_combo = await _wait_for_widget(
            f"{self._ERROR_WINDOW_TITLE}//Frame/**/ComboBox[*].identifier=='{self._action_combo_identifier(asset_name)}'"
        )
        if action_combo is None:
            self.fail(
                f"Unable to find action ComboBox for {asset_name} "
                f"(visible windows: {self._visible_window_titles()}, "
                f"screenshot: {await self._capture_debug_screenshot(f'action_combo_missing_{Path(asset_name).stem}')})"
            )

        # Select the row action through the real ComboBox model; Kit ui_test cannot click popup items reliably.
        action_combo.widget.model.get_item_value_model().set_value(list(PackagingActions).index(action))
        await omni.kit.app.get_app().next_update_async()

    @staticmethod
    def _action_combo_identifier(asset_name: str) -> str:
        return f"packaging_action_combo_{Path(asset_name).stem}"

    async def _select_replacement_asset(self, missing_asset_name: str, replacement_path: Path):
        self.assertTrue(replacement_path.exists())
        file_picker_title = f"Select a replacement asset for: ./{missing_asset_name}"

        select_button = await _wait_for_widget(f"{file_picker_title}//Frame/**/Button[*].text=='Select'")
        directory_field = await _wait_for_widget(
            f"{file_picker_title}//Frame/**/StringField[*].identifier=='filepicker_directory_path'"
        )
        file_name_field = await _wait_for_widget(
            f"{file_picker_title}//Frame/**/StringField[*].style_type_name_override=='Field'"
        )
        if select_button is None or directory_field is None or file_name_field is None:
            self.fail(
                f"Unable to find replacement file picker controls for {missing_asset_name} "
                f"(visible windows: {self._visible_window_titles()}, "
                f"screenshot: {await self._capture_debug_screenshot(f'replacement_picker_missing_{Path(missing_asset_name).stem}')})"
            )

        # Navigate through the real file picker fields so headless CI does not depend on toolbar focus state.
        expected_directory = replacement_path.parent.resolve().as_posix()
        for attempt in range(3):
            await self._select_file_picker_directory(directory_field, replacement_path.parent)
            await ui_test.human_delay(100 * (attempt + 1))

            await file_name_field.input(str(replacement_path.name), end_key=KeyboardInput.DOWN)
            await ui_test.human_delay(100 * (attempt + 1))

            for _ in range(300):
                if (
                    select_button.widget.enabled
                    and file_name_field.model.get_value_as_string() == replacement_path.name
                ):
                    break
                await omni.kit.app.get_app().next_update_async()
            self.assertTrue(select_button.widget.enabled)
            self.assertEqual(replacement_path.name, file_name_field.model.get_value_as_string())
            self.assertEqual(expected_directory, self._normalize_file_picker_path(directory_field))

            await select_button.click()
            for _ in range(300):
                if self._is_window_visible("Invalid File"):
                    await self._click_button("Invalid File", "Okay")
                    await ui_test.human_delay(250)
                    break
                if not self._is_window_visible(file_picker_title):
                    return
                await omni.kit.app.get_app().next_update_async()
        self.fail(
            f"Timed out waiting for replacement file picker to close "
            f"(visible windows: {self._visible_window_titles()}, "
            f"screenshot: {await self._capture_debug_screenshot(f'replacement_picker_timeout_{Path(missing_asset_name).stem}')})"
        )

    async def _cancel_replacement_asset(self, missing_asset_name: str):
        file_picker_title = f"Select a replacement asset for: ./{missing_asset_name}"
        await self._click_button(file_picker_title, "Cancel")
        for _ in range(300):
            packaging_window = _find_visible_widget(self._ERROR_WINDOW_TITLE)
            if not self._is_window_visible(file_picker_title) and packaging_window is not None:
                return
            await omni.kit.app.get_app().next_update_async()
        self.fail(
            f"Timed out waiting for replacement file picker cancel to return to the error window "
            f"(visible windows: {self._visible_window_titles()}, "
            f"screenshot: {await self._capture_debug_screenshot(f'replacement_picker_cancel_{Path(missing_asset_name).stem}')})"
        )

    async def _select_scan_directory(self, directory: Path):
        directory_field = await _wait_for_widget(
            "Select a directory to scan//Frame/**/StringField[*].identifier=='filepicker_directory_path'"
        )
        self.assertIsNotNone(directory_field)

        self.assertTrue(directory.exists())
        directory_name = str(directory.resolve())
        expected_directory = directory_name.replace("\\", "/").rstrip("/")
        await self._select_file_picker_directory(directory_field, directory)
        await ui_test.human_delay(250)
        self.assertEqual(expected_directory, self._normalize_file_picker_path(directory_field))

        select_button = await _wait_for_widget("Select a directory to scan//Frame/**/Button[*].text=='Select'")
        self.assertIsNotNone(select_button)
        await select_button.click()
        for _ in range(300):
            if not self._is_window_visible("Select a directory to scan"):
                return
            await omni.kit.app.get_app().next_update_async()
        self.fail(
            "Timed out waiting for scan-directory file picker to close "
            f"(visible windows: {self._visible_window_titles()}, "
            f"screenshot: {await self._capture_debug_screenshot('scan_directory_picker_timeout')})"
        )

    async def _select_file_picker_directory(self, directory_field, directory: Path):
        directory_name = str(directory.resolve())
        expected_directory = directory_name.replace("\\", "/").rstrip("/")
        if await self._wait_for_file_picker_directory(directory_field, expected_directory):
            return

        await directory_field.input(directory_name, end_key=KeyboardInput.ENTER)
        await ui_test.human_delay(250)
        if await self._wait_for_file_picker_directory(directory_field, expected_directory):
            return

        self.fail(
            f"File picker did not navigate to {expected_directory}. "
            f"Current path: {self._normalize_file_picker_path(directory_field)} "
            f"(screenshot: {await self._capture_debug_screenshot('file_picker_navigation')})"
        )

    async def _wait_for_file_picker_directory(self, directory_field, expected_directory: str) -> bool:
        for _ in range(300):
            if self._normalize_file_picker_path(directory_field) == expected_directory:
                return True
            await omni.kit.app.get_app().next_update_async()
        return False

    @staticmethod
    def _normalize_file_picker_path(directory_field) -> str:
        field = getattr(directory_field.model, "_field", None)
        field_model = getattr(field, "model", None)
        field_value = field_model.get_value_as_string() if field_model is not None else None
        return (field_value or getattr(directory_field.model, "_path", None) or "").replace("\\", "/").rstrip("/")

    @staticmethod
    def _is_window_visible(title: str) -> bool:
        return any(window.title == title and window.visible for window in ui.Workspace.get_windows())

    async def _click_button(self, window_title: str, button_text: str):
        button = await _wait_for_widget(f"{window_title}//Frame/**/Button[*].text=='{button_text}'")
        self.assertIsNotNone(button, f"Unable to find '{button_text}' button in '{window_title}'")
        await button.click()
        await omni.kit.app.get_app().next_update_async()

    async def _save_selected_files_if_present(self):
        for _ in range(300):
            save_button = _find_visible_widget(
                f"{self._SAVE_FILES_DIALOG_TITLE}//Frame/**/Button[*].text=='Save Selected'"
            )
            if save_button is not None:
                for _ in range(300):
                    if save_button.widget.enabled:
                        break
                    await omni.kit.app.get_app().next_update_async()
                self.assertTrue(save_button.widget.enabled)

                await save_button.click()
                for _ in range(300):
                    save_dialog = _find_visible_widget(self._SAVE_FILES_DIALOG_TITLE)
                    if save_dialog is None or not save_dialog.widget.visible:
                        return
                    await omni.kit.app.get_app().next_update_async()
                self.fail(
                    "Timed out waiting for the real save-selection dialog to close "
                    f"(visible windows: {self._visible_window_titles()}, "
                    f"screenshot: {await self._capture_debug_screenshot('save_files_dialog_timeout')})"
                )

            if self._packaging_task_started():
                return
            await omni.kit.app.get_app().next_update_async()

        self.fail(
            "Timed out waiting for packaging retry to enter save-selection or packaging progress "
            f"(visible windows: {self._visible_window_titles()}, "
            f"screenshot: {await self._capture_debug_screenshot('retry_save_selection_timeout')})"
        )

    async def _click_pre_package_prompt_if_present(self):
        for _ in range(120):
            if _find_visible_widget("Mod Packaging Errors") is not None:
                return

            discard_button = self._find_button_in_visible_windows("Discard")
            if discard_button is not None:
                await discard_button.click()
                await omni.kit.app.get_app().next_update_async()
                return

            delete_button = self._find_button_in_visible_windows("Delete")
            if delete_button is not None:
                await delete_button.click()
                await omni.kit.app.get_app().next_update_async()
                return

            if self._packaging_task_started():
                return
            await omni.kit.app.get_app().next_update_async()

    @staticmethod
    def _find_button_in_visible_windows(button_text: str):
        for button in ui_test.find_all(f"**/Button[*].text=='{button_text}'") or []:
            if _is_visible_widget(button):
                return button

        for window in ui.Workspace.get_windows():
            if not window.visible or window.title in {"DockSpace", "Debug##Default"}:
                continue
            button = _find_visible_widget(f"{window.title}//Frame/**/Button[*].text=='{button_text}'")
            if button is not None:
                return button
        return None

    def _packaging_task_started(self) -> bool:
        return any(window.title == "Packaging Mod" and window.visible for window in ui.Workspace.get_windows())

    @staticmethod
    def _visible_window_titles() -> list[str]:
        return [window.title for window in ui.Workspace.get_windows() if window.visible]

    async def _assert_package_succeeded(self, widget: PackagingPane, output_file: Path):
        for _ in range(1200):
            if output_file.exists():
                success_button = _find_visible_widget(f"{self._SUCCESS_DIALOG_TITLE}//Frame/**/Button[*].text=='Okay'")
                if success_button is not None:
                    await success_button.click()
                    for _ in range(300):
                        package_task = widget._packaging_core._package_task
                        success_dialog = _find_visible_widget(self._SUCCESS_DIALOG_TITLE)
                        success_closed = success_dialog is None or not success_dialog.widget.visible
                        if (package_task is None or package_task.done()) and success_closed:
                            return
                        await omni.kit.app.get_app().next_update_async()
                    self.fail(
                        "Timed out waiting for packaging cleanup and the success dialog to close "
                        f"(visible windows: {self._visible_window_titles()}, "
                        f"screenshot: {await self._capture_debug_screenshot('package_cleanup_timeout')})"
                    )
            await omni.kit.app.get_app().next_update_async()
        self.fail(
            f"Timed out waiting for packaged output file: {output_file} "
            f"(visible windows: {self._visible_window_titles()}, "
            f"screenshot: {await self._capture_debug_screenshot('package_output_timeout')})"
        )

    def _assert_output_directory_opened(self, open_directory_mock: Mock, output_directory: Path):
        open_directory_mock.assert_called_once_with(("explorer", os.path.normpath(output_directory.as_posix())))

    def _assert_flattened_output_matches_repaired_refs(self, output_file: Path, expect_replacement_asset: bool):
        self.assertEqual(".usd", output_file.suffix)

        output_layer = Sdf.Layer.FindOrOpen(str(output_file))
        self.assertIsNotNone(output_layer)
        self.assertEqual([], list(output_layer.subLayerPaths))

        output_text = output_layer.ExportToString()
        self.assertNotIn("sublayer.usda", output_text)
        self.assertNotIn("mod_capture_baker.usda", output_text)
        self.assertNotIn(self._MISSING_REMOVE_ASSET, output_text)
        self.assertNotIn(self._MISSING_REPLACE_ASSET, output_text)

        if expect_replacement_asset:
            self.assertIn('CylinderLight "TankA"', output_text)
            self.assertIn('CylinderLight "TankB"', output_text)
        else:
            self.assertNotIn('CylinderLight "TankA"', output_text)
            self.assertNotIn('CylinderLight "TankB"', output_text)

    async def _destroy_reference_repair_windows(self):
        stable_hidden_frames = 0
        for _ in range(120):
            _destroy_file_picker()
            for window in list(ui.Workspace.get_windows()):
                if self._is_reference_repair_window(window.title):
                    window.visible = False
                    destroy = getattr(window, "destroy", None)
                    if callable(destroy):
                        destroy()
                        continue

                    window_ref = ui_test.find(window.title)
                    destroy = getattr(getattr(window_ref, "widget", None), "destroy", None)
                    if callable(destroy):
                        destroy()
            await omni.kit.app.get_app().next_update_async()

            if self._visible_reference_repair_windows():
                stable_hidden_frames = 0
            else:
                stable_hidden_frames += 1
                if stable_hidden_frames == 3:
                    return

    def _visible_reference_repair_windows(self) -> list[str]:
        return [
            window.title
            for window in ui.Workspace.get_windows()
            if window.visible and self._is_reference_repair_window(window.title)
        ]

    def _is_reference_repair_window(self, title: str) -> bool:
        return (
            title
            in {
                self._ERROR_WINDOW_TITLE,
                self._RETRY_DIALOG_TITLE,
                self._SAVE_FILES_DIALOG_TITLE,
                self._SUCCESS_DIALOG_TITLE,
                "Packaging Mod",
                "Packaging Cannot Continue",
                "Invalid File",
                "Login Required",
                "Mod Packaging Error",
                "Mod Packaging Cancelled",
                "Select a directory to scan",
            }
            or title.startswith(self._TEST_WINDOW_TITLE)
            or title.startswith("Select a replacement asset for:")
        )

    async def _capture_debug_screenshot(self, label: str) -> str:
        screenshot_path = Path.cwd() / "_testoutput" / "packaging_widget_reference_repair" / f"{label}.png"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            app_window = omni.appwindow.get_default_app_window()
            renderer_capture = omni.kit.renderer_capture.acquire_renderer_capture_interface()
            renderer_capture.capture_next_frame_swapchain(str(screenshot_path), app_window)
            await omni.kit.app.get_app().next_update_async()
            renderer_capture.wait_async_capture(app_window)
        except (AttributeError, ImportError, RuntimeError) as exc:
            return f"screenshot capture failed: {exc}"
        return str(screenshot_path)

    @staticmethod
    def _get_reference_assets(layer: Sdf.Layer, prim_path: str) -> list[str]:
        prim_spec = layer.GetPrimAtPath(prim_path)
        if not prim_spec:
            return []
        return [reference.assetPath for reference in prim_spec.referenceList.GetAddedOrExplicitItems()]

    def _assert_reference_count(self, layer: Sdf.Layer, prim_path: str, expected_count: int):
        self.assertEqual(expected_count, len(self._get_reference_assets(layer, prim_path)))
