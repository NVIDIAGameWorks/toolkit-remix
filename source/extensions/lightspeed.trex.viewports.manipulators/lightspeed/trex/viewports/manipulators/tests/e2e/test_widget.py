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

from __future__ import annotations

import carb.settings
import omni.kit.app
import omni.ui as ui
import omni.usd
from carb.input import MouseEventType
from lightspeed.common.constants import LayoutFiles as _LayoutFiles
from lightspeed.common.constants import WindowNames as _WindowNames
from lightspeed.trex.utils.widget.quicklayout import load_layout as _load_layout
from lightspeed.trex.viewports.shared.widget import get_instance as _get_viewport_instance
from omni.flux.property_widget_builder.model.usd import USDModel as _USDModel
from omni.flux.property_widget_builder.model.usd import get_usd_listener_instance as _get_usd_listener_instance
from omni.flux.utils.widget.resources import get_quicklayout_config as _get_quicklayout_config
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit import ui_test
from omni.kit.test_suite.helpers import arrange_windows, open_stage, wait_stage_loading
from omni.kit.ui_test import Vec2
from omni.ui.tests.test_base import OmniUiTest
from omni.ui import scene as sc
from pxr import UsdGeom

_INSTANCE_SELECTION_PATH = (
    "/RootNode/instances/inst_BAC90CAA733B0859_1/ref_c89e0497f4ff4dc4a7b70b79c85692da/XForms/Root/Cube_01"
)
_INSTANCE_TRANSFORM_PATH = (
    "/RootNode/meshes/mesh_BAC90CAA733B0859/ref_c89e0497f4ff4dc4a7b70b79c85692da/XForms/Root/Cube_01"
)
_TRANSFORM_OPERATION_SETTING = "/app/transform/operation"
_TRANSFORM_MOVE_OPERATION = "move"
_CAMERA_DRAG_DISTANCE = 120


def _normalize_value(value):
    try:
        return tuple(value)
    except TypeError:
        return value


def _snapshot_property_model(model) -> tuple[tuple[tuple[str, ...], tuple[object, ...]], ...]:
    rows = []
    for item in model.get_all_items():
        name_models = item.name_models or ()
        value_models = item.value_models or ()
        names = []
        for name_model in name_models:
            try:
                names.append(name_model.get_value_as_string())
            except Exception:  # noqa: BLE001
                names.append("<error>")
        values = []
        for value_model in value_models:
            try:
                values.append(_normalize_value(value_model.get_value()))
            except Exception:  # noqa: BLE001
                values.append("<error>")
        rows.append((tuple(names), tuple(values)))
    return tuple(rows)


class TestViewportManipulators(OmniUiTest):
    async def setUp(self):
        await super().setUp()
        # Load the real workspace and project so manipulator, viewport, and Properties UI wiring is active.
        await arrange_windows()
        usd_context = omni.usd.get_context("")
        if usd_context.can_close_stage():
            await usd_context.close_stage_async()
        await open_stage(_get_test_data("usd/project_example/combined.usda"))
        await wait_stage_loading()
        await self.__show_workspace_layout()

    async def tearDown(self):
        usd_context = omni.usd.get_context("")
        if usd_context.can_close_stage():
            await usd_context.close_stage_async()
        await super().tearDown()

    async def __wait_n_updates(self, count: int = 5):
        app = omni.kit.app.get_app()
        for _ in range(count):
            await app.next_update_async()

    async def __show_workspace_layout(self):
        _load_layout(_get_quicklayout_config(_LayoutFiles.WORKSPACE_PAGE))

        # Wait for the workspace pieces the test drives directly instead of assuming layout load is synchronous.
        for _ in range(120):
            viewport_window = ui.Workspace.get_window(_WindowNames.VIEWPORT)
            properties_window = ui.Workspace.get_window(_WindowNames.PROPERTIES)
            stage_manager_window = ui.Workspace.get_window(_WindowNames.STAGE_MANAGER)
            viewport_widget = _get_viewport_instance("")
            if viewport_window and properties_window and stage_manager_window and viewport_widget:
                break
            await self.__wait_n_updates(1)

        for title in (_WindowNames.VIEWPORT, _WindowNames.PROPERTIES, _WindowNames.STAGE_MANAGER):
            ui.Workspace.show_window(title, True)

        await ui_test.human_delay(human_delay_speed=20)

        for title in (_WindowNames.VIEWPORT, _WindowNames.PROPERTIES, _WindowNames.STAGE_MANAGER):
            window = ui.Workspace.get_window(title)
            self.assertIsNotNone(window)
            self.assertTrue(window.visible)

        viewport_widget = _get_viewport_instance("")
        self.assertIsNotNone(viewport_widget)
        await self.__wait_for_rendered_viewport(viewport_widget)

        # The Properties selection tree is the visible signal that selection-driven property models are ready.
        selection_tree = ui_test.find(
            f"{_WindowNames.PROPERTIES}//Frame/**/TreeView[*].identifier=='LiveSelectionTreeView'"
        )
        self.assertIsNotNone(selection_tree)
        await self.__collapse_unrelated_property_sections()

    async def __collapse_unrelated_property_sections(self):
        for section_title in ("MATERIAL PROPERTIES", "PARTICLE PROPERTIES", "LOGIC PROPERTIES"):
            await self.__set_property_section_collapsed(section_title, True)

    async def __set_property_section_collapsed(self, section_title: str, collapsed: bool):
        for _ in range(10):
            title_labels = ui_test.find_all(
                f"{_WindowNames.PROPERTIES}//Frame/**/Label[*].name=='PropertiesPaneSectionTitle'"
            )
            frame_arrows = ui_test.find_all(
                f"{_WindowNames.PROPERTIES}//Frame/**/Image[*].identifier=='PropertyCollapsableFrameArrow'"
            )
            if title_labels and len(title_labels) == len(frame_arrows):
                break
            await self.__wait_n_updates(1)
        else:
            self.fail("Could not resolve the properties pane collapsable sections")

        try:
            section_index = next(
                index for index, label in enumerate(title_labels) if label.widget.text == section_title
            )
        except StopIteration as exc:
            raise AssertionError(f"Missing properties pane section '{section_title}'") from exc

        section_arrow = frame_arrows[section_index]
        arrow_name = section_arrow.widget.style_type_name_override
        is_collapsed = arrow_name == "ImagePropertiesPaneSectionTriangleCollapsed"
        if is_collapsed == collapsed:
            return

        await section_arrow.click()
        await ui_test.human_delay(human_delay_speed=6)
        arrow_name = section_arrow.widget.style_type_name_override
        is_collapsed = arrow_name == "ImagePropertiesPaneSectionTriangleCollapsed"

    async def __wait_for_rendered_viewport(self, viewport_widget):
        viewport_widget.set_active(True)
        await self.__wait_n_updates(5)
        viewport_api = viewport_widget.viewport_api
        await viewport_api.wait_for_rendered_frames(5)
        await self.__wait_n_updates(5)
        self.assertEqual(viewport_api.hydra_engine, "pxr")

    def __get_runtime_prim_transform_manipulator(self, viewport_widget):
        prim_layer = viewport_widget.viewport_layers.find_viewport_layer("Prim Transform", "manipulator")
        self.assertIsNotNone(prim_layer)
        prim_transform_manipulator = prim_layer.layer.manipulator()
        self.assertIsNotNone(prim_transform_manipulator)
        runtime_manipulator = prim_transform_manipulator._manipulator
        self.assertIsNotNone(runtime_manipulator)
        return runtime_manipulator

    @staticmethod
    def __screen_point_from_texture_pixel(viewport_widget, viewport_api, pixel) -> Vec2:
        viewport_frame = viewport_widget.viewport_frame()
        resolution = viewport_api.resolution
        return Vec2(
            viewport_frame.screen_position_x + (pixel[0] * viewport_frame.computed_width / resolution[0]),
            viewport_frame.screen_position_y + (pixel[1] * viewport_frame.computed_height / resolution[1]),
        )

    def __scene_local_point_to_screen(self, viewport_widget, viewport_api, scene_item, local_point) -> Vec2 | None:
        ndc_pos = scene_item.transform_space(sc.Space.OBJECT, sc.Space.NDC, list(local_point))
        if ndc_pos[2] > 1.0:
            return None
        pixel_loc, ret_viewport_api = viewport_api.map_ndc_to_texture_pixel(ndc_pos)
        if not ret_viewport_api:
            return None
        return self.__screen_point_from_texture_pixel(viewport_widget, viewport_api, pixel_loc)

    def __get_asset_drag_points(self, viewport_widget) -> tuple[Vec2, Vec2]:
        runtime_manipulator = self.__get_runtime_prim_transform_manipulator(viewport_widget)
        viewport_api = viewport_widget.viewport_api

        # Project the active manipulator handle into screen space so the drag starts where a user can click.
        start = self.__scene_local_point_to_screen(
            viewport_widget, viewport_api, runtime_manipulator._translate_line_x, [60, 0, 0]
        )
        end = self.__scene_local_point_to_screen(
            viewport_widget, viewport_api, runtime_manipulator._translate_line_x, [100, 0, 0]
        )

        self.assertIsNotNone(start)
        self.assertIsNotNone(end)
        return start, end

    @staticmethod
    def __get_attribute_by_prefix(prim, prefix: str):
        for attr in prim.GetAttributes():
            if attr.GetName().startswith(prefix):
                return attr
        return None

    def __get_runtime_manipulated_prim_paths(self, viewport_widget) -> tuple[str, ...]:
        runtime_manipulator = self.__get_runtime_prim_transform_manipulator(viewport_widget)
        model = runtime_manipulator.model
        self.assertIsNotNone(model)
        xformable_paths = tuple(str(path) for path in model._xformable_prim_paths or ())
        consolidated_paths = tuple(str(path) for path in model._consolidated_xformable_prim_paths or ())
        return consolidated_paths or xformable_paths

    @staticmethod
    def __model_prim_paths(model) -> tuple[str, ...]:
        if not isinstance(model, _USDModel):
            return ()
        return tuple(str(path) for path in model.prim_paths or ())

    def __property_models_for_paths(self, related_paths: set[str]):
        return [
            model
            for model in _get_usd_listener_instance()._models
            if any(path in related_paths for path in self.__model_prim_paths(model))
        ]

    @staticmethod
    def __snapshot_property_models(models):
        return {id(model): _snapshot_property_model(model) for model in models}

    async def __wait_for_property_models_to_change(self, models, baseline_snapshots):
        for _ in range(60):
            current_snapshots = self.__snapshot_property_models(models)
            if current_snapshots != baseline_snapshots:
                return current_snapshots
            await self.__wait_n_updates(1)
        self.fail("Property UI did not refresh after the user action completed")
        return baseline_snapshots

    async def __prepare_selected_asset(
        self,
        *,
        selection_path: str = _INSTANCE_SELECTION_PATH,
    ):
        usd_context = omni.usd.get_context("")
        stage = usd_context.get_stage()
        viewport_widget = _get_viewport_instance("")
        self.assertIsNotNone(viewport_widget)
        viewport_widget.set_active(True)
        carb.settings.get_settings().set(_TRANSFORM_OPERATION_SETTING, _TRANSFORM_MOVE_OPERATION)
        await ui_test.human_delay(human_delay_speed=10)

        # Select and frame the asset so the real viewport manipulator and Properties tree target the same prim.
        usd_context.get_selection().set_selected_prim_paths([selection_path], False)
        await ui_test.human_delay(human_delay_speed=15)
        viewport_widget.frame_viewport_selection([selection_path])
        await ui_test.human_delay(human_delay_speed=15)

        mesh_prim_frame = ui_test.find(f"{_WindowNames.PROPERTIES}//Frame/**/Frame[*].identifier=='frame_mesh_prim'")
        mesh_ref_frame = ui_test.find(f"{_WindowNames.PROPERTIES}//Frame/**/Frame[*].identifier=='frame_mesh_ref'")
        self.assertIsNotNone(mesh_prim_frame)
        self.assertIsNotNone(mesh_ref_frame)
        self.assertTrue(mesh_prim_frame.widget.visible or mesh_ref_frame.widget.visible)

        selection_tree_items = ui_test.find_all(f"{_WindowNames.PROPERTIES}//Frame/**/Label[*].identifier=='item_prim'")
        self.assertTrue(selection_tree_items)

        await selection_tree_items[-1].click()
        await ui_test.human_delay(human_delay_speed=10)

        manipulated_prim_paths = self.__get_runtime_manipulated_prim_paths(viewport_widget)
        self.assertTrue(manipulated_prim_paths)
        prim = stage.GetPrimAtPath(manipulated_prim_paths[0])
        # Resolve the authored USD attribute before dragging so failures can distinguish hit-test from authoring.
        target_attr = self.__get_attribute_by_prefix(prim, "xformOp:translate")
        self.assertIsNotNone(target_attr)
        self.assertTrue(target_attr.IsValid())

        viewport_ref = ui_test.find(f"{_WindowNames.VIEWPORT}//Frame/**/.identifier == 'viewport'")
        self.assertIsNotNone(viewport_ref)
        await viewport_ref.click()
        await ui_test.human_delay(human_delay_speed=3)
        start, end = self.__get_asset_drag_points(viewport_widget)
        await ui_test.human_delay(human_delay_speed=10)

        return target_attr, start, end, manipulated_prim_paths

    async def __open_camera_properties(self, camera_path: str):
        viewport_widget = _get_viewport_instance("")
        self.assertIsNotNone(viewport_widget)
        viewport_widget.set_active(True)
        # Open camera properties through the viewport menu path so the same UI models are used as in the app.
        viewport_widget._camera_menu_item_option_clicked(camera_path)
        await ui_test.human_delay(human_delay_speed=8)

        for _attempt in range(20):
            section_titles = [
                label.widget.text
                for label in ui_test.find_all(
                    f"{_WindowNames.VIEWPORT}//Frame/**/Label[*].name=='PropertiesPaneSectionTitle'"
                )
            ]
            if "CAMERA PROPERTIES" in section_titles:
                return
            await self.__wait_n_updates(1)

        self.fail(f"Could not open camera properties for {camera_path}")

    @staticmethod
    def __flatten_matrix(matrix) -> tuple[float, ...]:
        return tuple(component for row in matrix for component in row)

    def __get_camera_matrix(self, viewport_api) -> tuple[float, ...]:
        stage = omni.usd.get_context(viewport_api.usd_context_name).get_stage()
        camera_prim = stage.GetPrimAtPath(viewport_api.camera_path)
        self.assertTrue(camera_prim.IsValid())
        return self.__flatten_matrix(UsdGeom.Xformable(camera_prim).GetLocalTransformation(viewport_api.time))

    async def test_translate_drag_defers_property_ui_until_mouse_release(self):
        # Prepare a real translate manipulator drag and snapshot the visible property models before interaction.
        target_attr, start, end, manipulated_prim_paths = await self.__prepare_selected_asset()
        related_paths = {
            _INSTANCE_SELECTION_PATH,
            _INSTANCE_TRANSFORM_PATH,
            str(target_attr.GetPath().GetPrimPath()),
            *manipulated_prim_paths,
        }
        related_models = self.__property_models_for_paths(related_paths)
        self.assertTrue(related_models)
        baseline_snapshots = self.__snapshot_property_models(related_models)
        initial_value = target_attr.Get()
        pause = start + ((end - start) * 0.55)

        # Hold the mouse button down and drag partway; USD should update while the Properties UI stays frozen.
        await ui_test.input.emulate_mouse(MouseEventType.MOVE, start)
        await ui_test.human_delay(human_delay_speed=2)
        await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN, start)
        await ui_test.human_delay(human_delay_speed=2)
        await ui_test.input.emulate_mouse_slow_move(start, pause, num_steps=18, human_delay_speed=2)
        await ui_test.human_delay(human_delay_speed=90)

        current_value = target_attr.Get()
        self.assertNotEqual(_normalize_value(current_value), _normalize_value(initial_value))
        self.assertEqual(self.__snapshot_property_models(related_models), baseline_snapshots)

        await ui_test.input.emulate_mouse_slow_move(pause, end, num_steps=18, human_delay_speed=2)
        await ui_test.human_delay(human_delay_speed=45)
        self.assertEqual(self.__snapshot_property_models(related_models), baseline_snapshots)

        # Release the mouse to finish the interaction; the deferred USD notice should refresh Properties now.
        await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
        await ui_test.human_delay(human_delay_speed=8)

        post_drag_snapshots = await self.__wait_for_property_models_to_change(related_models, baseline_snapshots)
        self.assertNotEqual(post_drag_snapshots, baseline_snapshots)

    async def test_camera_right_drag_defers_property_ui_until_mouse_release(self):
        viewport_widget = _get_viewport_instance("")
        self.assertIsNotNone(viewport_widget)
        viewport_api = viewport_widget.viewport_api
        camera_path = viewport_api.camera_path.pathString
        viewport_ref = ui_test.find(f"{_WindowNames.VIEWPORT}//Frame/**/.identifier == 'viewport'")
        self.assertIsNotNone(viewport_ref)

        # Open the active camera in Properties and snapshot its displayed values before the RMB drag.
        await self.__open_camera_properties(camera_path)
        related_models = self.__property_models_for_paths({camera_path})
        self.assertTrue(related_models)
        baseline_snapshots = self.__snapshot_property_models(related_models)
        initial_camera_matrix = self.__get_camera_matrix(viewport_api)
        start = viewport_ref.center + Vec2(_CAMERA_DRAG_DISTANCE, 0)
        end = viewport_ref.center - Vec2(_CAMERA_DRAG_DISTANCE, 0)

        # Drag with RMB held down; the camera matrix should move while Properties remains unchanged mid-interaction.
        await ui_test.input.emulate_mouse(MouseEventType.MOVE, start)
        await ui_test.human_delay(human_delay_speed=2)
        await ui_test.input.emulate_mouse(MouseEventType.RIGHT_BUTTON_DOWN, start)
        await ui_test.human_delay(human_delay_speed=2)
        await ui_test.input.emulate_mouse_slow_move(start, end, num_steps=12, human_delay_speed=2)
        await ui_test.human_delay(human_delay_speed=4)

        current_camera_matrix = self.__get_camera_matrix(viewport_api)
        self.assertNotEqual(current_camera_matrix, initial_camera_matrix)
        self.assertEqual(self.__snapshot_property_models(related_models), baseline_snapshots)

        # Releasing RMB ends the camera interaction and should flush the deferred Properties refresh.
        await ui_test.input.emulate_mouse(MouseEventType.RIGHT_BUTTON_UP, end)
        await ui_test.human_delay(human_delay_speed=6)

        post_drag_snapshots = await self.__wait_for_property_models_to_change(related_models, baseline_snapshots)
        self.assertNotEqual(post_drag_snapshots, baseline_snapshots)

    async def test_camera_mouse_wheel_updates_property_ui_after_scroll(self):
        viewport_widget = _get_viewport_instance("")
        self.assertIsNotNone(viewport_widget)
        viewport_api = viewport_widget.viewport_api
        camera_path = viewport_api.camera_path.pathString
        viewport_ref = ui_test.find(f"{_WindowNames.VIEWPORT}//Frame/**/.identifier == 'viewport'")
        self.assertIsNotNone(viewport_ref)

        await self.__open_camera_properties(camera_path)
        related_models = self.__property_models_for_paths({camera_path})
        self.assertTrue(related_models)
        baseline_snapshots = self.__snapshot_property_models(related_models)
        initial_camera_matrix = self.__get_camera_matrix(viewport_api)

        # Wheel zoom is discrete, not a held interaction, so Properties should refresh after the scroll settles.
        await ui_test.input.emulate_mouse_move(viewport_ref.center)
        await ui_test.emulate_mouse_click()
        await ui_test.input.emulate_mouse_scroll(Vec2(0, -1200))

        for _ in range(60):
            current_camera_matrix = self.__get_camera_matrix(viewport_api)
            current_snapshots = self.__snapshot_property_models(related_models)
            if current_camera_matrix != initial_camera_matrix and current_snapshots != baseline_snapshots:
                break
            await self.__wait_n_updates(1)
        else:
            self.fail("Camera properties did not refresh after mouse-wheel zoom")

        self.assertNotEqual(self.__get_camera_matrix(viewport_api), initial_camera_matrix)
        stable_snapshots = self.__snapshot_property_models(related_models)
        await self.__wait_n_updates(12)
        self.assertEqual(self.__snapshot_property_models(related_models), stable_snapshots)
