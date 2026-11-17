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

import math

import carb.settings
import omni.kit.commands
import omni.ui as ui
import omni.usd
from carb.input import MouseEventType
from lightspeed.trex.viewports.shared.widget.layers import ViewportLayers
from lightspeed.ui_scene.light_manipulator.layer import (
    SETTING_LIGHT_INTENSITY_CONTROLS_VISIBLE,
    SETTING_LIGHT_MANIPULATOR_VISIBLE,
    SETTING_MANIPULATOR_SCALE,
    SETTING_SPOTLIGHT_CONE_SIDES,
    SETTING_SPOTLIGHT_CONE_VISIBLE,
    LightManipulatorLayer,
)
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.ui_test import Vec2
from omni.ui import scene as sc
from pxr import Gf, UsdGeom, UsdLux

_CAMERA_PATH = "/Camera"
_CAMERA_POSITION = (16, 12, 20)


class TestLightManipulatorViewport(AsyncTestCase):
    """Exercise light handles and spotlight cones in a real viewport."""

    async def setUp(self):
        """Create a real viewport with visible light controls and a fixed camera."""
        self._settings = carb.settings.get_settings()
        values = {
            SETTING_LIGHT_INTENSITY_CONTROLS_VISIBLE: True,
            SETTING_LIGHT_MANIPULATOR_VISIBLE: True,
            SETTING_MANIPULATOR_SCALE: 1.0,
            SETTING_SPOTLIGHT_CONE_SIDES: 6,
            SETTING_SPOTLIGHT_CONE_VISIBLE: True,
        }
        self._old_settings = {path: self._settings.get(path) for path in values}
        for path, value in values.items():
            self._settings.set(path, value)
        self._context = omni.usd.get_context()
        if self._context.can_close_stage():
            await self._context.close_stage_async()
        self._window = ui.Window("LightManipulatorTest", width=640, height=520, position_x=0, position_y=0)
        with self._window.frame:
            with ui.ZStack():
                self._viewport_layers = ViewportLayers("LightManipulatorTest")
                self._layer = LightManipulatorLayer(
                    {"viewport_api": self._viewport_layers.viewport_api, "layer_provider": self._viewport_layers}
                )
        await self._context.new_stage_async()
        stage = self._context.get_stage()
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        camera = UsdGeom.Camera.Define(stage, _CAMERA_PATH)
        camera.AddTransformOp().Set(
            Gf.Matrix4d().SetLookAt(Gf.Vec3d(*_CAMERA_POSITION), Gf.Vec3d(0, 0, -2), Gf.Vec3d(0, 1, 0)).GetInverse()
        )
        camera.CreateFocalLengthAttr(20)
        self._viewport_layers.viewport_api.camera_path = camera.GetPath()

    async def tearDown(self):
        """Release the viewport and restore the application settings."""
        for widget in (self._layer, self._viewport_layers, self._window):
            widget.destroy()
        self._layer = self._viewport_layers = self._window = None
        await self._context.close_stage_async()
        for path, value in self._old_settings.items():
            if value is None:
                self._settings.destroy_item(path)
            else:
                self._settings.set(path, value)

    async def __select_light(self, schema, intensity, angle=None):
        stage = self._context.get_stage()
        path = f"/{schema.__name__}"
        light = schema.Define(stage, path)
        light.CreateIntensityAttr(intensity)
        if schema is UsdLux.DistantLight:
            light.AddTranslateOp().Set(Gf.Vec3d(0, -4, 0))
        if schema is UsdLux.RectLight:
            light.CreateWidthAttr(3)
            light.CreateHeightAttr(2)
        elif schema is not UsdLux.DistantLight:
            light.CreateRadiusAttr(1.5)
            if schema is UsdLux.CylinderLight:
                light.CreateLengthAttr(3)
        if angle is not None:
            shaping = UsdLux.ShapingAPI.Apply(light.GetPrim())
            shaping.CreateShapingConeAngleAttr(angle)
            shaping.CreateShapingConeSoftnessAttr(0)
        await self.__wait_for(lambda: path in self._layer.manipulators)
        self._context.get_selection().set_selected_prim_paths([path], False)
        manipulator = self._layer.manipulators[path]
        await self.__wait_for(lambda: manipulator._intensity_arrows is not None)
        self._viewport_layers.viewport_api.camera_path = _CAMERA_PATH
        await self.__wait_for(
            lambda: Gf.IsClose(
                self._viewport_layers.viewport_api.transform.ExtractTranslation(), Gf.Vec3d(*_CAMERA_POSITION), 1e-5
            )
        )
        return light, manipulator

    async def __wait_for(self, condition):
        for _ in range(120):
            if condition():
                return
            await ui_test.human_delay()
        self.fail("The viewport did not reach the expected state")

    def __screen_point(self, item, point):
        ndc = item.transform_space(sc.Space.OBJECT, sc.Space.NDC, point)
        view = self._layer._scene_view
        return Vec2(
            view.screen_position_x + (ndc[0] + 1) * view.computed_width * 0.5,
            view.screen_position_y + (1 - ndc[1]) * view.computed_height * 0.5,
        )

    async def __drag(self, start, end):
        await ui_test.input.emulate_mouse_move(start)
        await ui_test.human_delay()
        await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN, start)
        await ui_test.human_delay()
        await ui_test.input.emulate_mouse_slow_move(start, end, num_steps=12)
        await ui_test.human_delay()
        await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_UP, end)
        await ui_test.human_delay()

    async def test_edit_lights_updates_intensity_dimensions_and_spotlight_cones(self):
        """Change light attributes and cone display through one real viewport."""
        # Select each light type. Its dimensions and active intensity handles must match the USD fixture.
        cases = (
            (UsdLux.DiskLight, 500, 4, (1.5, 1.5, 3.7)),
            (UsdLux.DistantLight, 25, 1, (5, 5, 3.7)),
            (UsdLux.RectLight, 400, 4, (3, 2, 3.7)),
            (UsdLux.SphereLight, 100, 6, (1.5, 1.5, 1.5)),
            (UsdLux.CylinderLight, 140, 6, (3, 1.5, 1.5)),
        )
        for schema, intensity, arrow_count, dimensions in cases:
            with self.subTest(light_type=schema.__name__):
                self._settings.set(SETTING_LIGHT_INTENSITY_CONTROLS_VISIBLE, True)
                light, manipulator = await self.__select_light(schema, intensity)
                self.assertTrue(manipulator.shape_xform.compute_visibility())
                for axis, expected in zip((0, 5, 10), dimensions):
                    self.assertAlmostEqual(manipulator.shape_xform.transform[axis], expected, places=4)
                arrows = manipulator._intensity_arrows
                self.assertEqual(len(arrows.shapes), arrow_count)
                self.assertEqual(len(arrows.arrows_group), arrow_count)
                self.assertTrue(all(shaft.compute_visibility() and shaft.gestures for shaft in arrows.shapes))
                for shaft in arrows.shapes:
                    self.assertTrue(Gf.IsClose(Gf.Vec4f(shaft.color), Gf.Vec4f(1, 1, 0, 1), 1e-5))

                # Hover over an intensity shaft. Its arrowheads must become visible with the active color.
                shaft = arrows.shapes[0]
                midpoint = tuple(a * 0.25 + b * 0.75 for a, b in zip(shaft.start, shaft.end))
                start = self.__screen_point(shaft, midpoint)
                end = self.__screen_point(shaft, (midpoint[0], midpoint[1], midpoint[2] - 0.7))
                await ui_test.input.emulate_mouse_move(start)
                await ui_test.human_delay()
                self.assertTrue(all(head.compute_visibility() for head in arrows.arrows_group))
                for head in arrows.arrows_group:
                    self.assertTrue(
                        all(Gf.IsClose(Gf.Vec4f(color), Gf.Vec4f(1, 1, 0, 1), 1e-5) for color in head.colors)
                    )
                # Drag the active intensity handle. The light's USD intensity must change.
                before = light.GetIntensityAttr().Get()
                await self.__drag(start, end)
                self.assertNotAlmostEqual(light.GetIntensityAttr().Get(), before)

                # Disable intensity controls. Passive handles must reject the same drag without a USD change.
                self._settings.set(SETTING_LIGHT_INTENSITY_CONTROLS_VISIBLE, False)
                await ui_test.human_delay()
                passive = manipulator._intensity_arrows
                if schema in (UsdLux.DiskLight, UsdLux.DistantLight, UsdLux.RectLight):
                    self.assertIsNotNone(passive)
                    self.assertEqual(len(passive.shapes), 1)
                    self.assertTrue(passive.arrows_group[0].compute_visibility())
                    self.assertFalse(passive.shapes[0].gestures)
                else:
                    self.assertIsNone(passive)
                before = light.GetIntensityAttr().Get()
                await self.__drag(start, end)
                self.assertEqual(light.GetIntensityAttr().Get(), before)

                # Drag a dimension handle. The corresponding USD width or radius must change.
                if schema is not UsdLux.DistantLight:
                    attribute = light.GetWidthAttr() if schema is UsdLux.RectLight else light.GetRadiusAttr()
                    point, target = {
                        UsdLux.RectLight: ((0.5, 0, 0), (0.9, 0, 0)),
                        UsdLux.CylinderLight: ((0.5, 0.7071, 0.7071), (0.5, 0.7071, 1.1)),
                    }.get(schema, ((0.7071, 0.7071, 0), (1.1, 0.7071, 0)))
                    before = attribute.Get()
                    await self.__drag(
                        self.__screen_point(manipulator.shape_xform, point),
                        self.__screen_point(manipulator.shape_xform, target),
                    )
                    self.assertNotAlmostEqual(attribute.Get(), before)
                # Rotate the light through USD. The manipulator must follow its world transform.
                light.AddRotateXYZOp().Set(Gf.Vec3f(30, 20 if schema is UsdLux.DistantLight else 45, 0))
                await ui_test.human_delay()
                expected = light.ComputeLocalToWorldTransform(0)
                root = manipulator._AbstractLightManipulator__root_xf
                for point in ((0, 0, 0), (1, 0, 0), (0, 1, 0)):
                    actual = root.transform_space(sc.Space.OBJECT, sc.Space.WORLD, point)
                    self.assertTrue(Gf.IsClose(Gf.Vec3d(actual), expected.Transform(Gf.Vec3d(point)), 1e-5))

                # Remove the light so the next case starts without a selected fixture.
                self._context.get_selection().set_selected_prim_paths([], False)
                self._context.get_stage().RemovePrim(light.GetPath())
                await ui_test.human_delay()

        self._settings.set(SETTING_LIGHT_INTENSITY_CONTROLS_VISIBLE, True)
        await ui_test.human_delay()
        # Select shaped disk and sphere lights. Each must display its outer cone with the authored angle.
        for schema, angle in ((UsdLux.DiskLight, 30), (UsdLux.SphereLight, 45)):
            with self.subTest(light_type=schema.__name__):
                light, manipulator = await self.__select_light(schema, 2, angle=angle)
                shaping = UsdLux.ShapingAPI(light.GetPrim())
                self.assertIsNotNone(manipulator._cone_xform)
                self.assertTrue(manipulator._cone_xform.compute_visibility())
                self.assertEqual(len(manipulator._cone_lines), 6)
                self.assertEqual(len(manipulator._cone_arcs), 2)
                line = manipulator._cone_lines[0]
                length = -line.end[2]
                self.assertGreater(length, 0)
                self.assertAlmostEqual(line.start[0], 1.5)
                self.assertAlmostEqual(line.end[0], 1.5 + length * math.tan(math.radians(angle)), places=4)
                self.assertAlmostEqual(manipulator._cone_arcs[-1].radius, line.end[0], places=4)
                self.assertTrue(Gf.IsClose(Gf.Vec4f(line.color), Gf.Vec4f(0, 1, 0, 1), 1e-5))
                self.assertTrue(
                    all(item.compute_visibility() for item in manipulator._cone_lines + manipulator._cone_arcs)
                )

                # Change the cone angle and softness. The inner cone must be narrower and use its own color.
                for attribute, value in (
                    (shaping.GetShapingConeAngleAttr(), 45.0),
                    (shaping.GetShapingConeSoftnessAttr(), 0.2),
                ):
                    omni.kit.commands.execute(
                        "ChangeProperty", prop_path=attribute.GetPath(), value=value, prev=attribute.Get()
                    )
                    await ui_test.human_delay()
                self.assertEqual(len(manipulator._cone_lines), 12)
                self.assertEqual(len(manipulator._cone_arcs), 3)
                inner = manipulator._cone_lines[6]
                inner_angle = math.acos(min(1, math.cos(math.radians(45)) + 0.2))
                length = -inner.end[2]
                self.assertAlmostEqual(inner.end[0], 1.5 + length * math.tan(inner_angle), places=4)
                self.assertLess(inner.end[0], manipulator._cone_lines[0].end[0])
                self.assertTrue(Gf.IsClose(Gf.Vec4f(inner.color), Gf.Vec4f(0, 1, 1, 1), 1e-5))

                # Toggle cone visibility. The cone must disappear without hiding the light's shape.
                for visible in (False, True):
                    self._settings.set(SETTING_SPOTLIGHT_CONE_VISIBLE, visible)
                    await self.__wait_for(
                        lambda manipulator=manipulator, visible=visible: (
                            (manipulator._cone_xform is not None) == visible
                        )
                    )
                    self.assertTrue(manipulator.shape_xform.compute_visibility())
                    if visible:
                        self.assertTrue(manipulator._cone_xform.compute_visibility())
                    else:
                        self.assertEqual((manipulator._cone_lines, manipulator._cone_arcs), ([], []))
                self._context.get_selection().set_selected_prim_paths([], False)
                self._context.get_stage().RemovePrim(light.GetPath())
                await ui_test.human_delay()
