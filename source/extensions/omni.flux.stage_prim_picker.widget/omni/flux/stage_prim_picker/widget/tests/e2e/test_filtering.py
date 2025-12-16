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

import omni.kit.app
import omni.kit.test
import omni.kit.ui_test as ui_test
import omni.ui as ui
import omni.usd
from omni.flux.stage_prim_picker.widget import StagePrimPickerField
from pxr import UsdGeom, UsdLux


class MockValueModel(ui.AbstractValueModel):
    def __init__(self, initial_value: str = ""):
        super().__init__()
        self._value = initial_value

    def get_value_as_string(self) -> str:
        return self._value

    def set_value(self, value):
        self._value = str(value)
        self._value_changed()

    def get_value_as_float(self) -> float:
        return 0.0

    def get_value_as_bool(self) -> bool:
        return bool(self._value)

    def get_value_as_int(self) -> int:
        return 0


class MockItem:
    def __init__(self, name: str, value: str = ""):
        self.name = name
        self.element_count = 1
        self.value_models = [MockValueModel(value)]


class TestFiltering(omni.kit.test.AsyncTestCase):
    """Advanced filtering tests."""

    async def setUp(self):
        # ARRANGE
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()
        self._test_window = None
        self._picker = None

    async def tearDown(self):
        # CLEANUP - Destroy picker widget (handles dropdown window cleanup)
        if self._picker:
            self._picker.destroy()
            self._picker = None

        # CLEANUP - Destroy test window
        if self._test_window:
            self._test_window.frame.clear()
            self._test_window.destroy()
            self._test_window = None

        await omni.kit.app.get_app().next_update_async()

        # CLEANUP - Close stage if still open
        if self.context and self.context.get_stage():
            await self.context.close_stage_async()

        self.stage = None

    async def test_prim_type_filter_shows_only_specified_types(self):
        """H1: prim_types parameter filters to specified types only."""
        # ARRANGE - Mix of different prim types
        UsdGeom.Xform.Define(self.stage, "/World")
        UsdGeom.Mesh.Define(self.stage, "/World/Mesh1")
        UsdGeom.Mesh.Define(self.stage, "/World/Mesh2")
        UsdGeom.Sphere.Define(self.stage, "/World/Sphere")
        UsdLux.SphereLight.Define(self.stage, "/World/Light")
        UsdGeom.Camera.Define(self.stage, "/World/Camera")

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            # Only show Mesh types
            self._picker = StagePrimPickerField(identifier="test_picker", prim_types=["Mesh"])
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='test_picker_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Only Mesh prims appear (in dropdown window)
        prim_buttons = ui_test.find_all(
            "StagePrimPickerDropdown_test_picker_0//Frame/**/Label[*].name=='StagePrimPickerItem'"
        )
        prim_paths = [b.widget.text for b in prim_buttons]

        self.assertEqual(len(prim_buttons), 2, "Should show exactly 2 Mesh prims")
        self.assertIn("/World/Mesh1", prim_paths)
        self.assertIn("/World/Mesh2", prim_paths)
        self.assertNotIn("/World/Light", prim_paths, "Lights should be filtered out")
        self.assertNotIn("/World/Camera", prim_paths, "Cameras should be filtered out")

    async def test_custom_filter_function_works(self):
        """H2: Custom prim_filter function filters prims correctly."""
        # ARRANGE - Prims with varying names
        UsdGeom.Xform.Define(self.stage, "/World")
        UsdGeom.Mesh.Define(self.stage, "/World/ActiveMesh")
        UsdGeom.Mesh.Define(self.stage, "/World/InactiveMesh").GetPrim().SetActive(False)
        UsdGeom.Mesh.Define(self.stage, "/World/AnotherActive")

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            # Only show active prims
            self._picker = StagePrimPickerField(identifier="test_picker", prim_filter=lambda prim: prim.IsActive())
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='test_picker_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Only active prims appear (in dropdown window)
        prim_buttons = ui_test.find_all(
            "StagePrimPickerDropdown_test_picker_0//Frame/**/Label[*].name=='StagePrimPickerItem'"
        )
        prim_paths = [b.widget.text for b in prim_buttons]

        self.assertIn("/World/ActiveMesh", prim_paths)
        self.assertIn("/World/AnotherActive", prim_paths)
        self.assertNotIn("/World/InactiveMesh", prim_paths, "Inactive prim should be filtered out")

    async def test_combined_type_and_custom_filters(self):
        """H3: Type filter AND custom filter both apply (AND logic)."""
        # ARRANGE - Mix of types and states
        UsdGeom.Xform.Define(self.stage, "/World")
        UsdGeom.Mesh.Define(self.stage, "/World/ActiveMesh")
        inactive_mesh = UsdGeom.Mesh.Define(self.stage, "/World/InactiveMesh")
        inactive_mesh.GetPrim().SetActive(False)
        UsdGeom.Sphere.Define(self.stage, "/World/ActiveSphere")  # Wrong type

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            # Must be Mesh AND active
            self._picker = StagePrimPickerField(
                identifier="test_picker",
                prim_types=["Mesh"],
                prim_filter=lambda prim: prim.IsActive(),
            )
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='test_picker_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Only active Meshes (in dropdown window)
        prim_buttons = ui_test.find_all(
            "StagePrimPickerDropdown_test_picker_0//Frame/**/Label[*].name=='StagePrimPickerItem'"
        )
        self.assertEqual(len(prim_buttons), 1, "Should have exactly 1 prim (active Mesh)")
        self.assertIn("/World/ActiveMesh", prim_buttons[0].widget.text)

    async def test_empty_type_list_shows_nothing(self):
        """H1: Edge case - empty prim_types list shows no prims."""
        # ARRANGE
        UsdGeom.Mesh.Define(self.stage, "/World/Mesh")
        UsdGeom.Sphere.Define(self.stage, "/World/Sphere")

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            self._picker = StagePrimPickerField(identifier="test_picker", prim_types=[])
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='test_picker_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - No prims shown (in dropdown window)
        prim_buttons = ui_test.find_all(
            "StagePrimPickerDropdown_test_picker_0//Frame/**/Label[*].name=='StagePrimPickerItem'"
        )
        self.assertEqual(len(prim_buttons), 0, "Empty type list should show no prims")

        no_prims_label = ui_test.find("StagePrimPickerDropdown_test_picker_0//Frame/**/Label[*].text=='No prims found'")
        self.assertIsNotNone(no_prims_label, "Should show 'No prims found' message")
