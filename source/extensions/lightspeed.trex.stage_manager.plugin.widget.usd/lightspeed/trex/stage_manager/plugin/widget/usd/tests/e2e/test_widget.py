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

import omni.kit.commands
import omni.kit.test
from lightspeed.common import constants
from lightspeed.trex.stage_manager.plugin.tree.usd.category_groups import CategoryGroupsItem as _CategoryGroupsItem
from lightspeed.trex.stage_manager.plugin.tree.usd.category_groups import CategoryGroupsModel as _CategoryGroupsModel
from lightspeed.trex.stage_manager.plugin.widget.usd.focus_in_viewport import (
    FocusInViewportActionWidgetPlugin as _FocusInViewportActionWidgetPlugin,
)
from lightspeed.trex.stage_manager.plugin.widget.usd.state_hidden_category import (
    IsCategoryHiddenStateWidgetPlugin as _IsCategoryHiddenStateWidgetPlugin,
)
from lightspeed.trex.stage_manager.plugin.widget.usd.state_is_capture import (
    IsCaptureStateWidgetPlugin as _IsCaptureStateWidgetPlugin,
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
    FOCUS_IN_VIEWPORT_TOOLTIP_DISABLED = "Prim cannot be framed within the viewport"

    # Before running each test
    async def setUp(self):
        await usd.get_context().new_stage_async()
        self.stage = usd.get_context().get_stage()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_path, self.remix_dir = await self.__setup_directories()

    # After running each test
    async def tearDown(self):
        if usd.get_context().get_stage():
            await usd.get_context().close_stage_async()

        await self.__cleanup_directories()
        self.temp_dir.cleanup()

        self.stage = None
        self.temp_dir = None

    async def __setup_widget(self, widget_plugin_type: type[_StageManagerStateWidgetPlugin]):
        await arrange_windows(topleft_window="Stage")

        window = ui.Window("TestWidgetPluginsWindow", width=200, height=100)
        with window.frame:
            widget = widget_plugin_type()

        return window, widget

    async def __destroy(self, window, widget):
        # await wait_stage_loading()  # NOTE: This causes the window to not fully destroy

        widget = None  # noqa: F841
        window.destroy()

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

    async def __cleanup_directories(self):
        shutil.rmtree(self.remix_dir / constants.REMIX_MODS_FOLDER / self.project_path.parent.stem, ignore_errors=True)
        shutil.rmtree(self.project_path.parent / constants.REMIX_DEPENDENCIES_FOLDER, ignore_errors=True)

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

        await self.__destroy(_window, _widget)

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

        await self.__destroy(_window, _widget)

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

        await self.__destroy(_window, _widget)

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

        await self.__destroy(_window, _widget)
