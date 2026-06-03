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
import re
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import carb.settings
import omni.appwindow
import omni.kit.app
import omni.kit.renderer_capture
import omni.ui as ui
import omni.usd
from carb.input import KeyboardInput
from lightspeed.common import constants as _constants
from lightspeed.trex.packaging.core.enum import ModPackagingMode
from lightspeed.trex.packaging.widget import setup_ui as _setup_ui
from lightspeed.trex.packaging.widget.setup_ui import PackagingPane
from lightspeed.trex.packaging.window.tree.item import PackagingActions
from omni.flux.utils.common import path_utils as _path_utils
from omni.flux.utils.tests.context_managers import get_test_data_path
from omni.flux.utils.widget.file_pickers import destroy_file_picker as _destroy_file_picker
from omni.flux.validator.factory import BASE_HASH_KEY, VALIDATION_PASSED
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows
from omni.kit.ui_test.query import WindowRef
from omni.kit.widget.prompt import PromptManager as _PromptManager
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
    widget = widget_ref.widget
    if widget is not None and not widget.visible:
        return False

    window = widget_ref.window
    return window is None or window.visible


def _get_extension_path(extension_name: str) -> Path:
    ext_manager = omni.kit.app.get_app().get_extension_manager()
    ext_path = ext_manager.get_extension_path_by_module(extension_name)
    if not ext_path:
        ext_id = ext_manager.get_enabled_extension_id(extension_name)
        ext_path = ext_manager.get_extension_path(ext_id)
    return Path(ext_path)


class TestPackagingPaneReferenceRepairE2E(AsyncTestCase):
    _TEST_WINDOW_TITLE = "test_packaging_reference_repair"
    _ERROR_WINDOW_TITLE = "Mod Packaging Errors"
    _SUCCESS_DIALOG_TITLE = "Mod Packaging Successful"
    _MISSING_REMOVE_ASSET = "missing_remove.usda"
    _MISSING_REPLACE_ASSET = "missing_replace.usda"
    _MISSING_ABSOLUTE_ASSET = "missing_absolute.usda"
    _MISSING_INSTANCE_ASSET = "missing_instance.usda"
    _BROKEN_REFS_LAYER = "broken_refs/broken_refs_all.usda"
    _TEMP_LAYER_PATTERN = re.compile(
        r"_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.usd[ac]?$",
        re.IGNORECASE,
    )

    async def setUp(self):
        await self._destroy_reference_repair_windows()
        self._open_directory_patcher = patch.object(_path_utils.subprocess, "call")
        self._open_directory_mock = self._open_directory_patcher.start()
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
        self._open_directory_patcher.stop()
        self._open_directory_patcher = None
        self._open_directory_mock = None
        await self._destroy_reference_repair_windows()

    async def test_flatten_package_cancel_from_error_window_should_close_without_packaging(self):
        # Copy the real packaging project fixture and link the committed broken-reference layer into the local stack.
        project_root, root_path, _, _ = self._copy_project_with_broken_ref_fixture()
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
            self._assert_no_temporary_layers(project_root)
            self._open_directory_mock.assert_not_called()
        finally:
            widget.destroy()
            window.destroy()
            await self._destroy_reference_repair_windows()

    async def test_flatten_package_ignore_all_retry_should_stop(self):
        # Copy the real packaging project fixture and link the committed broken-reference layer into the local stack.
        project_root, root_path, _, _ = self._copy_project_with_broken_ref_fixture()
        output_file = project_root / "package" / "mod.usd"

        # Open the real project stage and create a tall Packaging pane so the mode dropdown and Package button fit.
        await self._open_project(root_path)
        window, widget = await _create_widget(f"{self._TEST_WINDOW_TITLE}_ignore_all", width=900, height=1600)

        try:
            widget.show(True)
            # Click the real Package button in flatten mode and wait for the invalid-reference UI.
            await self._package_until_error_window(widget, window)

            # Mark every unresolved asset for removal, then switch everything back to Ignore.
            await self._click_button(self._ERROR_WINDOW_TITLE, "Remove All")
            await self._click_button(self._ERROR_WINDOW_TITLE, "Ignore All")
            await self._wait_for_error_window_actions(
                {
                    self._MISSING_REMOVE_ASSET: PackagingActions.IGNORE,
                    self._MISSING_REPLACE_ASSET: PackagingActions.IGNORE,
                },
                widget,
            )
            # Retry from the real error window and confirm the all-ignore selection stops packaging.
            await self._click_button(self._ERROR_WINDOW_TITLE, "Retry Packaging")
            await self._click_button("Packaging Cannot Continue", "Okay")
            self.assertFalse(output_file.exists())
            self._open_directory_mock.assert_not_called()
        finally:
            widget.destroy()
            window.destroy()
            await self._destroy_reference_repair_windows()

    async def test_flatten_package_remove_all_broken_refs_from_error_window_should_retry_and_package(self):
        # Copy the real packaging project fixture and link the committed broken-reference layer into the local stack.
        project_root, root_path, repair_layer_path, _ = self._copy_project_with_broken_ref_fixture()
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
            await self._wait_for_packaging_retry_started(widget)

            # The retry must produce a flattened package and request to open Explorer without launching it in CI.
            await self._assert_package_succeeded(widget, output_file)
            self._assert_output_directory_opened(output_file.parent)
            self._assert_flattened_output_matches_repaired_refs(output_file, expect_replacement_asset=False)

            # The remove-all repair must persist both reference removals in the local layer that authored them.
            repair_layer = self._open_layer_from_disk(repair_layer_path)
            self.assertIsNotNone(repair_layer)
            self._assert_reference_count(repair_layer, self._missing_remove_prim_path(), 0)
            self._assert_reference_count(repair_layer, self._missing_replace_prim_path(), 0)
        finally:
            widget.destroy()
            window.destroy()
            await self._destroy_reference_repair_windows()

    async def test_flatten_package_remove_all_absolute_and_instance_refs_should_save_and_export_clean_package(self):
        # Link the fixture layer that already contains grouped absolute refs and instance-child refs.
        project_root, root_path, repair_layer_path, _ = self._copy_project_with_broken_ref_fixture()
        output_file = project_root / "package" / "mod.usd"

        # Open the real project and use the real Packaging pane to reproduce the grouped-ref repair flow.
        await self._open_project(root_path)
        window, widget = await _create_widget(f"{self._TEST_WINDOW_TITLE}_absolute_instance", width=900, height=1600)

        try:
            widget.show(True)
            # Package until the real invalid-reference window lists every committed missing asset group.
            await self._package_until_error_window(
                widget,
                window,
                {
                    self._MISSING_REMOVE_ASSET,
                    self._MISSING_REPLACE_ASSET,
                    self._MISSING_ABSOLUTE_ASSET,
                    self._MISSING_INSTANCE_ASSET,
                },
            )

            # Drive the real bulk Remove All and Retry Packaging controls.
            await self._click_button(self._ERROR_WINDOW_TITLE, "Remove All")
            await self._click_button(self._ERROR_WINDOW_TITLE, "Retry Packaging")
            repair_statuses = await self._wait_for_packaging_retry_started(widget)

            # Verify the repair progress is one overall UI flow and that the authored layer was saved before retry.
            self._assert_repair_progress_is_overall_only(repair_statuses)
            repair_layer_text = repair_layer_path.read_text()
            self.assertNotIn(self._MISSING_REMOVE_ASSET, repair_layer_text)
            self.assertNotIn(self._MISSING_REPLACE_ASSET, repair_layer_text)
            self.assertNotIn(self._MISSING_ABSOLUTE_ASSET, repair_layer_text)
            self.assertNotIn(self._MISSING_INSTANCE_ASSET, repair_layer_text)

            # The package retry must complete and export a flattened package without the broken references.
            await self._assert_package_succeeded(widget, output_file)
            self._assert_output_directory_opened(output_file.parent)
            self._assert_flattened_output_matches_repaired_refs(output_file, expect_replacement_asset=False)

            # Reopen the saved authoring layer from disk so the assertion proves the repair was exported.
            repair_layer = self._open_layer_from_disk(repair_layer_path)
            self.assertIsNotNone(repair_layer)
            for prim_path in [
                self._missing_remove_prim_path(),
                self._missing_replace_prim_path(),
                *(self._missing_absolute_prim_path(index) for index in range(4)),
                *(self._missing_instance_prim_path(index) for index in range(4)),
            ]:
                self._assert_reference_count(repair_layer, prim_path, 0)
        finally:
            widget.destroy()
            window.destroy()
            await self._destroy_reference_repair_windows()

    async def test_flatten_package_retry_should_apply_repairs_without_live_save_dialog(self):
        # Copy the real project fixture and link the committed broken-reference layer into the local layer stack.
        project_root, root_path, _, _ = self._copy_project_with_broken_ref_fixture()
        output_file = project_root / "package" / "mod.usd"

        # Use the real Packaging pane and Retry Packaging flow; no extra confirmation dialog should be needed.
        await self._open_project(root_path)
        window, widget = await _create_widget(f"{self._TEST_WINDOW_TITLE}_no_save_dialog", width=900, height=1600)

        try:
            widget.show(True)
            # Package until the repair dialog is visible with the broken references loaded.
            await self._package_until_error_window(widget, window)

            # Remove every broken reference and retry directly; no extra save dialog should appear.
            await self._click_button(self._ERROR_WINDOW_TITLE, "Remove All")
            await self._click_button(self._ERROR_WINDOW_TITLE, "Retry Packaging")
            await self._wait_for_packaging_retry_started(widget)

            # The retry should finish packaging and open the output directory through the mocked Explorer call.
            await self._assert_package_succeeded(widget, output_file)
            self._assert_output_directory_opened(output_file.parent)
        finally:
            widget.destroy()
            window.destroy()
            await self._destroy_reference_repair_windows()

    async def test_flatten_package_replacement_picker_should_use_existing_ingestion_validation(self):
        # Copy the fixture project, link the broken refs layer, and add invalid replacement files for picker validation.
        project_root, root_path, _, _ = self._copy_project_with_broken_ref_fixture()
        invalid_dir = project_root / "assets" / "invalid_replacements"
        not_ingested_path = invalid_dir / "not_ingested.usda"
        stale_path = invalid_dir / "stale_ingestion.usda"
        self._write_replacement_validation_assets(not_ingested_path, stale_path)

        await self._open_project(root_path)
        window, widget = await _create_widget(f"{self._TEST_WINDOW_TITLE}_validation_messages", width=900, height=1600)

        try:
            widget.show(True)
            # Package until the repair dialog is visible, then choose Replace Asset for the replaceable row.
            await self._package_until_error_window(widget, window)

            # Pick a USD file without ingestion metadata and verify the user-facing validation message.
            self._settings.set(_FILE_PICKER_LAST_SELECTED_DIRECTORY_SETTING, self._file_picker_path(invalid_dir))
            await self._select_row_action(self._MISSING_REPLACE_ASSET, PackagingActions.REPLACE_ASSET)
            await self._select_invalid_replacement_asset(
                self._MISSING_REPLACE_ASSET,
                not_ingested_path,
                _constants.ASSET_NEED_INGEST_MESSAGE,
            )
            await self._dismiss_dialog(_constants.ASSET_NEED_INGEST_WINDOW_TITLE, "Cancel")

            # Pick a stale ingested USD file and verify the shared ingestion validation message.
            self._settings.set(_FILE_PICKER_LAST_SELECTED_DIRECTORY_SETTING, self._file_picker_path(invalid_dir))
            await self._select_row_action(self._MISSING_REPLACE_ASSET, PackagingActions.REPLACE_ASSET)
            await self._select_invalid_replacement_asset(
                self._MISSING_REPLACE_ASSET,
                stale_path,
                _constants.ASSET_NEED_INGEST_MESSAGE,
            )
            await self._dismiss_dialog(_constants.ASSET_NEED_INGEST_WINDOW_TITLE, "Cancel")
        finally:
            widget.destroy()
            window.destroy()
            await self._destroy_reference_repair_windows()

    async def test_flatten_package_scan_directory_replaces_matching_refs_from_error_window_should_retry_and_package(
        self,
    ):
        # Copy the real packaging project fixture and link the committed broken-reference layer into the local stack.
        project_root, root_path, repair_layer_path, replacement_path = self._copy_project_with_broken_ref_fixture()
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
            self._settings.set(
                _FILE_PICKER_LAST_SELECTED_DIRECTORY_SETTING, self._file_picker_path(replacement_path.parent)
            )
            await self._click_button(self._ERROR_WINDOW_TITLE, "Scan Directory")
            await self._select_scan_directory(replacement_path.parent)
            await self._wait_for_error_window_actions(
                {
                    self._MISSING_REMOVE_ASSET: PackagingActions.REMOVE_REFERENCE,
                    self._MISSING_REPLACE_ASSET: PackagingActions.REPLACE_ASSET,
                },
                widget,
            )

            # Retry through the real error window so packaging resumes from the saved repairs.
            await self._click_button(self._ERROR_WINDOW_TITLE, "Retry Packaging")
            await self._wait_for_packaging_retry_started(widget)

            # The retry must produce a flattened package and request to open Explorer without launching it in CI.
            await self._assert_package_succeeded(widget, output_file)
            self._assert_output_directory_opened(output_file.parent)
            self._assert_flattened_output_matches_repaired_refs(output_file, expect_replacement_asset=True)

            # The scan-directory repair must persist one removal and one replacement in the authoring layer.
            repair_layer = self._open_layer_from_disk(repair_layer_path)
            self.assertIsNotNone(repair_layer)
            self._assert_reference_count(repair_layer, self._missing_remove_prim_path(), 0)
            refs = self._get_reference_assets(repair_layer, self._missing_replace_prim_path())
            self.assertEqual([self._make_asset_path_relative_to_layer(repair_layer_path, replacement_path)], refs)
            self.assertEqual(replacement_path.resolve(), (repair_layer_path.parent / refs[0]).resolve())
        finally:
            widget.destroy()
            window.destroy()
            await self._destroy_reference_repair_windows()

    async def test_flatten_package_mixed_remove_and_replace_refs_from_error_window_should_retry_and_package(self):
        # Copy the real packaging project fixture and link the committed broken-reference layer into the local stack.
        project_root, root_path, repair_layer_path, replacement_path = self._copy_project_with_broken_ref_fixture()
        output_file = project_root / "package" / "mod.usd"

        # Open the real project stage and create a tall Packaging pane so the mode dropdown and Package button fit.
        await self._open_project(root_path)
        window, widget = await _create_widget(f"{self._TEST_WINDOW_TITLE}_mixed", width=900, height=1600)

        try:
            widget.show(True)
            # Click the real Package button in flatten mode and wait for the invalid-reference UI.
            await self._package_until_error_window(widget, window)

            # Remove the extra rows from the combined fixture, then exercise one row-level remove/replace path.
            await self._click_button(self._ERROR_WINDOW_TITLE, "Remove All")
            await self._select_row_action(self._MISSING_REMOVE_ASSET, PackagingActions.REMOVE_REFERENCE)
            await self._select_row_action(self._MISSING_REMOVE_ASSET, PackagingActions.IGNORE)
            await self._wait_for_error_window_actions(
                {
                    self._MISSING_REMOVE_ASSET: PackagingActions.IGNORE,
                    self._MISSING_REPLACE_ASSET: PackagingActions.REMOVE_REFERENCE,
                },
                widget,
            )
            await self._select_row_action(self._MISSING_REMOVE_ASSET, PackagingActions.REMOVE_REFERENCE)

            # Select Replace Asset and choose a real USD asset.
            self._settings.set(
                _FILE_PICKER_LAST_SELECTED_DIRECTORY_SETTING, self._file_picker_path(replacement_path.parent)
            )
            await self._select_row_action(self._MISSING_REPLACE_ASSET, PackagingActions.REPLACE_ASSET)
            await self._select_replacement_asset(self._MISSING_REPLACE_ASSET, replacement_path)
            await self._wait_for_error_window_actions(
                {
                    self._MISSING_REMOVE_ASSET: PackagingActions.REMOVE_REFERENCE,
                    self._MISSING_REPLACE_ASSET: PackagingActions.REPLACE_ASSET,
                },
                widget,
            )
            # Retry through the real error window so packaging resumes from the saved repairs.
            await self._click_button(self._ERROR_WINDOW_TITLE, "Retry Packaging")
            await self._wait_for_packaging_retry_started(widget)

            # The retry must produce a flattened package and request to open Explorer without launching it in CI.
            await self._assert_package_succeeded(widget, output_file)
            self._assert_output_directory_opened(output_file.parent)
            self._assert_flattened_output_matches_repaired_refs(output_file, expect_replacement_asset=True)

            # The mixed remove/replace repair must persist in the authoring layer.
            repair_layer = self._open_layer_from_disk(repair_layer_path)
            self.assertIsNotNone(repair_layer)
            self._assert_reference_count(repair_layer, self._missing_remove_prim_path(), 0)
            refs = self._get_reference_assets(repair_layer, self._missing_replace_prim_path())
            self.assertEqual([self._make_asset_path_relative_to_layer(repair_layer_path, replacement_path)], refs)
            self.assertEqual(replacement_path.resolve(), (repair_layer_path.parent / refs[0]).resolve())
        finally:
            widget.destroy()
            window.destroy()
            await self._destroy_reference_repair_windows()

    def _copy_project_with_broken_ref_fixture(self) -> tuple[Path, Path, Path, Path]:
        temp_projects = Path(self._temp_dir.name) / "projects"
        source_projects = Path(get_test_data_path("packaging/projects").path)
        shutil.copytree(source_projects, temp_projects)

        project_root = temp_projects / "MainProject"
        root_path = project_root / "main_project.usda"
        broken_refs_layer_path = project_root / self._BROKEN_REFS_LAYER
        self.assertTrue(
            broken_refs_layer_path.exists(),
            f"Broken-reference fixture layer does not exist: {broken_refs_layer_path}",
        )
        self._link_broken_refs_layer(project_root / "mod.usda", self._BROKEN_REFS_LAYER)
        replacement_path = self._copy_valid_replacement_asset(project_root)
        self._copy_resolved_shader_assets(project_root)

        return project_root, root_path, broken_refs_layer_path, replacement_path

    @staticmethod
    def _link_broken_refs_layer(mod_layer_path: Path, broken_refs_layer_name: str):
        mod_layer = Sdf.Layer.FindOrOpen(str(mod_layer_path))
        if not mod_layer:
            raise RuntimeError(f"Unable to open fixture mod layer: {mod_layer_path}")
        broken_refs_sublayer = f"./{broken_refs_layer_name}"
        if broken_refs_sublayer not in mod_layer.subLayerPaths:
            mod_layer.subLayerPaths.append(broken_refs_sublayer)
            mod_layer.Save()

    @staticmethod
    def _copy_valid_replacement_asset(project_root: Path) -> Path:
        source_asset = Path(get_test_data_path("usd/project_example/ingested_assets/output/good").path)
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
    def _open_layer_from_disk(layer_path: Path):
        return Sdf.Layer.OpenAsAnonymous(str(layer_path))

    @staticmethod
    def _make_asset_path_relative_to_layer(layer_path: Path, asset_path: Path) -> str:
        relative_path = Path(os.path.relpath(asset_path, layer_path.parent)).as_posix()
        if relative_path.startswith("../"):
            return relative_path
        return f"./{relative_path}"

    @staticmethod
    def _missing_remove_prim_path() -> str:
        return "/RootNode/meshes/mesh_ZB98945ABC2E27F5/ref_missing_remove"

    @staticmethod
    def _missing_replace_prim_path() -> str:
        return "/RootNode/meshes/mesh_ZB98945ABC2E27F5/ref_missing_replace"

    @staticmethod
    def _missing_absolute_prim_path(index: int) -> str:
        return f"/RootNode/meshes/mesh_ZB98945ABC2E27F5/absolute_missing/ref_{index}"

    @staticmethod
    def _missing_instance_prim_path(index: int) -> str:
        return f"/RootNode/meshes/mesh_ZB98945ABC2E27F5/ref_missing_instance/instances/inst_{index}"

    @staticmethod
    def _write_replacement_validation_assets(not_ingested_path: Path, stale_path: Path):
        not_ingested_path.parent.mkdir(parents=True, exist_ok=True)
        not_ingested_path.write_text("#usda 1.0\n", encoding="utf-8")
        stale_path.write_text("#usda 1.0\n", encoding="utf-8")
        _path_utils.write_metadata(str(stale_path), BASE_HASH_KEY, "stale_hash")
        _path_utils.write_metadata(str(stale_path), VALIDATION_PASSED, True)

    async def _open_project(self, root_path: Path):
        context = omni.usd.get_context()
        success, _ = await context.open_stage_async(str(root_path))
        self.assertTrue(success)
        stage = context.get_stage()
        self.assertIsNotNone(stage)

    async def _click_package(self, widget: PackagingPane, window: ui.Window):
        self.assertEqual(ModPackagingMode.FLATTEN, widget._get_selected_packaging_mode())

        package_button = await _wait_for_widget(f"{window.title}//Frame/**/Button[*].text=='Package'")
        self.assertIsNotNone(package_button)
        for _ in range(300):
            if package_button.widget.enabled:
                break
            await omni.kit.app.get_app().next_update_async()
        self.assertTrue(package_button.widget.enabled)

        await package_button.click()
        await self._wait_for_packaging_start_or_error_window()

    async def _wait_for_packaging_start_or_error_window(self):
        for _ in range(120):
            if self._packaging_task_started() or self._is_window_visible(self._ERROR_WINDOW_TITLE):
                return
            await omni.kit.app.get_app().next_update_async()

    async def _package_until_error_window(
        self, widget: PackagingPane, window: ui.Window, expected_asset_names: set[str] | None = None
    ):
        await self._click_package(widget, window)
        await self._wait_for_packaging_error_window(widget)

        expected_asset_names = expected_asset_names or {self._MISSING_REMOVE_ASSET, self._MISSING_REPLACE_ASSET}
        self._assert_error_window_contains_assets(widget, expected_asset_names)
        await self._wait_for_error_window_actions(dict.fromkeys(expected_asset_names, PackagingActions.IGNORE), widget)

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

        select_button, directory_field, file_name_field = await self._get_replacement_file_picker_controls(
            missing_asset_name, file_picker_title
        )

        # Navigate through the real file picker fields so headless CI does not depend on toolbar focus state.
        expected_directory = self._file_picker_path(replacement_path.parent)
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
                    await self._dismiss_dialog("Invalid File", "Okay")
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

    async def _select_invalid_replacement_asset(
        self, missing_asset_name: str, replacement_path: Path, expected_message: str
    ):
        self.assertTrue(replacement_path.exists())
        file_picker_title = f"Select a replacement asset for: ./{missing_asset_name}"
        select_button, directory_field, file_name_field = await self._get_replacement_file_picker_controls(
            missing_asset_name, file_picker_title
        )

        await self._select_file_picker_directory(directory_field, replacement_path.parent)
        await ui_test.human_delay(100)
        await file_name_field.input(str(replacement_path.name), end_key=KeyboardInput.DOWN)
        await ui_test.human_delay(100)

        for _ in range(300):
            if select_button.widget.enabled and file_name_field.model.get_value_as_string() == replacement_path.name:
                break
            await omni.kit.app.get_app().next_update_async()
        self.assertTrue(select_button.widget.enabled)
        await select_button.click()

        await self._wait_for_invalid_replacement_message(expected_message)

    async def _get_replacement_file_picker_controls(self, missing_asset_name: str, file_picker_title: str):
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
        return select_button, directory_field, file_name_field

    async def _wait_for_invalid_replacement_message(self, expected_message: str):
        for _ in range(300):
            if self._is_window_visible(_constants.ASSET_NEED_INGEST_WINDOW_TITLE) and self._window_contains_label_text(
                _constants.ASSET_NEED_INGEST_WINDOW_TITLE, expected_message
            ):
                return
            await omni.kit.app.get_app().next_update_async()
        self.fail(
            f"Timed out waiting for invalid replacement dialog containing {expected_message!r} "
            f"(visible windows: {self._visible_window_titles()}, "
            f"screenshot: {await self._capture_debug_screenshot('invalid_replacement_message_timeout')})"
        )

    async def _select_scan_directory(self, directory: Path):
        directory_field = await _wait_for_widget(
            "Select a directory to scan//Frame/**/StringField[*].identifier=='filepicker_directory_path'"
        )
        self.assertIsNotNone(directory_field)

        self.assertTrue(directory.exists())
        directory_name = self._file_picker_path(directory)
        expected_directory = directory_name
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
        directory_name = self._file_picker_path(directory)
        expected_directory = directory_name
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
        field_value = ""
        if directory_field.model._field is not None:
            field_value = directory_field.model._field.model.get_value_as_string()
        return (field_value or directory_field.model._path or "").replace("\\", "/").rstrip("/")

    @staticmethod
    def _file_picker_path(path: Path) -> str:
        return os.path.abspath(path).replace("\\", "/").rstrip("/")

    @staticmethod
    def _is_window_visible(title: str) -> bool:
        return any(window.title == title and window.visible for window in ui.Workspace.get_windows())

    @staticmethod
    def _window_contains_label_text(window_title: str, expected_text: str) -> bool:
        for label in ui_test.find_all(f"{window_title}//Frame/**/Label[*]") or []:
            if expected_text == label.widget.text:
                return True
        return False

    async def _click_button(self, window_title: str, button_text: str):
        button = await self._wait_for_button(window_title, button_text)
        self.assertIsNotNone(button, f"Unable to find '{button_text}' button in '{window_title}'")
        await button.click()
        await omni.kit.app.get_app().next_update_async()

    async def _dismiss_dialog(self, window_title: str, button_text: str):
        self.assertTrue(
            self._is_window_visible(window_title),
            f"Unable to find visible dialog '{window_title}'. Visible windows: {self._visible_window_titles()}",
        )
        button = await self._wait_for_button(window_title, button_text)
        self.assertIsNotNone(button, f"Unable to find '{button_text}' button in '{window_title}'")
        await button.click()
        await self._wait_for_window_closed(window_title)

    async def _wait_for_button(self, window_title: str, button_text: str, max_frames: int = 600):
        for _ in range(max_frames):
            button = self._find_visible_button(window_title, button_text)
            if button is not None:
                return button
            await omni.kit.app.get_app().next_update_async()
        return None

    @staticmethod
    def _find_visible_button(window_title: str, button_text: str):
        for window in ui.Workspace.get_windows():
            if not window.visible or window.title != window_title:
                continue
            button = WindowRef(window, window_title).find(f"Frame/**/Button[*].text=='{button_text}'")
            if button is not None and _is_visible_widget(button):
                return button
        return None

    async def _wait_for_window_closed(self, window_title: str):
        for _ in range(300):
            if not self._is_window_visible(window_title):
                return
            await omni.kit.app.get_app().next_update_async()
        screenshot_label = f"{window_title.lower().replace(' ', '_')}_close_timeout"
        self.fail(
            f"Timed out waiting for dialog '{window_title}' to close "
            f"(visible windows: {self._visible_window_titles()}, "
            f"screenshot: {await self._capture_debug_screenshot(screenshot_label)})"
        )

    async def _wait_for_packaging_retry_started(self, widget: PackagingPane | None = None) -> list[str]:
        repair_statuses = []
        for _ in range(600):
            self._record_apply_progress_status(widget, repair_statuses)
            if self._packaging_task_started():
                return repair_statuses
            await omni.kit.app.get_app().next_update_async()

        self.fail(
            "Timed out waiting for packaging retry to enter packaging progress "
            f"(visible windows: {self._visible_window_titles()}, "
            f"screenshot: {await self._capture_debug_screenshot('retry_packaging_timeout')})"
        )
        return repair_statuses

    @staticmethod
    def _record_apply_progress_status(widget: PackagingPane | None, repair_statuses: list[str]):
        packaging_window = None if widget is None else widget._packaging_window
        progress_popup = None if packaging_window is None else packaging_window._progress_popup
        if progress_popup is None or not progress_popup.is_visible():
            return
        status = progress_popup.status_text
        if status and (not repair_statuses or repair_statuses[-1] != status):
            repair_statuses.append(status)

    def _assert_repair_progress_is_overall_only(self, repair_statuses: list[str]):
        self.assertTrue(
            any(status.startswith("Applying packaging repairs...") for status in repair_statuses),
            f"Repair progress did not show apply status. Captured: {repair_statuses}",
        )
        self.assertTrue(
            any(status.startswith("Saving repaired layers...") for status in repair_statuses),
            f"Repair progress did not show save status. Captured: {repair_statuses}",
        )
        self.assertFalse(
            any("Removing unresolved reference" in status for status in repair_statuses),
            f"Repair progress showed per-reference spam. Captured: {repair_statuses}",
        )

    def _packaging_task_started(self) -> bool:
        return any(window.title == "Packaging Mod" and window.visible for window in ui.Workspace.get_windows())

    @staticmethod
    def _visible_window_titles() -> list[str]:
        return [window.title for window in ui.Workspace.get_windows() if window.visible]

    async def _assert_package_succeeded(self, widget: PackagingPane, output_file: Path):
        for _ in range(1200):
            if output_file.exists():
                success_button = self._find_visible_button(self._SUCCESS_DIALOG_TITLE, "Okay")
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

    def _assert_output_directory_opened(self, output_directory: Path):
        self._open_directory_mock.assert_called_once_with(("explorer", os.path.normpath(output_directory.as_posix())))

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
        self.assertNotIn(self._MISSING_ABSOLUTE_ASSET, output_text)
        self.assertNotIn(self._MISSING_INSTANCE_ASSET, output_text)
        self.assertNotIn("E:/Missing/Packaging", output_text)

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
            for prompt in list(_PromptManager._prompts):
                if self._is_reference_repair_window(prompt._title):
                    prompt.destroy()
            for window in list(ui.Workspace.get_windows()):
                if self._is_reference_repair_window(window.title):
                    window.visible = False
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
                self._SUCCESS_DIALOG_TITLE,
                "Packaging Mod",
                "Packaging Cannot Continue",
                "Login Required",
                "Mod Packaging Error",
                "Mod Packaging Cancelled",
                "Applying Packaging Repairs",
                "Select a directory to scan",
            }
            or title.startswith("test_packaging_")
            or title.startswith("test_cancelled_packaging_")
            or title.startswith("test_retry_")
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

    def _assert_no_temporary_layers(self, project_root: Path):
        temp_layers = [
            layer_path
            for layer_path in project_root.rglob("*.usd*")
            if self._TEMP_LAYER_PATTERN.search(layer_path.name)
        ]
        self.assertEqual([], temp_layers)
