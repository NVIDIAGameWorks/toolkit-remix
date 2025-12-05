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

import random

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


class TestPathPatterns(omni.kit.test.AsyncTestCase):
    """Path pattern filtering tests with glob support."""

    async def setUp(self):
        # ARRANGE
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()
        self._test_window = None
        self._picker = None
        self._test_id = f"test_{random.randint(10000, 99999)}"

    async def tearDown(self):
        # CLEANUP
        if self._picker:
            self._picker.destroy()
            self._picker = None

        if self._test_window:
            self._test_window.frame.clear()
            self._test_window.destroy()
            self._test_window = None

        await omni.kit.app.get_app().next_update_async()

        if self.context and self.context.get_stage():
            await self.context.close_stage_async()

        self.stage = None

    async def test_simple_wildcard_pattern(self):
        """Path pattern with simple wildcard filters correctly."""
        # ARRANGE - Create hierarchy
        UsdGeom.Xform.Define(self.stage, "/World")
        UsdGeom.Xform.Define(self.stage, "/World/Geometry")
        UsdGeom.Mesh.Define(self.stage, "/World/Geometry/Cube")
        UsdGeom.Mesh.Define(self.stage, "/World/Geometry/Sphere")
        UsdGeom.Xform.Define(self.stage, "/World/Lights")
        UsdLux.SphereLight.Define(self.stage, "/World/Lights/Key")

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            # Only show prims under /World/Geometry/*
            self._picker = StagePrimPickerField(identifier=self._test_id, path_patterns=["/World/Geometry/*"])
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='{self._test_id}_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Only Geometry children appear
        dropdown_id = f"StagePrimPickerDropdown_{self._test_id}_0"
        prim_buttons = ui_test.find_all(f"{dropdown_id}//Frame/**/Button[*].name=='StagePrimPickerItem'")
        prim_paths = [b.widget.text for b in prim_buttons]

        self.assertEqual(len(prim_buttons), 2, "Should show 2 prims under Geometry")
        self.assertIn("/World/Geometry/Cube", prim_paths)
        self.assertIn("/World/Geometry/Sphere", prim_paths)
        self.assertNotIn("/World/Lights/Key", prim_paths, "Lights should be filtered out")

    async def test_recursive_wildcard_pattern(self):
        """Path pattern with ** matches prims at any depth."""
        # ARRANGE - Deep hierarchy
        UsdGeom.Xform.Define(self.stage, "/World")
        UsdGeom.Xform.Define(self.stage, "/World/Props")
        UsdGeom.Mesh.Define(self.stage, "/World/Props/Table")
        UsdLux.SphereLight.Define(self.stage, "/World/Lights/KeyLight")
        UsdLux.SphereLight.Define(self.stage, "/World/Set1/Lights/LightRig")
        UsdGeom.Mesh.Define(self.stage, "/World/Other/Mesh")

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            # Match any prim whose name starts with "Light" at any depth
            self._picker = StagePrimPickerField(identifier=self._test_id, path_patterns=["**/Light*"])
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='{self._test_id}_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Finds all prims whose name starts with "Light"
        dropdown_id = f"StagePrimPickerDropdown_{self._test_id}_0"
        prim_buttons = ui_test.find_all(f"{dropdown_id}//Frame/**/Button[*].name=='StagePrimPickerItem'")
        prim_paths = [b.widget.text for b in prim_buttons]

        self.assertIn("/World/Lights", prim_paths, "Should match 'Lights' folder")
        self.assertIn("/World/Lights/KeyLight", prim_paths, "Should match KeyLight")
        self.assertIn(
            "/World/Set1/Lights/LightRig",
            prim_paths,
            "Should match LightRig at any depth",
        )
        self.assertNotIn("/World/Props/Table", prim_paths, "Table doesn't start with Light")
        self.assertNotIn("/World/Other/Mesh", prim_paths, "Mesh doesn't start with Light")

    async def test_multiple_or_patterns(self):
        """Multiple path patterns are OR'd together."""
        # ARRANGE
        UsdGeom.Xform.Define(self.stage, "/World")
        UsdGeom.Mesh.Define(self.stage, "/World/Geometry/Cube")
        UsdLux.SphereLight.Define(self.stage, "/World/Lights/Key")
        UsdGeom.Camera.Define(self.stage, "/World/Cameras/Main")
        UsdGeom.Mesh.Define(self.stage, "/World/Props/Table")

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            # Match Geometry/* OR Lights/*
            self._picker = StagePrimPickerField(
                identifier=self._test_id,
                path_patterns=["/World/Geometry/*", "/World/Lights/*"],
            )
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='{self._test_id}_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Shows Geometry and Lights, not Cameras or Props
        dropdown_id = f"StagePrimPickerDropdown_{self._test_id}_0"
        prim_buttons = ui_test.find_all(f"{dropdown_id}//Frame/**/Button[*].name=='StagePrimPickerItem'")
        prim_paths = [b.widget.text for b in prim_buttons]

        self.assertIn("/World/Geometry/Cube", prim_paths)
        self.assertIn("/World/Lights/Key", prim_paths)
        self.assertNotIn("/World/Cameras/Main", prim_paths, "Cameras not in patterns")
        self.assertNotIn("/World/Props/Table", prim_paths, "Props not in patterns")

    async def test_path_pattern_with_type_filter(self):
        """Path patterns combine with type filters (AND logic)."""
        # ARRANGE
        UsdGeom.Xform.Define(self.stage, "/World")
        UsdGeom.Xform.Define(self.stage, "/World/Geometry")  # Xform, not Mesh
        UsdGeom.Mesh.Define(self.stage, "/World/Geometry/Cube")  # Mesh
        UsdGeom.Mesh.Define(self.stage, "/World/Geometry/Sphere")  # Mesh
        UsdGeom.Mesh.Define(self.stage, "/World/Props/Table")  # Wrong path

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            # Must be Mesh AND under /World/Geometry/**
            self._picker = StagePrimPickerField(
                identifier=self._test_id,
                prim_types=["Mesh"],
                path_patterns=["/World/Geometry/**"],
            )
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='{self._test_id}_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Only Meshes under Geometry
        dropdown_id = f"StagePrimPickerDropdown_{self._test_id}_0"
        prim_buttons = ui_test.find_all(f"{dropdown_id}//Frame/**/Button[*].name=='StagePrimPickerItem'")
        prim_paths = [b.widget.text for b in prim_buttons]

        self.assertEqual(len(prim_buttons), 2, "Should have 2 Meshes under Geometry")
        self.assertIn("/World/Geometry/Cube", prim_paths)
        self.assertIn("/World/Geometry/Sphere", prim_paths)
        self.assertNotIn("/World/Geometry", prim_paths, "Xform should be filtered by type")
        self.assertNotIn("/World/Props/Table", prim_paths, "Props outside pattern scope")

    async def test_empty_pattern_list_shows_nothing(self):
        """Edge case: empty path_patterns list shows no prims."""
        # ARRANGE
        UsdGeom.Mesh.Define(self.stage, "/World/Mesh")
        UsdGeom.Sphere.Define(self.stage, "/World/Sphere")

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            self._picker = StagePrimPickerField(identifier=self._test_id, path_patterns=[])
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='{self._test_id}_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - No prims shown
        dropdown_id = f"StagePrimPickerDropdown_{self._test_id}_0"
        prim_buttons = ui_test.find_all(f"{dropdown_id}//Frame/**/Button[*].name=='StagePrimPickerItem'")
        self.assertEqual(len(prim_buttons), 0, "Empty pattern list should show nothing")

        no_prims_label = ui_test.find(f"{dropdown_id}//Frame/**/Label[*].text=='No prims found'")
        self.assertIsNotNone(no_prims_label, "Should show 'No prims found' message")

    async def test_multiple_wildcards_in_pattern(self):
        """Pattern with multiple * wildcards."""
        # ARRANGE
        UsdGeom.Xform.Define(self.stage, "/World")
        UsdGeom.Mesh.Define(self.stage, "/World/Geometry/Props/Table_01")
        UsdGeom.Mesh.Define(self.stage, "/World/Geometry/Props/Chair_02")
        UsdGeom.Mesh.Define(self.stage, "/World/Geometry/Lights/Lamp_01")
        UsdGeom.Mesh.Define(self.stage, "/World/Other/Item")

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            # Pattern: /World/*/Props/*_01
            self._picker = StagePrimPickerField(identifier=self._test_id, path_patterns=["/World/*/Props/*_01"])
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='{self._test_id}_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT
        dropdown_id = f"StagePrimPickerDropdown_{self._test_id}_0"
        prim_buttons = ui_test.find_all(f"{dropdown_id}//Frame/**/Button[*].name=='StagePrimPickerItem'")
        prim_paths = [b.widget.text for b in prim_buttons]

        self.assertEqual(len(prim_buttons), 1, "Should match only Table_01")
        self.assertIn("/World/Geometry/Props/Table_01", prim_paths)
        self.assertNotIn("/World/Geometry/Props/Chair_02", prim_paths, "Doesn't end with _01")
        self.assertNotIn("/World/Geometry/Lights/Lamp_01", prim_paths, "Not under Props")

    async def test_multiple_recursive_wildcards(self):
        """Pattern with ** finds prims under specific folder structure at any depth."""
        # ARRANGE
        UsdGeom.Xform.Define(self.stage, "/World")
        UsdGeom.Xform.Define(self.stage, "/World/Set1/Geometry/Props")
        UsdGeom.Mesh.Define(self.stage, "/World/Set1/Geometry/Props/Table")
        UsdGeom.Xform.Define(self.stage, "/World/Set2/Geometry/Props")
        UsdGeom.Mesh.Define(self.stage, "/World/Set2/Geometry/Props/Chair")
        UsdGeom.Mesh.Define(self.stage, "/World/Set1/Lights/Key")

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            # Pattern: anything under a "Props" folder at any level
            self._picker = StagePrimPickerField(identifier=self._test_id, path_patterns=["**/Props/*"])
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='{self._test_id}_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Finds direct children of any "Props" folder
        dropdown_id = f"StagePrimPickerDropdown_{self._test_id}_0"
        prim_buttons = ui_test.find_all(f"{dropdown_id}//Frame/**/Button[*].name=='StagePrimPickerItem'")
        prim_paths = [b.widget.text for b in prim_buttons]

        self.assertIn("/World/Set1/Geometry/Props/Table", prim_paths)
        self.assertIn("/World/Set2/Geometry/Props/Chair", prim_paths)
        self.assertNotIn("/World/Set1/Lights/Key", prim_paths, "Not under Props folder")

    async def test_root_exclusive_pattern(self):
        """Pattern /World/Geometry/* excludes Geometry itself, shows only children."""
        # ARRANGE
        UsdGeom.Xform.Define(self.stage, "/World")
        UsdGeom.Xform.Define(self.stage, "/World/Geometry")
        UsdGeom.Mesh.Define(self.stage, "/World/Geometry/Cube")
        UsdGeom.Mesh.Define(self.stage, "/World/Geometry/Sphere")

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            # /* means children only, not parent
            self._picker = StagePrimPickerField(identifier=self._test_id, path_patterns=["/World/Geometry/*"])
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='{self._test_id}_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Geometry itself NOT included
        dropdown_id = f"StagePrimPickerDropdown_{self._test_id}_0"
        prim_buttons = ui_test.find_all(f"{dropdown_id}//Frame/**/Button[*].name=='StagePrimPickerItem'")
        prim_paths = [b.widget.text for b in prim_buttons]

        self.assertNotIn("/World/Geometry", prim_paths, "Root itself should be excluded with /*")
        self.assertIn("/World/Geometry/Cube", prim_paths, "Children should be included")
        self.assertIn("/World/Geometry/Sphere", prim_paths, "Children should be included")

    async def test_root_inclusive_pattern(self):
        """Pattern with exact match and /** includes root and descendants."""
        # ARRANGE
        UsdGeom.Xform.Define(self.stage, "/World")
        UsdGeom.Xform.Define(self.stage, "/World/Geometry")
        UsdGeom.Mesh.Define(self.stage, "/World/Geometry/Cube")
        UsdGeom.Mesh.Define(self.stage, "/World/Other/Mesh")

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            # Use two patterns: exact match + recursive for root-inclusive
            self._picker = StagePrimPickerField(
                identifier=self._test_id,
                path_patterns=["/World/Geometry", "/World/Geometry/**"],
            )
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='{self._test_id}_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Geometry AND its children included
        dropdown_id = f"StagePrimPickerDropdown_{self._test_id}_0"
        prim_buttons = ui_test.find_all(f"{dropdown_id}//Frame/**/Button[*].name=='StagePrimPickerItem'")
        prim_paths = [b.widget.text for b in prim_buttons]

        self.assertIn("/World/Geometry", prim_paths, "Root should be included")
        self.assertIn("/World/Geometry/Cube", prim_paths, "Children should be included")
        self.assertNotIn("/World/Other/Mesh", prim_paths, "Other paths excluded")

    async def test_pattern_optimization_skips_subtrees(self):
        """Path patterns optimize traversal by skipping non-matching subtrees."""
        # ARRANGE - Large stage, but pattern targets small subset
        UsdGeom.Xform.Define(self.stage, "/World")

        # Create 200 prims under /World/Ignored (should be skipped entirely)
        UsdGeom.Xform.Define(self.stage, "/World/Ignored")
        for i in range(200):
            UsdGeom.Mesh.Define(self.stage, f"/World/Ignored/Mesh_{i:03d}")

        # Create 5 prims under /World/Target (only these should be checked)
        UsdGeom.Xform.Define(self.stage, "/World/Target")
        for i in range(5):
            UsdGeom.Mesh.Define(self.stage, f"/World/Target/Mesh_{i}")

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            # Only target /World/Target/*
            self._picker = StagePrimPickerField(
                identifier=self._test_id,
                path_patterns=["/World/Target/*"],
                initial_items=50,  # More than 5, so all would show if optimization works
            )
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='{self._test_id}_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Only 5 prims from Target, Ignored subtree was skipped
        dropdown_id = f"StagePrimPickerDropdown_{self._test_id}_0"
        prim_buttons = ui_test.find_all(f"{dropdown_id}//Frame/**/Button[*].name=='StagePrimPickerItem'")
        prim_paths = [b.widget.text for b in prim_buttons]

        self.assertEqual(len(prim_buttons), 5, "Should find exactly 5 Target prims")
        for i in range(5):
            self.assertIn(f"/World/Target/Mesh_{i}", prim_paths)

        # Verify none from Ignored (proves optimization worked)
        for path in prim_paths:
            self.assertNotIn("Ignored", path, "Should skip entire Ignored subtree")
