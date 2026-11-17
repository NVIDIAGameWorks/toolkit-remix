"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["TestParticleGizmosViewport"]

import carb.settings
import omni.ui as ui
import omni.usd
from lightspeed.common.constants import PARTICLE_SCHEMA_NAME
from lightspeed.particle.gizmos.layer import (
    CARB_SETTING_CONST_SCALE_ENABLED,
    CARB_SETTING_GIZMO_SCALE,
    SETTING_PARTICLE_GIZMO_VISIBLE,
    ParticleGizmosLayer,
)
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.ui_test import Vec2
from omni.kit.widget.viewport import ViewportWidget
from omni.ui import scene as sc
from pxr import Gf, UsdGeom

_SELECTED_ICON_COLOR = (1, 0, 0, 1)
_UNSELECTED_ICON_COLOR = (0.0859, 0.8945, 0.7148, 1)


class TestParticleGizmosViewport(AsyncTestCase):
    """Exercise particle icons through a real viewport."""

    async def setUp(self):
        """Create the viewport and open a stage for particle emitters."""
        self._settings = carb.settings.get_settings()
        values = {
            SETTING_PARTICLE_GIZMO_VISIBLE: True,
            CARB_SETTING_GIZMO_SCALE: 1.0,
            CARB_SETTING_CONST_SCALE_ENABLED: False,
        }
        self._old_settings = {path: self._settings.get(path) for path in values}
        for path, value in values.items():
            self._settings.set(path, value)
        self._context = omni.usd.get_context()
        if self._context.can_close_stage():
            await self._context.close_stage_async()
        self._window = ui.Window("ParticleGizmosTest", width=640, height=440, position_x=0, position_y=0)
        with self._window.frame, ui.ZStack():
            self._viewport = ViewportWidget(hd_engine="pxr", resolution=(640, 400), identifier="viewport")
            self._layer = ParticleGizmosLayer({"viewport_api": self._viewport.viewport_api})
        await self._context.new_stage_async()
        stage = self._context.get_stage()
        camera = UsdGeom.Camera.Define(stage, "/Camera")
        camera.CreateProjectionAttr(UsdGeom.Tokens.orthographic)
        camera.CreateHorizontalApertureAttr(1600)
        camera.CreateVerticalApertureAttr(1000)
        camera.CreateClippingRangeAttr(Gf.Vec2f(0.1, 1000))
        camera.AddTranslateOp().Set(Gf.Vec3d(0, 0, 100))
        self._viewport.viewport_api.camera_path = camera.GetPath()

    async def tearDown(self):
        """Close the stage and release the viewport."""
        await self._context.close_stage_async()
        for widget in (self._layer, self._viewport, self._window):
            widget.destroy()
        self._layer = self._viewport = self._window = None
        for path, value in self._old_settings.items():
            if value is None:
                self._settings.destroy_item(path)
            else:
                self._settings.set(path, value)

    def __screen_point(self, item, point=(0, 0, 0)):
        ndc = item.transform_space(sc.Space.OBJECT, sc.Space.NDC, point)
        api = self._viewport.viewport_api
        pixel, _ = api.map_ndc_to_texture_pixel(ndc)
        frame = ui_test.find(f"{self._window.title}//Frame/**/Frame[*].identifier=='viewport'").widget
        return Vec2(
            frame.screen_position_x + pixel[0] * frame.computed_width / api.resolution[0],
            frame.screen_position_y + pixel[1] * frame.computed_height / api.resolution[1],
        )

    def __assert_icon_color(self, mesh, expected):
        self.assertTrue(mesh.colors)
        for color in mesh.colors:
            self.assertTrue(Gf.IsClose(Gf.Vec4d(*color), Gf.Vec4d(*expected), 0.00005))

    async def test_click_transformed_emitters_updates_billboard_selection_color(self):
        """Select transformed emitters through their displayed icons."""
        # Create transformed emitters. Their icons must retain screen size and face the camera.
        stage = self._context.get_stage()
        for index in range(5):
            mesh = UsdGeom.Mesh.Define(stage, f"/Particles/Emitter{index}")
            self.assertTrue(mesh.GetPrim().ApplyAPI(PARTICLE_SCHEMA_NAME))
            mesh.CreatePointsAttr([(-1, -1, 0), (1, -1, 0), (0, 1, 0)])
            mesh.CreateFaceVertexCountsAttr([3])
            mesh.CreateFaceVertexIndicesAttr([0, 1, 2])
            mesh.AddTranslateOp().Set(Gf.Vec3d((index - 2) * 32, 0, 0))
            mesh.AddRotateXYZOp().Set(Gf.Vec3f(index * 15, index * 20, index * 10))
            mesh.AddScaleOp().Set(Gf.Vec3f(index + 1))
        for _ in range(120):
            if (
                len(self._layer._manipulators) == 5
                and all(manipulator._icon_mesh is not None for manipulator in self._layer._manipulators.values())
                and self._viewport.viewport_api.transform.ExtractTranslation() == Gf.Vec3d(0, 0, 100)
            ):
                break
            await self._viewport.viewport_api.wait_for_rendered_frames(2)
        self.assertEqual(len(self._layer._manipulators), 5)
        self.assertEqual(self._viewport.viewport_api.transform.ExtractTranslation(), Gf.Vec3d(0, 0, 100))

        # Check each unselected icon before a click changes its USD selection and color.
        for index in range(5):
            with self.subTest(emitter=index):
                path = f"/Particles/Emitter{index}"
                manipulator = self._layer._manipulators[path]
                mesh = manipulator._icon_mesh
                self.assertTrue(mesh.compute_visibility())
                self.assertEqual((len(mesh.positions), len(mesh.vertex_counts)), (140, 41))
                self.assertEqual(sum(mesh.vertex_counts), len(mesh.vertex_indices))
                self.__assert_icon_color(mesh, _UNSELECTED_ICON_COLOR)
                self.assertEqual(manipulator._billboard.look_at, sc.Transform.LookAt.CAMERA)
                self.assertEqual(manipulator._billboard.scale_to, sc.Space.SCREEN)
                position = manipulator._gizmo_root.transform_space(sc.Space.OBJECT, sc.Space.WORLD, (0, 0, 0))
                self.assertAlmostEqual(position[0], (index - 2) * 32)
                origin = self.__screen_point(mesh)
                edge = self.__screen_point(mesh, (1, 0, 0))
                self.assertAlmostEqual(abs(edge.x - origin.x), 32, delta=1)

                await ui_test.input.emulate_mouse_move_and_click(origin)
                await ui_test.human_delay()
                self.assertEqual(self._context.get_selection().get_selected_prim_paths(), [path])
                self.__assert_icon_color(manipulator._icon_mesh, _SELECTED_ICON_COLOR)

                # Clear the selection. The icon must return to its unselected color.
                self._context.get_selection().set_selected_prim_paths([], False)
                await ui_test.human_delay()
                self.__assert_icon_color(manipulator._icon_mesh, _UNSELECTED_ICON_COLOR)

        # Toggle the application setting. Hidden icons must reject clicks, and visible icons must accept them.
        for visible, selected in ((False, []), (True, [path])):
            with self.subTest(visible=visible):
                self._settings.set(SETTING_PARTICLE_GIZMO_VISIBLE, visible)
                await ui_test.human_delay()
                await ui_test.input.emulate_mouse_move_and_click(origin)
                await ui_test.human_delay()
                self.assertEqual(self._layer._scene_view.visible, visible)
                self.assertEqual(self._context.get_selection().get_selected_prim_paths(), selected)
                self.__assert_icon_color(
                    manipulator._icon_mesh, _SELECTED_ICON_COLOR if visible else _UNSELECTED_ICON_COLOR
                )
