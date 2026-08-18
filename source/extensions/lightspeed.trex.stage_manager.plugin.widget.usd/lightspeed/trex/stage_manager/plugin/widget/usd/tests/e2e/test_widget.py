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

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import omni.kit.commands
import omni.kit.test
from lightspeed.common import constants
from lightspeed.trex.comfyui.core.core import ComfyUISubmission, ComfyUISubmissionResult
from lightspeed.trex.stage_manager.plugin.tree.usd.category_groups import CategoryGroupsItem as _CategoryGroupsItem
from lightspeed.trex.stage_manager.plugin.tree.usd.category_groups import CategoryGroupsModel as _CategoryGroupsModel
from lightspeed.trex.stage_manager.plugin.widget.usd.action_logic_graph import (
    LogicGraphWidgetPlugin as _LogicGraphWidgetPlugin,
)
from lightspeed.trex.stage_manager.plugin.widget.usd.action_rename_prim import (
    PrimRenameNameActionWidgetPlugin as _PrimRenameNameActionWidgetPlugin,
)
from lightspeed.trex.stage_manager.plugin.widget.usd.focus_in_viewport import (
    FocusInViewportActionWidgetPlugin as _FocusInViewportActionWidgetPlugin,
)
from lightspeed.trex.stage_manager.plugin.widget.usd.state_hidden_category import (
    IsCategoryHiddenStateWidgetPlugin as _IsCategoryHiddenStateWidgetPlugin,
)
from lightspeed.trex.stage_manager.plugin.widget.usd.state_is_capture import (
    IsCaptureStateWidgetPlugin as _IsCaptureStateWidgetPlugin,
)
from lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job import (
    SubmitComfyUIJobActionWidgetPlugin as _SubmitComfyUIJobActionWidgetPlugin,
)
from omni import ui, usd
from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel as _StageManagerTreeModel
from omni.flux.stage_manager.plugin.widget.usd.base import (
    StageManagerStateWidgetPlugin as _StageManagerStateWidgetPlugin,
)
from omni.kit import ui_test
from omni.kit.test_suite.helpers import arrange_windows, get_test_data_path
from pxr import Sdf, Usd


class TestStageManagerPluginWidget(omni.kit.test.AsyncTestCase):
    FOCUS_IN_VIEWPORT_TOOLTIP_ENABLED = "Frame prim in the viewport (F)"
    FOCUS_IN_VIEWPORT_TOOLTIP_DISABLED = "The prim cannot be framed in the viewport"

    # Before running each test
    async def setUp(self):
        self.context = usd.get_context("")
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_path, self.remix_dir = await self.__setup_directories()

    # After running each test
    async def tearDown(self):
        if self.context.get_stage():
            await self.context.close_stage_async()

        await self.__cleanup_directories()
        self.temp_dir.cleanup()

        self.stage = None
        self.context = None
        self.temp_dir = None

    async def __setup_widget(self, widget_plugin_type: type[_StageManagerStateWidgetPlugin]):
        await arrange_windows()

        window = ui.Window(
            f"TestWidgetPluginsWindow_{self._testMethodName}",
            width=200,
            height=100,
            position_x=500,
            position_y=100,
            flags=ui.WINDOW_FLAGS_MODAL | ui.WINDOW_FLAGS_NO_DOCKING,
        )
        with window.frame:
            widget = widget_plugin_type()
        window.focus()
        await ui_test.human_delay()

        return window, widget

    async def __destroy(self, window):
        window.visible = False
        window.destroy()
        await ui_test.human_delay()

    async def __setup_directories(self):
        project_dir = Path(self.temp_dir.name) / "projects" / "MyProject"
        project_path = (project_dir / "my_project.usda").resolve()

        remix_dir = (Path(self.temp_dir.name) / constants.REMIX_FOLDER).resolve()
        captures_dir = remix_dir / constants.REMIX_CAPTURE_FOLDER
        mods_dir = remix_dir / constants.REMIX_MODS_FOLDER
        lib_dir = remix_dir / "lib"

        mod_dir = mods_dir / "ExistingMod"

        os.makedirs(project_dir)
        os.makedirs(captures_dir)
        os.makedirs(lib_dir)
        os.makedirs(mod_dir)

        (lib_dir / "d3d9.dll").touch()

        test_capture_path = Path(get_test_data_path(__name__, "usd/capture.usda")).resolve()
        test_mod_path = Path(get_test_data_path(__name__, "usd/mod.usda")).resolve()

        shutil.copy(str(test_capture_path), str(captures_dir / "capture.usda"))
        shutil.copy(str(test_mod_path), str(mod_dir / constants.REMIX_MOD_FILE))

        return project_path, remix_dir

    async def __create_project(self, create_symlinks: bool):
        test_project_path = Path(get_test_data_path(__name__, "usd/project.usda"))
        shutil.copy(str(test_project_path), str(self.project_path))

        if create_symlinks:
            remix_project = self.remix_dir / constants.REMIX_MODS_FOLDER / self.project_path.parent.stem
            subprocess.check_call(
                f'mklink /J "{remix_project}" "{self.project_path.parent}"',
                shell=True,
            )
            subprocess.check_call(
                f'mklink /J "{self.project_path.parent / constants.REMIX_DEPENDENCIES_FOLDER}" "{self.remix_dir}"',
                shell=True,
            )

    async def test_prim_name_columns_render_one_name_field(self):
        await arrange_windows(topleft_window="Stage")
        window = ui.Window("TestSinglePrimNameField", width=400, height=100)
        model = _StageManagerTreeModel()
        item = _StageManagerTreeItem(
            display_name="TestPrim",
            tooltip="/World/TestPrim",
            data=self.stage.DefinePrim("/World/TestPrim", "Xform"),
        )

        try:
            with window.frame:
                with ui.HStack():
                    item.build_widget()
                    _LogicGraphWidgetPlugin().build_icon_ui(model, item, 0, False)
                    _PrimRenameNameActionWidgetPlugin().build_icon_ui(model, item, 0, False)

            await ui_test.human_delay(5)

            name_fields = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='nickname_field'")
            self.assertEqual(1, len(name_fields))
        finally:
            model.destroy()
            window.destroy()

    async def __cleanup_directories(self):
        shutil.rmtree(self.remix_dir / constants.REMIX_MODS_FOLDER / self.project_path.parent.stem, ignore_errors=True)
        shutil.rmtree(self.project_path.parent / constants.REMIX_DEPENDENCIES_FOLDER, ignore_errors=True)

    async def test_comfyui_action_icon_shows_setup_state_and_opens_ai_tools(self):
        """A real click on the disconnected action opens AI Tools for setup."""
        # Render the Stage Manager action for a real prim while ComfyUI is unavailable.
        window, widget = await self.__setup_widget(widget_plugin_type=_SubmitComfyUIJobActionWidgetPlugin)
        model = _StageManagerTreeModel()
        item = _StageManagerTreeItem(
            display_name="Material", tooltip="Material", data=self.stage.DefinePrim("/Material")
        )
        core = MagicMock(is_ready=False)
        try:
            with (
                patch(
                    "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.get_comfyui_core_instance",
                    return_value=core,
                ),
                patch.object(widget, "_open_ai_tools_layout") as open_layout,
            ):
                with window.frame:
                    widget.build_icon_ui(model, item, 0, False)
                window.focus()
                await ui_test.human_delay(2)

                action = ui_test.find(f"{window.title}//Frame/Image[*].identifier=='submit_comfyui_job_widget_image'")
                self.assertIsNotNone(action)
                self.assertEqual(action.widget.name, "AIToolsDisabled")
                self.assertEqual(
                    action.widget.tooltip,
                    "ComfyUI is not connected, or no workflow is selected. Select to open AI Tools.",
                )

                # Click the visible disabled-state action and follow its recovery path.
                await action.click()
                await ui_test.human_delay()

                open_layout.assert_called_once_with()
        finally:
            await self.__destroy(window)

    async def test_comfyui_action_icon_preserves_multi_selection_for_active_workflow(self):
        """A real click on the ready action submits every selected Stage Manager prim."""
        # Render the ready Stage Manager action for two selected live-stage prims.
        window, widget = await self.__setup_widget(widget_plugin_type=_SubmitComfyUIJobActionWidgetPlugin)
        model = _StageManagerTreeModel()
        first_prim = self.stage.DefinePrim("/FirstMaterial")
        second_prim = self.stage.DefinePrim("/SecondMaterial")
        item = _StageManagerTreeItem(display_name="First Material", tooltip="First Material", data=first_prim)
        second_item = _StageManagerTreeItem(
            display_name="Second Material",
            tooltip="Second Material",
            data=second_prim,
        )
        model.selection = [item, second_item]
        core = MagicMock(is_ready=True)
        core.workflow.name = "Upscale"
        submission = ComfyUISubmission((), 0)
        core.prepare_submission = AsyncMock(return_value=submission)
        core.submit_prepared_submission = AsyncMock(return_value=ComfyUISubmissionResult(0, 0))
        usd.get_context().get_selection().set_selected_prim_paths(
            [str(first_prim.GetPath()), str(second_prim.GetPath())],
            True,
        )
        try:
            with patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.get_comfyui_core_instance",
                return_value=core,
            ):
                with window.frame:
                    widget.build_icon_ui(model, item, 0, False)
                window.focus()
                await ui_test.human_delay(2)

                action = ui_test.find(f"{window.title}//Frame/Image[*].identifier=='submit_comfyui_job_widget_image'")
                self.assertIsNotNone(action)
                self.assertEqual(action.widget.name, "AITools")
                self.assertEqual(
                    action.widget.tooltip,
                    "Run 'Upscale' for this selection using the current AI Tools settings.",
                )

                # Click the visible action and let the production widget prepare and submit the selection.
                await action.click()
                await ui_test.human_delay(5)

                core.prepare_submission.assert_awaited_once_with(
                    prim_paths=["/FirstMaterial", "/SecondMaterial"], progress=ANY, is_cancelled=ANY
                )
                core.submit_prepared_submission.assert_awaited_once_with(submission)
        finally:
            _SubmitComfyUIJobActionWidgetPlugin.cancel_pending_submissions()
            await self.__destroy(window)

    async def test_prim_is_from_capture_or_mod(self):
        # Set up the test
        await self.__create_project(create_symlinks=False)
        _window, _widget = await self.__setup_widget(widget_plugin_type=_IsCaptureStateWidgetPlugin)

        # Find and open the capture layer
        expected_capture_file = Path(self.temp_dir.name) / "rtx-remix" / "captures" / "capture.usda"
        capture_layer = Sdf.Layer.FindOrOpen(str(expected_capture_file))
        self.stage = Usd.Stage.Open(capture_layer)

        # Create sample data
        light_prim = self.stage.GetPrimAtPath("/RootNode/meshes/mesh_one/SphereLight")
        item = _StageManagerTreeItem(display_name="sample_item", tooltip="foobar", data=light_prim)

        # Build the widget icon with the capture layer sample data
        with _window.frame:
            _widget.build_icon_ui(_StageManagerTreeModel(), item, 1, True)
        await ui_test.human_delay(5)

        # Ensure the UI correlates with capture layer data
        capture_state_widget_image = ui_test.find(
            f"{_window.title}//Frame/Image[*].identifier=='capture_state_widget_image'"
        )
        self.assertIsNotNone(capture_state_widget_image)
        self.assertEqual(capture_state_widget_image.widget.name, "Capture")
        self.assertEqual(capture_state_widget_image.widget.tooltip, "The prim originates from a capture layer.")

        # Find and open the mod layer
        expected_mod_file = Path(self.temp_dir.name) / "rtx-remix" / "mods" / "ExistingMod" / "mod.usda"
        mod_layer = Sdf.Layer.FindOrOpen(str(expected_mod_file))
        self.stage = Usd.Stage.Open(mod_layer)

        # Create sample data
        light_prim = self.stage.GetPrimAtPath("/RootNode/meshes/mesh_two/SphereLight")
        item = _StageManagerTreeItem(display_name="sample_item", tooltip="foobar", data=light_prim)

        # Build the widget icon with the mod layer sample data
        with _window.frame:
            _widget.build_icon_ui(_StageManagerTreeModel(), item, 1, True)
        await ui_test.human_delay(5)

        # Ensure the UI correlates with mod layer data
        window_widgets = ui_test.find_all(f"{_window.title}//Frame/capture_state_widget_image")
        capture_state_widget_image = window_widgets[0]
        self.assertIsNotNone(capture_state_widget_image)
        self.assertEqual(capture_state_widget_image.widget.name, "Collection")
        self.assertEqual(capture_state_widget_image.widget.tooltip, "The prim originates from a mod layer.")

        await self.__destroy(_window)

    async def test_prim_can_be_framed_in_viewport(self):
        # Set up the test
        await self.__create_project(create_symlinks=False)
        _window, _widget = await self.__setup_widget(widget_plugin_type=_FocusInViewportActionWidgetPlugin)

        # Find and open the capture layer
        expected_capture_file = Path(self.temp_dir.name) / "rtx-remix" / "captures" / "capture.usda"
        capture_layer = Sdf.Layer.FindOrOpen(str(expected_capture_file))
        self.stage = Usd.Stage.Open(capture_layer)

        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
        # Create sample data for a light
        light_prim = self.stage.GetPrimAtPath("/RootNode/meshes/mesh_one/SphereLight")
        item = _StageManagerTreeItem(display_name="sample_item", tooltip="foobar", data=light_prim)

        # Build the widget icon with the capture layer sample data
        with _window.frame:
            _widget.build_icon_ui(_StageManagerTreeModel(), item, level=4, expanded=True)
        await ui_test.human_delay(5)

        # Ensure the widget icon is enabled since it is a light
        focus_in_viewport_widget_image = ui_test.find(
            f"{_window.title}//Frame/Image[*].identifier=='focus_in_viewport_widget_image'"
        )
        self.assertIsNotNone(focus_in_viewport_widget_image)
        self.assertTrue(focus_in_viewport_widget_image.widget.enabled)
        self.assertEqual(focus_in_viewport_widget_image.widget.name, "Frame")
        self.assertEqual(
            focus_in_viewport_widget_image.widget.tooltip,
            TestStageManagerPluginWidget.FOCUS_IN_VIEWPORT_TOOLTIP_ENABLED,
        )

        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
        # Create sample data for a mesh
        mesh_prim = self.stage.GetPrimAtPath("/RootNode/meshes/mesh_one")
        item = _StageManagerTreeItem(display_name="sample_item", tooltip="foobar", data=mesh_prim)

        # Build the widget icon with the capture layer sample data
        with _window.frame:
            _widget.build_icon_ui(_StageManagerTreeModel(), item, level=3, expanded=True)
        await ui_test.human_delay(5)

        # Ensure the widget icon is enabled since it is a mesh
        focus_in_viewport_widget_image = ui_test.find(
            f"{_window.title}//Frame/Image[*].identifier=='focus_in_viewport_widget_image'"
        )
        self.assertIsNotNone(focus_in_viewport_widget_image)
        self.assertTrue(focus_in_viewport_widget_image.widget.enabled)
        self.assertEqual(focus_in_viewport_widget_image.widget.name, "Frame")
        self.assertEqual(
            focus_in_viewport_widget_image.widget.tooltip,
            TestStageManagerPluginWidget.FOCUS_IN_VIEWPORT_TOOLTIP_ENABLED,
        )

        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
        # Create sample data for an instance
        instance_prim = self.stage.GetPrimAtPath("/RootNode/instances/inst_4381216431E468DC_1/mesh")
        item = _StageManagerTreeItem(display_name="sample_item", tooltip="foobar", data=instance_prim)

        # Build the widget icon with the capture layer sample data
        with _window.frame:
            _widget.build_icon_ui(_StageManagerTreeModel(), item, level=4, expanded=True)
        await ui_test.human_delay(5)

        # Ensure the widget icon is enabled since it is an instance
        focus_in_viewport_widget_image = ui_test.find(
            f"{_window.title}//Frame/Image[*].identifier=='focus_in_viewport_widget_image'"
        )
        self.assertIsNotNone(focus_in_viewport_widget_image)
        self.assertTrue(focus_in_viewport_widget_image.widget.enabled)
        self.assertEqual(focus_in_viewport_widget_image.widget.name, "Frame")
        self.assertEqual(
            focus_in_viewport_widget_image.widget.tooltip,
            TestStageManagerPluginWidget.FOCUS_IN_VIEWPORT_TOOLTIP_ENABLED,
        )

        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
        # Create sample data for a parent mesh prim
        parent_mesh_prim = self.stage.GetPrimAtPath("/RootNode/meshes")
        item = _StageManagerTreeItem(display_name="sample_item", tooltip="foobar", data=parent_mesh_prim)

        # Build the widget icon with the capture layer sample data
        with _window.frame:
            _widget.build_icon_ui(_StageManagerTreeModel(), item, level=2, expanded=True)
        await ui_test.human_delay(5)

        # Ensure the widget icon is disabled
        focus_in_viewport_widget_image = ui_test.find(
            f"{_window.title}//Frame/Image[*].identifier=='focus_in_viewport_widget_image'"
        )
        self.assertIsNotNone(focus_in_viewport_widget_image)
        self.assertFalse(focus_in_viewport_widget_image.widget.enabled)
        self.assertEqual(focus_in_viewport_widget_image.widget.name, "FrameDisabled")
        self.assertEqual(
            focus_in_viewport_widget_image.widget.tooltip,
            TestStageManagerPluginWidget.FOCUS_IN_VIEWPORT_TOOLTIP_DISABLED,
        )

        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
        # Create sample data for the RootNode
        root_node_prim = self.stage.GetPrimAtPath("/RootNode")
        item = _StageManagerTreeItem(display_name="sample_item", tooltip="foobar", data=root_node_prim)

        # Build the widget icon with the capture layer sample data
        with _window.frame:
            _widget.build_icon_ui(_StageManagerTreeModel(), item, level=1, expanded=True)
        await ui_test.human_delay(5)

        # Ensure the widget icon is disabled
        focus_in_viewport_widget_image = ui_test.find(
            f"{_window.title}//Frame/Image[*].identifier=='focus_in_viewport_widget_image'"
        )
        self.assertIsNotNone(focus_in_viewport_widget_image)
        self.assertFalse(focus_in_viewport_widget_image.widget.enabled)
        self.assertEqual(focus_in_viewport_widget_image.widget.name, "FrameDisabled")
        self.assertEqual(
            focus_in_viewport_widget_image.widget.tooltip,
            TestStageManagerPluginWidget.FOCUS_IN_VIEWPORT_TOOLTIP_DISABLED,
        )

        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
        # Create sample data for a material prim
        material_prim = self.stage.GetPrimAtPath("/RootNode/Looks/mat_7546356AB6B4A5D2/Shader")
        item = _StageManagerTreeItem(display_name="sample_item", tooltip="foobar", data=material_prim)

        # Build the widget icon with the capture layer sample data
        with _window.frame:
            _widget.build_icon_ui(_StageManagerTreeModel(), item, level=3, expanded=True)
        await ui_test.human_delay(5)

        # Ensure the widget icon is disabled since it is not a light, mesh, or instance
        focus_in_viewport_widget_image = ui_test.find(
            f"{_window.title}//Frame/Image[*].identifier=='focus_in_viewport_widget_image'"
        )
        self.assertIsNotNone(focus_in_viewport_widget_image)
        self.assertFalse(focus_in_viewport_widget_image.widget.enabled)
        self.assertEqual(focus_in_viewport_widget_image.widget.name, "FrameDisabled")
        self.assertEqual(
            focus_in_viewport_widget_image.widget.tooltip,
            TestStageManagerPluginWidget.FOCUS_IN_VIEWPORT_TOOLTIP_DISABLED,
        )

        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
        # Create sample data for a "other" prim
        other_prim = self.stage.GetPrimAtPath("/RootNode/Other/some_random_prim")
        item = _StageManagerTreeItem(display_name="sample_item", tooltip="foobar", data=other_prim)

        # Build the widget icon with the capture layer sample data
        with _window.frame:
            _widget.build_icon_ui(_StageManagerTreeModel(), item, level=3, expanded=True)
        await ui_test.human_delay(5)

        # Ensure the widget icon is disabled since it is not a light, mesh, or instance
        focus_in_viewport_widget_image = ui_test.find(
            f"{_window.title}//Frame/Image[*].identifier=='focus_in_viewport_widget_image'"
        )
        self.assertIsNotNone(focus_in_viewport_widget_image)
        self.assertFalse(focus_in_viewport_widget_image.widget.enabled)
        self.assertEqual(focus_in_viewport_widget_image.widget.name, "FrameDisabled")
        self.assertEqual(
            focus_in_viewport_widget_image.widget.tooltip,
            TestStageManagerPluginWidget.FOCUS_IN_VIEWPORT_TOOLTIP_DISABLED,
        )

        # Ensure the widget icon is disabled since it is not a light, mesh, or instance
        focus_in_viewport_widget_image = ui_test.find(
            f"{_window.title}//Frame/Image[*].identifier=='focus_in_viewport_widget_image'"
        )
        self.assertIsNotNone(focus_in_viewport_widget_image)
        self.assertFalse(focus_in_viewport_widget_image.widget.enabled)
        self.assertEqual(focus_in_viewport_widget_image.widget.name, "FrameDisabled")
        self.assertEqual(
            focus_in_viewport_widget_image.widget.tooltip,
            TestStageManagerPluginWidget.FOCUS_IN_VIEWPORT_TOOLTIP_DISABLED,
        )

        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
        # Find and open the project layer
        project_layer = Sdf.Layer.FindOrOpen(str(self.project_path))
        self.stage = Usd.Stage.Open(project_layer)

        # Create sample data for a waypoint prim
        waypoint_prim = self.stage.GetPrimAtPath("/Viewport_Waypoints/Waypoint_01")
        item = _StageManagerTreeItem(display_name="sample_item", tooltip="foobar", data=waypoint_prim)

        # Build the widget icon with the capture layer sample data
        with _window.frame:
            _widget.build_icon_ui(_StageManagerTreeModel(), item, level=2, expanded=True)
        await ui_test.human_delay(5)

        # Ensure the widget icon is disabled since it is not a light, mesh, or instance
        focus_in_viewport_widget_image = ui_test.find(
            f"{_window.title}//Frame/Image[*].identifier=='focus_in_viewport_widget_image'"
        )
        self.assertIsNotNone(focus_in_viewport_widget_image)
        self.assertFalse(focus_in_viewport_widget_image.widget.enabled)
        self.assertEqual(focus_in_viewport_widget_image.widget.name, "FrameDisabled")
        self.assertEqual(
            focus_in_viewport_widget_image.widget.tooltip,
            TestStageManagerPluginWidget.FOCUS_IN_VIEWPORT_TOOLTIP_DISABLED,
        )

        # Ensure the widget icon is disabled since it is not a light, mesh, or instance
        focus_in_viewport_widget_image = ui_test.find(
            f"{_window.title}//Frame/Image[*].identifier=='focus_in_viewport_widget_image'"
        )
        self.assertIsNotNone(focus_in_viewport_widget_image)
        self.assertFalse(focus_in_viewport_widget_image.widget.enabled)
        self.assertEqual(focus_in_viewport_widget_image.widget.name, "FrameDisabled")
        self.assertEqual(
            focus_in_viewport_widget_image.widget.tooltip,
            TestStageManagerPluginWidget.FOCUS_IN_VIEWPORT_TOOLTIP_DISABLED,
        )

        await self.__destroy(_window)

    async def test_prim_category_visible(self):
        # Set up the test
        await self.__create_project(create_symlinks=False)
        _window, _widget = await self.__setup_widget(widget_plugin_type=_IsCategoryHiddenStateWidgetPlugin)

        # Find and open the capture layer and adding attr for for check
        expected_capture_file = Path(self.temp_dir.name) / "rtx-remix" / "captures" / "capture.usda"
        capture_layer = Sdf.Layer.FindOrOpen(str(expected_capture_file))
        self.stage = Usd.Stage.Open(capture_layer)

        # Create sample data
        light_prim = self.stage.GetPrimAtPath("/RootNode/meshes/mesh_one/SphereLight")
        omni.kit.commands.execute(
            "CreateUsdAttribute",
            prim=light_prim,
            attr_name="remix_category:particle",
            attr_value=True,
            attr_type=Sdf.ValueTypeNames.Bool,
        )
        item = _CategoryGroupsItem(display_name="Particle", tooltip="foobar", data=light_prim)

        # Build the widget icon with the capture layer sample data
        with _window.frame:
            _widget.build_icon_ui(_CategoryGroupsModel(), item, 1, True)
        await ui_test.human_delay(5)

        # Ensure the UI correlates with capture layer data
        category_state_widget_image = ui_test.find(
            f"{_window.title}//Frame/Image[*].identifier=='category_state_widget_image'"
        )
        self.assertIsNotNone(category_state_widget_image)
        self.assertEqual(category_state_widget_image.widget.name, "CategoriesShown")
        self.assertEqual(
            category_state_widget_image.widget.tooltip,
            "The prim's visibility is not affected by the assigned categories",
        )

        await self.__destroy(_window)

    async def test_prim_category_hidden(self):
        # Set up the test
        await self.__create_project(create_symlinks=False)
        _window, _widget = await self.__setup_widget(widget_plugin_type=_IsCategoryHiddenStateWidgetPlugin)

        # Find and open the capture layer
        expected_capture_file = Path(self.temp_dir.name) / "rtx-remix" / "captures" / "capture.usda"
        capture_layer = Sdf.Layer.FindOrOpen(str(expected_capture_file))
        self.stage = Usd.Stage.Open(capture_layer)

        # Create sample data and adding attr for check
        light_prim = self.stage.GetPrimAtPath("/RootNode/meshes/mesh_one/SphereLight")
        omni.kit.commands.execute(
            "CreateUsdAttribute",
            prim=light_prim,
            attr_name="remix_category:hidden",
            attr_value=True,
            attr_type=Sdf.ValueTypeNames.Bool,
        )
        item = _CategoryGroupsItem(display_name="Hidden", tooltip="foobar", data=light_prim)

        # Build the widget icon with the capture layer sample data
        with _window.frame:
            _widget.build_icon_ui(_CategoryGroupsModel(), item, 1, True)
        await ui_test.human_delay(5)

        # Ensure the icon indicates that the prim isn't visible
        category_state_widget_image = ui_test.find(
            f"{_window.title}//Frame/Image[*].identifier=='category_state_widget_image'"
        )
        self.assertIsNotNone(category_state_widget_image)
        self.assertEqual(category_state_widget_image.widget.name, "CategoriesHidden")
        self.assertEqual(
            category_state_widget_image.widget.tooltip,
            "The prim is not visible because the following category is not rendered in the viewport: \n- Hidden",
        )

        await self.__destroy(_window)
