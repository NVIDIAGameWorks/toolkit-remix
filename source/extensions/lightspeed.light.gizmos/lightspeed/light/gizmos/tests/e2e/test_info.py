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

__all__ = ["TestLightGizmosViewport"]

from dataclasses import dataclass

import omni.ui as ui
import omni.usd
from lightspeed.light.gizmos.layer import LightGizmosLayer
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.ui_test import Vec2
from omni.kit.widget.viewport import ViewportWidget
from omni.ui import scene as sc
from pxr import Gf, UsdGeom, UsdLux

_READINESS_ATTEMPTS = 120
_NUMERIC_TOLERANCE = 1e-5


@dataclass(frozen=True)
class _LightCase:
    """Define a light fixture and its expected icon geometry."""

    schema: type
    position_x: float
    polygons: tuple[int, ...]
    fill_vertices: int


class TestLightGizmosViewport(AsyncTestCase):
    """Exercise light icons through a real viewport."""

    async def setUp(self):
        """Create the viewport and open a stage for lights."""
        self._context = omni.usd.get_context()
        if self._context.can_close_stage():
            await self._context.close_stage_async()
        self._window = ui.Window("LightGizmosTest", width=640, height=440, position_x=0, position_y=0)
        with self._window.frame, ui.ZStack():
            self._viewport = ViewportWidget(hd_engine="pxr", resolution=(640, 400), identifier="viewport")
            self._layer = LightGizmosLayer({"viewport_api": self._viewport.viewport_api})
        await self._context.new_stage_async()
        stage = self._context.get_stage()
        camera = UsdGeom.Camera.Define(stage, "/Camera")
        camera.CreateProjectionAttr(UsdGeom.Tokens.orthographic)
        camera.CreateHorizontalApertureAttr(1600)
        camera.CreateVerticalApertureAttr(1000)
        camera.CreateClippingRangeAttr(Gf.Vec2f(0.1, 1000))
        camera.AddTranslateOp().Set(Gf.Vec3d(0, 0, 100))
        self._viewport.viewport_api.camera_path = camera.GetPath()
        UsdGeom.Xform.Define(stage, "/Lights")

    async def tearDown(self):
        """Close the stage and release the viewport."""
        await self._context.close_stage_async()
        self._layer.destroy()
        self._viewport.destroy()
        self._window.destroy()
        self._layer = self._viewport = self._window = None

    def __screen_point(self, item, point=(0, 0, 0)):
        api = self._viewport.viewport_api
        pixel, viewport = api.map_ndc_to_texture_pixel(item.transform_space(sc.Space.OBJECT, sc.Space.NDC, point))
        self.assertIsNotNone(viewport)
        frame = ui_test.find(f"{self._window.title}//Frame/**/Frame[*].identifier=='viewport'").widget
        return Vec2(
            frame.screen_position_x + pixel[0] * frame.computed_width / api.resolution[0],
            frame.screen_position_y + pixel[1] * frame.computed_height / api.resolution[1],
        )

    async def test_click_light_types_selects_visible_billboard_icons(self):
        """Select each light type through its displayed icon."""
        # Create one fixture per light type. Each fixture must produce the expected icon geometry.
        stage = self._context.get_stage()
        cases = (
            _LightCase(UsdLux.SphereLight, 0, (4,) * 8 + (10,), 10),
            _LightCase(UsdLux.RectLight, 32, (4,) * 5, 4),
            _LightCase(UsdLux.DistantLight, 64, (4,) * 12, 0),
            _LightCase(UsdLux.DiskLight, -32, (4, 4, 4, 6), 6),
            _LightCase(UsdLux.CylinderLight, -64, (4,) * 7, 4),
        )
        for case in cases:
            case.schema.Define(stage, f"/Lights/{case.schema.__name__}").AddTranslateOp().Set(
                Gf.Vec3d(case.position_x, 0, 0)
            )
        for _ in range(_READINESS_ATTEMPTS):
            if len(self._layer._manipulators) == len(cases) and all(
                manipulator._icon_mesh is not None for manipulator in self._layer._manipulators.values()
            ):
                break
            await ui_test.human_delay()
        self.assertEqual(len(self._layer._manipulators), len(cases))
        self._layer.gizmo_scale = 1.0
        for _ in range(_READINESS_ATTEMPTS):
            if self._viewport.viewport_api.transform.ExtractTranslation() == Gf.Vec3d(0, 0, 100):
                break
            await self._viewport.viewport_api.wait_for_rendered_frames(2)
        self.assertEqual(self._viewport.viewport_api.transform.ExtractTranslation(), Gf.Vec3d(0, 0, 100))

        # Check each billboard's geometry and screen size before a click selects its light.
        for case in cases:
            with self.subTest(light_type=case.schema.__name__):
                path = f"/Lights/{case.schema.__name__}"
                manipulator = self._layer._manipulators[path]
                mesh = manipulator._icon_mesh
                self.assertIsNotNone(mesh)
                self.assertTrue(mesh.compute_visibility())
                vertices = sum(case.polygons)
                self.assertEqual(len(mesh.positions), vertices)
                self.assertEqual(list(mesh.vertex_counts), list(case.polygons))
                self.assertEqual(list(mesh.vertex_indices), list(range(vertices)))
                self.assertEqual(manipulator._billboard.look_at, sc.Transform.LookAt.CAMERA)
                self.assertEqual(manipulator._billboard.scale_to, sc.Space.SCREEN)
                self.assertEqual(len(mesh.colors), vertices)
                for index, color in enumerate(mesh.colors):
                    expected = (1, 0.8, 0.2, 1) if index < vertices - case.fill_vertices else (1, 0.9, 0.5, 0.9)
                    self.assertTrue(Gf.IsClose(Gf.Vec4d(*color), Gf.Vec4d(*expected), _NUMERIC_TOLERANCE))
                position = manipulator._root.transform_space(sc.Space.OBJECT, sc.Space.WORLD, (0, 0, 0))
                self.assertTrue(Gf.IsClose(Gf.Vec3d(*position), Gf.Vec3d(case.position_x, 0, 0), _NUMERIC_TOLERANCE))
                origin = self.__screen_point(mesh)
                edge = self.__screen_point(mesh, (1, 0, 0))
                self.assertAlmostEqual(abs(edge.x - origin.x), 32, delta=1)

                # Click the displayed icon. The USD selection must contain only its light.
                await ui_test.input.emulate_mouse_move_and_click(origin)
                await ui_test.human_delay()
                self.assertEqual(self._context.get_selection().get_selected_prim_paths(), [path])

        # Hide and show the layer. Only visible icons must accept a selection click.
        for visible, selected_paths in ((False, []), (True, [path])):
            with self.subTest(visible=visible):
                self._layer.visible = visible
                self._context.get_selection().set_selected_prim_paths([], False)
                await ui_test.human_delay()
                await ui_test.input.emulate_mouse_move_and_click(origin)
                await ui_test.human_delay()
                self.assertEqual(self._layer.visible, visible)
                self.assertEqual(self._context.get_selection().get_selected_prim_paths(), selected_paths)
