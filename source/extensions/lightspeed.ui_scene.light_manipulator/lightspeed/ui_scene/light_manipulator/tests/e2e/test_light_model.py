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

import omni.kit.test
import omni.usd
from lightspeed.ui_scene.light_manipulator import DiskLightModel, SphereLightModel, is_spotlight
from omni.ui.tests.test_base import OmniUiTest
from pxr import Sdf, Usd, UsdLux


class MockManip:
    def __init__(self, model):
        self._model = model

    @property
    def model(self):
        return self._model


class MockLayer:
    def __init__(self):
        self._manipulators = {}

    def create_manipulator(self, prim_path, manipulator):
        self._manipulators[prim_path] = manipulator

    @property
    def manipulators(self):
        return self._manipulators


class TestLightModel(OmniUiTest):
    # Before running each test
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.stage: Usd.Stage = omni.usd.get_context().get_stage()

    # After running each test
    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()

    async def test_model_usd_interaction(self):
        """
        Test to make sure manipulators will be able to interact well with model and get get updates
        flowing through to USD at the right time.
        """
        # create a light
        light = self.stage.DefinePrim("/TestLight")
        light.SetTypeName("DiskLight")
        disk_light = UsdLux.DiskLight(light)
        disk_light.CreateIntensityAttr().Set(10.0)
        disk_light.CreateRadiusAttr().Set(10.0)

        mock_viewport_layer = MockLayer()
        disk_model = DiskLightModel(
            light, usd_context_name=omni.usd.get_context().get_name(), viewport_layer=mock_viewport_layer
        )
        mock_viewport_layer.create_manipulator("/TestLight", MockManip(disk_model))
        # mock selecting a light
        omni.usd.get_context().get_selection().set_selected_prim_paths(["/TestLight"], True)
        disk_model._on_kit_selection_changed()

        with self.subTest("Test setting just the model, and reverting via updating from USD"):
            # set only the model item (not USD)
            disk_model.set_item_value(disk_model.radius, 100.0)
            self.assertNotEqual(disk_model.get_as_float("radius"), 100.0)
            # update the model from USD
            disk_model.update_from_prim()
            self.assertEqual(disk_model.get_as_float("radius"), 10.0)

        with self.subTest("Test set_float() behavior"):
            # make sure set_float forwards changes to USD
            disk_model.set_float(disk_model.radius, 100.0)
            self.assertEqual(disk_light.GetRadiusAttr().Get(), 100.0)
            # get_as_float should read from USD
            self.assertEqual(disk_model.get_as_float("radius"), 100.0)
            # but not the model itself
            self.assertEqual(disk_model.radius.value, 10.0)

            # until we update the model from USD
            disk_model.update_from_prim()
            self.assertEqual(disk_model.get_as_float("radius"), 100.0)

        with self.subTest("Test set_float_commands() behavior"):
            # set an initial value and then simulate a manipulator move to a new value
            disk_model.set_item_value(disk_model.radius, 5.0)
            disk_model.set_float(disk_model.radius, 15.0)  # intermediate value
            disk_model.set_float_commands(disk_model.radius, 50.0)
            self.assertEqual(disk_light.GetRadiusAttr().Get(), 50.0)
            omni.kit.undo.undo()
            self.assertEqual(disk_light.GetRadiusAttr().Get(), 5.0)

        with self.subTest("Test set_float_multiple()"):
            disk_model.set_float_multiple("radius", disk_model.radius, 60.0)
            self.assertNotEqual(disk_model.radius.value, 60.0)

    async def test_is_spotlight_helper(self):
        """`is_spotlight` should be True only when ShapingAPI is applied with an authored cone
        angle narrower than a hemisphere (90°). Anything else is an ordinary light."""
        plain_light_prim = self.stage.DefinePrim("/PlainLight")
        plain_light_prim.SetTypeName("SphereLight")
        self.assertFalse(is_spotlight(plain_light_prim), "Plain SphereLight must not be a spotlight")

        applied_no_value_prim = self.stage.DefinePrim("/ShapingNoValue")
        applied_no_value_prim.SetTypeName("SphereLight")
        UsdLux.ShapingAPI.Apply(applied_no_value_prim)
        self.assertFalse(
            is_spotlight(applied_no_value_prim),
            "ShapingAPI applied but cone angle unauthored must not count as a spotlight",
        )

        narrow_prim = self.stage.DefinePrim("/NarrowSpot")
        narrow_prim.SetTypeName("SphereLight")
        UsdLux.ShapingAPI.Apply(narrow_prim).CreateShapingConeAngleAttr(45.0)
        self.assertTrue(is_spotlight(narrow_prim), "Cone angle 45° must count as a spotlight")

        hemisphere_prim = self.stage.DefinePrim("/Hemisphere")
        hemisphere_prim.SetTypeName("SphereLight")
        UsdLux.ShapingAPI.Apply(hemisphere_prim).CreateShapingConeAngleAttr(90.0)
        self.assertFalse(is_spotlight(hemisphere_prim), "Cone angle 90° is omnidirectional, not a spotlight")

    async def test_is_spotlight_with_degenerate_cone_angle_returns_false(self):
        """`is_spotlight` rejects zero and negative cone angles."""
        for path, angle in (("/ZeroCone", 0.0), ("/NegativeCone", -1.0)):
            with self.subTest(angle=angle):
                prim = self.stage.DefinePrim(path)
                prim.SetTypeName("SphereLight")
                UsdLux.ShapingAPI.Apply(prim).CreateShapingConeAngleAttr(angle)

                self.assertFalse(is_spotlight(prim), f"Cone angle {angle} must not count as a spotlight")

    async def test_shaping_mixin_reads_cone_angle(self):
        """DiskLightModel (and by extension SphereLightModel) should expose a cone_angle item
        populated from `inputs:shaping:cone:angle` via update_from_prim."""
        prim = self.stage.DefinePrim("/SpotDisk")
        prim.SetTypeName("DiskLight")
        UsdLux.DiskLight(prim).CreateRadiusAttr().Set(2.0)
        UsdLux.ShapingAPI.Apply(prim).CreateShapingConeAngleAttr(30.0)

        mock_viewport_layer = MockLayer()
        model = DiskLightModel(
            prim, usd_context_name=omni.usd.get_context().get_name(), viewport_layer=mock_viewport_layer
        )
        mock_viewport_layer.create_manipulator("/SpotDisk", MockManip(model))
        omni.usd.get_context().get_selection().set_selected_prim_paths(["/SpotDisk"], True)
        model._on_kit_selection_changed()
        model.update_from_prim()

        self.assertEqual(model.cone_angle.value, 30.0)

    async def test_shaping_mixin_notice_picks_up_cone_attr(self):
        """A change-notice on inputs:shaping:cone:angle must route to the cone_angle item so the
        manipulator re-renders (via on_model_updated)."""
        prim = self.stage.DefinePrim("/SpotDisk2")
        prim.SetTypeName("DiskLight")
        UsdLux.ShapingAPI.Apply(prim).CreateShapingConeAngleAttr(60.0)

        mock_viewport_layer = MockLayer()
        model = DiskLightModel(
            prim, usd_context_name=omni.usd.get_context().get_name(), viewport_layer=mock_viewport_layer
        )

        changed = model._light_attribute_notice_changed(Sdf.Path("/SpotDisk2.inputs:shaping:cone:angle"))
        self.assertIn(model.cone_angle, changed)
        # Unrelated attrs don't trigger
        unrelated = model._light_attribute_notice_changed(Sdf.Path("/SpotDisk2.inputs:color"))
        self.assertNotIn(model.cone_angle, unrelated)
        # Radius still routes to its own item (mixin chaining preserved DiskLightModel's logic)
        radius_changed = model._light_attribute_notice_changed(Sdf.Path("/SpotDisk2.inputs:radius"))
        self.assertIn(model.radius, radius_changed)

    async def test_spherelight_model_inherits_cone_angle(self):
        """SphereLightModel inherits ShapingMixin via DiskLightModel."""
        prim = self.stage.DefinePrim("/SpotSphere")
        prim.SetTypeName("SphereLight")
        model = SphereLightModel(prim, usd_context_name=omni.usd.get_context().get_name())
        self.assertTrue(hasattr(model, "cone_angle"))
        self.assertTrue(hasattr(model, "softness"))

    async def test_shaping_mixin_reads_softness(self):
        """DiskLightModel should expose a softness item populated from
        `inputs:shaping:cone:softness`. Unauthored values default to 0.0."""
        prim = self.stage.DefinePrim("/SpotDiskSoft")
        prim.SetTypeName("DiskLight")
        UsdLux.DiskLight(prim).CreateRadiusAttr().Set(2.0)
        shaping = UsdLux.ShapingAPI.Apply(prim)
        shaping.CreateShapingConeAngleAttr(45.0)
        shaping.CreateShapingConeSoftnessAttr(0.25)

        mock_viewport_layer = MockLayer()
        model = DiskLightModel(
            prim, usd_context_name=omni.usd.get_context().get_name(), viewport_layer=mock_viewport_layer
        )
        mock_viewport_layer.create_manipulator("/SpotDiskSoft", MockManip(model))
        omni.usd.get_context().get_selection().set_selected_prim_paths(["/SpotDiskSoft"], True)
        model._on_kit_selection_changed()
        model.update_from_prim()

        self.assertAlmostEqual(model.softness.value, 0.25)

    async def test_shaping_mixin_softness_unauthored_defaults_to_zero(self):
        """A spotlight without an authored softness attribute reports softness = 0.0."""
        prim = self.stage.DefinePrim("/SpotDiskNoSoft")
        prim.SetTypeName("DiskLight")
        UsdLux.ShapingAPI.Apply(prim).CreateShapingConeAngleAttr(30.0)

        mock_viewport_layer = MockLayer()
        model = DiskLightModel(
            prim, usd_context_name=omni.usd.get_context().get_name(), viewport_layer=mock_viewport_layer
        )
        mock_viewport_layer.create_manipulator("/SpotDiskNoSoft", MockManip(model))
        omni.usd.get_context().get_selection().set_selected_prim_paths(["/SpotDiskNoSoft"], True)
        model._on_kit_selection_changed()
        model.update_from_prim()

        self.assertEqual(model.softness.value, 0.0)

    async def test_shaping_mixin_notice_picks_up_softness_attr(self):
        """A change-notice on inputs:shaping:cone:softness must route to the softness item so the
        manipulator re-renders its inner cone."""
        prim = self.stage.DefinePrim("/SpotDiskSoft2")
        prim.SetTypeName("DiskLight")
        shaping = UsdLux.ShapingAPI.Apply(prim)
        shaping.CreateShapingConeAngleAttr(45.0)
        shaping.CreateShapingConeSoftnessAttr(0.5)

        mock_viewport_layer = MockLayer()
        model = DiskLightModel(
            prim, usd_context_name=omni.usd.get_context().get_name(), viewport_layer=mock_viewport_layer
        )

        changed = model._light_attribute_notice_changed(Sdf.Path("/SpotDiskSoft2.inputs:shaping:cone:softness"))
        self.assertIn(model.softness, changed)
        # The cone angle item should NOT be routed on a softness change.
        self.assertNotIn(model.cone_angle, changed)

    async def test_notice_changed_handles_shaping_removal(self):
        """Removing a shaping attribute emits only a USD resync notice; `_notice_changed`
        must walk resynced paths so the cone manipulator clears without reselection."""
        prim = self.stage.DefinePrim("/SpotDiskRemove")
        prim.SetTypeName("DiskLight")
        shaping = UsdLux.ShapingAPI.Apply(prim)
        cone_attr = shaping.CreateShapingConeAngleAttr(30.0)

        mock_viewport_layer = MockLayer()
        model = DiskLightModel(
            prim, usd_context_name=omni.usd.get_context().get_name(), viewport_layer=mock_viewport_layer
        )
        mock_viewport_layer.create_manipulator("/SpotDiskRemove", MockManip(model))
        omni.usd.get_context().get_selection().set_selected_prim_paths(["/SpotDiskRemove"], True)
        model._on_kit_selection_changed()
        model.update_from_prim()
        self.assertAlmostEqual(model.cone_angle.value, 30.0)

        prim.RemoveProperty(cone_attr.GetName())
        self.assertFalse(prim.GetAttribute("inputs:shaping:cone:angle").HasAuthoredValue())
        self.assertEqual(model.cone_angle.value, 0.0)

    async def test_notice_changed_handles_shaping_creation_for_selected_sphere(self):
        """A resync-only shaping notice refreshes a selected SphereLight without reselection."""
        prim = self.stage.DefinePrim("/SpotSphereCreate")
        prim.SetTypeName("SphereLight")

        mock_viewport_layer = MockLayer()
        model = SphereLightModel(
            prim, usd_context_name=omni.usd.get_context().get_name(), viewport_layer=mock_viewport_layer
        )
        mock_viewport_layer.create_manipulator("/SpotSphereCreate", MockManip(model))
        model._light = UsdLux.SphereLight(prim)
        model.prim_path.value = "/SpotSphereCreate"
        model.update_from_prim()
        self.assertEqual(model.cone_angle.value, 0.0)

        signaled: list = []
        original_item_changed = model._item_changed

        def capture(item):
            signaled.append(item)
            original_item_changed(item)

        model._item_changed = capture

        UsdLux.ShapingAPI.Apply(prim).CreateShapingConeAngleAttr(45.0)

        mock_notice = type("MockNotice", (), {})()
        mock_notice.GetResyncedPaths = lambda: [Sdf.Path("/SpotSphereCreate.inputs:shaping:cone:angle")]
        mock_notice.GetChangedInfoOnlyPaths = lambda: []

        model._notice_changed(mock_notice, self.stage)

        self.assertIn(model.cone_angle, signaled)
        self.assertAlmostEqual(model.cone_angle.value, 45.0)

    async def test_notice_changed_does_not_teardown_manipulator_on_authoring_resync(self):
        """Routine attribute authoring (e.g. mid-drag intensity write) can trigger a USD
        resync alongside the value change. `_notice_changed` must not signal `prim_path`
        in that case — doing so tears down the manipulator and ends the in-progress drag.
        Regression test for the deselect-mid-drag bug."""
        prim = self.stage.DefinePrim("/SpotDiskDrag")
        prim.SetTypeName("DiskLight")
        UsdLux.ShapingAPI.Apply(prim).CreateShapingConeAngleAttr(30.0)

        mock_viewport_layer = MockLayer()
        model = DiskLightModel(
            prim, usd_context_name=omni.usd.get_context().get_name(), viewport_layer=mock_viewport_layer
        )
        mock_viewport_layer.create_manipulator("/SpotDiskDrag", MockManip(model))
        omni.usd.get_context().get_selection().set_selected_prim_paths(["/SpotDiskDrag"], True)
        model._on_kit_selection_changed()
        model.update_from_prim()
        self.assertAlmostEqual(model.cone_angle.value, 30.0)

        signaled: list = []
        original_item_changed = model._item_changed

        def capture(item):
            signaled.append(item)
            original_item_changed(item)

        model._item_changed = capture

        # First-time intensity authoring fires a resync (attr spec creation) plus a
        # ChangedInfoOnly on the value, in the same notice.
        UsdLux.DiskLight(prim).CreateIntensityAttr().Set(500.0)

        self.assertNotIn(
            model.prim_path,
            signaled,
            "prim_path must not be signaled on a resync that didn't change prim identity — "
            "would tear down the manipulator and break in-progress drags",
        )
        self.assertNotIn(
            model.cone_angle,
            signaled,
            "cone_angle must not be signaled when the shaping attr is still authored",
        )
