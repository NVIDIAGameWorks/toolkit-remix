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

import carb
import omni.kit.test
import omni.usd
from omni.flux.utils.common.interactive_usd_notices import begin_interaction as _begin_interaction
from omni.flux.utils.common.interactive_usd_notices import end_interaction as _end_interaction
from lightspeed.ui_scene.light_manipulator.constants import (
    CONE_SIDES_MIN_INPUT,
    CONE_THRESHOLD_DEFAULT,
    CONE_THRESHOLD_MIN,
)
from lightspeed.ui_scene.light_manipulator.layer import (
    SETTING_LIGHT_INTENSITY_CONTROLS_VISIBLE,
    SETTING_LIGHT_MANIPULATOR_VISIBLE,
    SETTING_SPOTLIGHT_CONE_ILLUMINANCE_THRESHOLD,
    SETTING_SPOTLIGHT_CONE_VISIBLE,
    LightManipulatorLayer,
)
from omni.kit.widget.viewport.api import ViewportAPI
from omni.ui.tests.test_base import OmniUiTest
from pxr import Tf, Usd, UsdLux


class TestLightLayer(OmniUiTest):
    # Before running each test
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.stage: Usd.Stage = omni.usd.get_context().get_stage()

    # After running each test
    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()

    async def test_layer_create_manipulators(self):
        vp_api = ViewportAPI("", 0, lambda: 0)
        layer = LightManipulatorLayer({"viewport_api": vp_api})

        # create a few lights
        lights = ["DiskLight", "RectLight", "RectLight"]
        for i, light_type in enumerate(lights):
            light = self.stage.DefinePrim(f"/TestLight{i}")
            light.SetTypeName(light_type)

        # simulate a hierarchy change
        class MockEvent:
            type = omni.usd.StageEventType.HIERARCHY_CHANGED.value

        # trigger change
        layer._on_stage_event(MockEvent())

        # make sure a manipulator object was created for each light in the stage
        self.assertEqual(len(layer.manipulators), len(lights))

        # make sure we can destroy layer properly
        layer.destroy()

    async def test_layer_uses_default_visible_setting(self):
        vp_api = ViewportAPI("", 0, lambda: 0)
        settings = carb.settings.get_settings()
        settings.destroy_item(SETTING_LIGHT_MANIPULATOR_VISIBLE)

        layer = LightManipulatorLayer({"viewport_api": vp_api})

        self.assertTrue(layer.visible)

        layer.destroy()
        settings.destroy_item(SETTING_LIGHT_MANIPULATOR_VISIBLE)

    async def test_layer_visibility_tracks_setting_changes(self):
        vp_api = ViewportAPI("", 0, lambda: 0)
        settings = carb.settings.get_settings()
        layer = LightManipulatorLayer({"viewport_api": vp_api})

        settings.set(SETTING_LIGHT_MANIPULATOR_VISIBLE, False)
        layer._light_manipulator_setting_change(None, carb.settings.ChangeEventType.CHANGED)
        self.assertFalse(layer.visible)

        settings.set(SETTING_LIGHT_MANIPULATOR_VISIBLE, True)
        layer._light_manipulator_setting_change(None, carb.settings.ChangeEventType.CHANGED)
        self.assertTrue(layer.visible)

        layer.destroy()

    async def test_layer_uses_default_intensity_controls_setting(self):
        vp_api = ViewportAPI("", 0, lambda: 0)
        settings = carb.settings.get_settings()
        settings.destroy_item(SETTING_LIGHT_INTENSITY_CONTROLS_VISIBLE)

        layer = LightManipulatorLayer({"viewport_api": vp_api})

        self.assertFalse(layer.intensity_controls_visible)

        layer.destroy()
        settings.destroy_item(SETTING_LIGHT_INTENSITY_CONTROLS_VISIBLE)

    async def test_layer_intensity_controls_tracks_setting_changes(self):
        vp_api = ViewportAPI("", 0, lambda: 0)
        settings = carb.settings.get_settings()
        layer = LightManipulatorLayer({"viewport_api": vp_api})

        settings.set(SETTING_LIGHT_INTENSITY_CONTROLS_VISIBLE, False)
        layer._light_manipulator_setting_change(None, carb.settings.ChangeEventType.CHANGED)
        self.assertFalse(layer.intensity_controls_visible)

        settings.set(SETTING_LIGHT_INTENSITY_CONTROLS_VISIBLE, True)
        layer._light_manipulator_setting_change(None, carb.settings.ChangeEventType.CHANGED)
        self.assertTrue(layer.intensity_controls_visible)

        layer.destroy()

    async def test_spotlight_cone_toggle_propagates(self):
        """`spotlightConeVisible` updates propagate to every manipulator."""
        settings = carb.settings.get_settings()
        original = settings.get(SETTING_SPOTLIGHT_CONE_VISIBLE)
        try:
            vp_api = ViewportAPI("", 0, lambda: 0)
            layer = LightManipulatorLayer({"viewport_api": vp_api})

            for i, light_type in enumerate(["DiskLight", "SphereLight"]):
                light = self.stage.DefinePrim(f"/SpotTest{i}")
                light.SetTypeName(light_type)

            class MockEvent:
                type = omni.usd.StageEventType.HIERARCHY_CHANGED.value

            layer._on_stage_event(MockEvent())
            self.assertEqual(len(layer.manipulators), 2)

            settings.set(SETTING_SPOTLIGHT_CONE_VISIBLE, False)
            self.assertFalse(layer._cone_visible)
            for manipulator in layer.manipulators.values():
                self.assertFalse(manipulator.cone_visible)

            settings.set(SETTING_SPOTLIGHT_CONE_VISIBLE, True)
            self.assertTrue(layer._cone_visible)
            for manipulator in layer.manipulators.values():
                self.assertTrue(manipulator.cone_visible)

            layer.destroy()
        finally:
            # Restore the setting so other tests aren't affected by our toggling.
            if original is None:
                settings.set(SETTING_SPOTLIGHT_CONE_VISIBLE, True)
            else:
                settings.set(SETTING_SPOTLIGHT_CONE_VISIBLE, original)

    async def test_spotlight_cone_threshold_propagates(self):
        """`spotlightConeIlluminanceThreshold` updates propagate to every manipulator and clamp at the floor."""
        settings = carb.settings.get_settings()
        original = settings.get(SETTING_SPOTLIGHT_CONE_ILLUMINANCE_THRESHOLD)
        try:
            vp_api = ViewportAPI("", 0, lambda: 0)
            layer = LightManipulatorLayer({"viewport_api": vp_api})

            for i, light_type in enumerate(["DiskLight", "SphereLight"]):
                light = self.stage.DefinePrim(f"/ThreshTest{i}")
                light.SetTypeName(light_type)

            class MockEvent:
                type = omni.usd.StageEventType.HIERARCHY_CHANGED.value

            layer._on_stage_event(MockEvent())
            self.assertEqual(len(layer.manipulators), 2)

            # A positive override propagates unchanged.
            settings.set(SETTING_SPOTLIGHT_CONE_ILLUMINANCE_THRESHOLD, 7.5)
            self.assertAlmostEqual(layer._cone_threshold, 7.5)
            for manipulator in layer.manipulators.values():
                self.assertAlmostEqual(manipulator.cone_threshold, 7.5)

            # A zero/negative override is clamped to the tiny positive floor so the cone
            # formula doesn't divide by zero (a 0-threshold would mean "infinite reach").
            settings.set(SETTING_SPOTLIGHT_CONE_ILLUMINANCE_THRESHOLD, 0.0)
            self.assertAlmostEqual(layer._cone_threshold, CONE_THRESHOLD_MIN)
            for manipulator in layer.manipulators.values():
                self.assertAlmostEqual(manipulator.cone_threshold, CONE_THRESHOLD_MIN)

            layer.destroy()
        finally:
            if original is None:
                settings.set(SETTING_SPOTLIGHT_CONE_ILLUMINANCE_THRESHOLD, 10.0)
            else:
                settings.set(SETTING_SPOTLIGHT_CONE_ILLUMINANCE_THRESHOLD, original)

    async def test_spotlight_cone_color_requires_three_components(self):
        """Cone color setters reject malformed RGB tuples before geometry rebuild."""
        vp_api = ViewportAPI("", 0, lambda: 0)
        layer = LightManipulatorLayer({"viewport_api": vp_api})
        try:
            light = self.stage.DefinePrim("/ColorValidationDisk")
            light.SetTypeName("DiskLight")

            class MockEvent:
                type = omni.usd.StageEventType.HIERARCHY_CHANGED.value

            layer._on_stage_event(MockEvent())
            manipulator = layer.manipulators["/ColorValidationDisk"]

            for value in ((1.0, 0.0), (1.0, 0.0, 0.0, 1.0)):
                with self.assertRaisesRegex(ValueError, "cone_outer_color requires exactly 3 components"):
                    manipulator.cone_outer_color = value
                with self.assertRaisesRegex(ValueError, "cone_inner_color requires exactly 3 components"):
                    manipulator.cone_inner_color = value
        finally:
            layer.destroy()

    async def test_spotlight_cone_sides_clamps_to_ui_floor(self):
        """Direct manipulator updates use the same subdivision floor as settings and menu controls."""
        vp_api = ViewportAPI("", 0, lambda: 0)
        layer = LightManipulatorLayer({"viewport_api": vp_api})
        try:
            light = self.stage.DefinePrim("/ConeSidesDisk")
            light.SetTypeName("DiskLight")

            class MockEvent:
                type = omni.usd.StageEventType.HIERARCHY_CHANGED.value

            layer._on_stage_event(MockEvent())
            manipulator = layer.manipulators["/ConeSidesDisk"]

            manipulator.cone_sides = 2

            self.assertEqual(manipulator.cone_sides, CONE_SIDES_MIN_INPUT)
        finally:
            layer.destroy()

    def _wire_model_light(self, layer, path):
        # The Tf.Notice listener is normally registered on selection; this harness never fires
        # SELECTION_CHANGED, so wire each model's _light manually so ShapingMixin reads work.
        manipulator = layer.manipulators[path]
        prim = self.stage.GetPrimAtPath(path)
        manipulator.model._light = manipulator.light_class(prim)
        return manipulator

    async def test_intensity_scale_scales_with_threshold_for_spotlight(self):
        """Spotlight (Disk + ShapingAPI) `intensity_scale` = `_base × √(T / T_default)`."""
        vp_api = ViewportAPI("", 0, lambda: 0)
        layer = LightManipulatorLayer({"viewport_api": vp_api})
        try:
            light = self.stage.DefinePrim("/ShapedDisk")
            light.SetTypeName("DiskLight")
            UsdLux.ShapingAPI.Apply(light).CreateShapingConeAngleAttr(30.0)

            class MockEvent:
                type = omni.usd.StageEventType.HIERARCHY_CHANGED.value

            layer._on_stage_event(MockEvent())
            manipulator = self._wire_model_light(layer, "/ShapedDisk")
            base = manipulator._base_intensity_scale

            manipulator.cone_threshold = CONE_THRESHOLD_DEFAULT
            self.assertAlmostEqual(manipulator.intensity_scale, base, places=6)

            manipulator.cone_threshold = 4.0 * CONE_THRESHOLD_DEFAULT
            self.assertAlmostEqual(manipulator.intensity_scale, base * 2.0, places=6)

            manipulator.cone_threshold = 0.25 * CONE_THRESHOLD_DEFAULT
            self.assertAlmostEqual(manipulator.intensity_scale, base * 0.5, places=6)
        finally:
            layer.destroy()

    async def test_spotlight_cone_capable_lights_keep_stage_unit_scale(self):
        """Disk and Sphere cone distances stay in stage units because their models are proportional."""
        vp_api = ViewportAPI("", 0, lambda: 0)
        layer = LightManipulatorLayer({"viewport_api": vp_api})
        try:
            for path, light_type in (("/ScaledDisk", "DiskLight"), ("/ScaledSphere", "SphereLight")):
                light = self.stage.DefinePrim(path)
                light.SetTypeName(light_type)

            class MockEvent:
                type = omni.usd.StageEventType.HIERARCHY_CHANGED.value

            layer._on_stage_event(MockEvent())

            for path in ("/ScaledDisk", "/ScaledSphere"):
                manipulator = self._wire_model_light(layer, path)
                manipulator.model.set_manipulator_scale(12.0)
                self.assertAlmostEqual(manipulator.model.get_as_float(manipulator.model.manipulator_scale), 1.0)
        finally:
            layer.destroy()

    async def test_intensity_scale_unchanged_without_shaping(self):
        """DiskLight without ShapingAPI returns the base scale regardless of threshold."""
        vp_api = ViewportAPI("", 0, lambda: 0)
        layer = LightManipulatorLayer({"viewport_api": vp_api})
        try:
            light = self.stage.DefinePrim("/PlainDisk")
            light.SetTypeName("DiskLight")

            class MockEvent:
                type = omni.usd.StageEventType.HIERARCHY_CHANGED.value

            layer._on_stage_event(MockEvent())
            manipulator = self._wire_model_light(layer, "/PlainDisk")
            base = manipulator._base_intensity_scale
            for threshold in (0.01, CONE_THRESHOLD_DEFAULT, 1.0, 10.0):
                manipulator.cone_threshold = threshold
                self.assertEqual(manipulator.intensity_scale, base)
        finally:
            layer.destroy()

    async def test_intensity_scale_unchanged_for_non_spotlight_light(self):
        """RectLight (`supports_spotlight_cone = False`) ignores threshold; arrow stays at base scale."""
        vp_api = ViewportAPI("", 0, lambda: 0)
        layer = LightManipulatorLayer({"viewport_api": vp_api})
        try:
            light = self.stage.DefinePrim("/ARect")
            light.SetTypeName("RectLight")

            class MockEvent:
                type = omni.usd.StageEventType.HIERARCHY_CHANGED.value

            layer._on_stage_event(MockEvent())
            manipulator = self._wire_model_light(layer, "/ARect")
            base = manipulator._base_intensity_scale
            manipulator.cone_threshold = 5.0 * CONE_THRESHOLD_DEFAULT
            self.assertEqual(manipulator.intensity_scale, base)
        finally:
            layer.destroy()

    async def test_intensity_scale_snapshots_shaping_at_drag_begin(self):
        """`mark_drag_began` snapshots `_has_shaping_authored()` so drag-tick `intensity_scale`
        reads stay USD-free; `mark_drag_ended` clears the snapshot."""
        vp_api = ViewportAPI("", 0, lambda: 0)
        layer = LightManipulatorLayer({"viewport_api": vp_api})
        try:
            light = self.stage.DefinePrim("/ShapedDiskForCache")
            light.SetTypeName("DiskLight")
            UsdLux.ShapingAPI.Apply(light).CreateShapingConeAngleAttr(30.0)

            class MockEvent:
                type = omni.usd.StageEventType.HIERARCHY_CHANGED.value

            layer._on_stage_event(MockEvent())
            manipulator = self._wire_model_light(layer, "/ShapedDiskForCache")
            self.assertIsNone(manipulator._shaping_authored_cache)
            manipulator.mark_drag_began()
            self.assertTrue(manipulator._shaping_authored_cache)
            manipulator.mark_drag_ended()
            self.assertIsNone(manipulator._shaping_authored_cache)
        finally:
            layer.destroy()

    async def test_drag_end_invalidates_only_for_authored_spotlight_cone(self):
        """Drag-end refreshes only when a cone exists to rebuild."""
        vp_api = ViewportAPI("", 0, lambda: 0)
        layer = LightManipulatorLayer({"viewport_api": vp_api})
        try:
            for path, light_type, cone_angle in (
                ("/PlainDiskForDragEnd", "DiskLight", None),
                ("/PlainSphereForDragEnd", "SphereLight", None),
                ("/ShapedDiskForDragEnd", "DiskLight", 30.0),
                ("/ShapedSphereForDragEnd", "SphereLight", 30.0),
            ):
                light = self.stage.DefinePrim(path)
                light.SetTypeName(light_type)
                if cone_angle is not None:
                    UsdLux.ShapingAPI.Apply(light).CreateShapingConeAngleAttr(cone_angle)

            class MockEvent:
                type = omni.usd.StageEventType.HIERARCHY_CHANGED.value

            layer._on_stage_event(MockEvent())

            invalidated: list[str] = []
            for path, manipulator in layer.manipulators.items():
                self._wire_model_light(layer, path)
                manipulator.invalidate = (lambda self, p=path: invalidated.append(p)).__get__(manipulator)

            for manipulator in layer.manipulators.values():
                manipulator.mark_drag_ended()

            self.assertNotIn("/PlainDiskForDragEnd", invalidated)
            self.assertNotIn("/PlainSphereForDragEnd", invalidated)
            self.assertIn("/ShapedDiskForDragEnd", invalidated)
            self.assertIn("/ShapedSphereForDragEnd", invalidated)
        finally:
            layer.destroy()

    async def test_spotlight_cone_invalidates_on_intensity_change(self):
        """Changing `inputs:intensity` on a spotlight prim invalidates the cone-bearing manipulator."""
        vp_api = ViewportAPI("", 0, lambda: 0)
        layer = LightManipulatorLayer({"viewport_api": vp_api})
        try:
            disk = self.stage.DefinePrim("/IntensityTestDisk")
            disk.SetTypeName("DiskLight")
            sphere = self.stage.DefinePrim("/IntensityTestSphere")
            sphere.SetTypeName("SphereLight")
            for prim in (disk, sphere):
                UsdLux.ShapingAPI.Apply(prim).CreateShapingConeAngleAttr(30.0)

            class MockEvent:
                type = omni.usd.StageEventType.HIERARCHY_CHANGED.value

            layer._on_stage_event(MockEvent())
            self.assertEqual(len(layer.manipulators), 2)

            # The Tf.Notice listener is normally registered on selection; this harness
            # never fires SELECTION_CHANGED, so wire each model up manually.
            for path, manipulator in layer.manipulators.items():
                model = manipulator.model
                prim = self.stage.GetPrimAtPath(path)
                model._light = manipulator.light_class(prim)
                model.prim_path.value = path
                model._stage_listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, model._notice_changed, self.stage)

            invalidated: list[str] = []
            for path, manipulator in layer.manipulators.items():
                # Stub rendering-state methods that `_on_model_updated` calls before
                # `invalidate()` — they need `_shape_xform` etc. which `_build` sets up.
                manipulator.build_shape_xform = (lambda self: None).__get__(manipulator)
                manipulator.build_minimal_intensity_xform = (lambda self: None).__get__(manipulator)
                manipulator.invalidate = (lambda self, p=path: invalidated.append(p)).__get__(manipulator)

            for prim_path in ("/IntensityTestDisk", "/IntensityTestSphere"):
                self.stage.GetPrimAtPath(prim_path).GetAttribute("inputs:intensity").Set(12345.0)

            self.assertIn("/IntensityTestDisk", invalidated)
            self.assertIn("/IntensityTestSphere", invalidated)
        finally:
            layer.destroy()

    async def test_spotlight_cone_defers_invalidation_during_property_edit_interaction(self):
        """Active property edits should not rebuild selected light manipulators until edit completion."""
        vp_api = ViewportAPI("", 0, lambda: 0)
        layer = LightManipulatorLayer({"viewport_api": vp_api})
        token = None
        try:
            disk = self.stage.DefinePrim("/DeferredIntensityDisk")
            disk.SetTypeName("DiskLight")
            sphere = self.stage.DefinePrim("/DeferredIntensitySphere")
            sphere.SetTypeName("SphereLight")
            for prim in (disk, sphere):
                UsdLux.ShapingAPI.Apply(prim).CreateShapingConeAngleAttr(30.0)

            class MockEvent:
                type = omni.usd.StageEventType.HIERARCHY_CHANGED.value

            layer._on_stage_event(MockEvent())
            self.assertEqual(len(layer.manipulators), 2)

            for path, manipulator in layer.manipulators.items():
                model = manipulator.model
                prim = self.stage.GetPrimAtPath(path)
                model._light = manipulator.light_class(prim)
                model.prim_path.value = path
                model._stage_listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, model._notice_changed, self.stage)

            invalidated: list[str] = []
            for path, manipulator in layer.manipulators.items():
                manipulator.build_shape_xform = (lambda self: None).__get__(manipulator)
                manipulator.build_minimal_intensity_xform = (lambda self: None).__get__(manipulator)
                manipulator.build_intensity_xform = (lambda self: None).__get__(manipulator)
                manipulator.invalidate = (lambda self, p=path: invalidated.append(p)).__get__(manipulator)

            token = _begin_interaction(self.stage)
            disk.GetAttribute("inputs:intensity").Set(12345.0)
            disk.GetAttribute("inputs:shaping:cone:angle").Set(45.0)
            sphere.GetAttribute("inputs:intensity").Set(6789.0)

            self.assertEqual(invalidated, [])

            _end_interaction(token)
            token = None

            self.assertEqual(invalidated.count("/DeferredIntensityDisk"), 1)
            self.assertEqual(invalidated.count("/DeferredIntensitySphere"), 1)
        finally:
            if token is not None:
                _end_interaction(token)
            layer.destroy()

    async def test_spotlight_cone_teardown_cancels_deferred_invalidation(self):
        """Layer teardown should revoke deferred cone rebuild callbacks before scene items are cleared."""
        vp_api = ViewportAPI("", 0, lambda: 0)
        layer = LightManipulatorLayer({"viewport_api": vp_api})
        token = None
        try:
            disk = self.stage.DefinePrim("/DeferredDestroyDisk")
            disk.SetTypeName("DiskLight")
            UsdLux.ShapingAPI.Apply(disk).CreateShapingConeAngleAttr(30.0)

            class MockEvent:
                type = omni.usd.StageEventType.HIERARCHY_CHANGED.value

            layer._on_stage_event(MockEvent())
            self.assertEqual(len(layer.manipulators), 1)

            manipulator = self._wire_model_light(layer, "/DeferredDestroyDisk")
            manipulator.model.prim_path.value = "/DeferredDestroyDisk"
            manipulator.model._stage_listener = Tf.Notice.Register(
                Usd.Notice.ObjectsChanged, manipulator.model._notice_changed, self.stage
            )

            invalidated: list[str] = []
            manipulator.build_shape_xform = (lambda self: None).__get__(manipulator)
            manipulator.build_minimal_intensity_xform = (lambda self: None).__get__(manipulator)
            manipulator.invalidate = (lambda self: invalidated.append("/DeferredDestroyDisk")).__get__(manipulator)

            token = _begin_interaction(self.stage)
            disk.GetAttribute("inputs:intensity").Set(12345.0)

            self.assertEqual(invalidated, [])
            self.assertTrue(manipulator._cone_refresh_deferred)
            self.assertIsNotNone(manipulator._interaction_end_subscription)

            layer._destroy_manipulators()

            self.assertFalse(manipulator._cone_refresh_deferred)
            self.assertIsNone(manipulator._interaction_end_subscription)

            _end_interaction(token)
            token = None

            self.assertEqual(invalidated, [])
        finally:
            if token is not None:
                _end_interaction(token)
            layer.destroy()
