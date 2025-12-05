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
from pxr import UsdGeom


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


class TestOptimization(omni.kit.test.AsyncTestCase):
    """Optimization validation tests."""

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

    async def test_pagination_prevents_loading_all_prims(self):
        """O1: Pagination limits ensure only initial_items loaded, not entire stage."""
        # ARRANGE - Create 500 prims (enough to prove optimization)
        UsdGeom.Xform.Define(self.stage, "/World")
        for i in range(500):
            UsdGeom.Mesh.Define(self.stage, f"/World/Mesh_{i:03d}")

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            self._picker = StagePrimPickerField(identifier="test_picker", initial_items=25)
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT - Open dropdown
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='test_picker_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Exactly 25 prims loaded, not 500 (in dropdown window)
        prim_buttons = ui_test.find_all(
            "StagePrimPickerDropdown_test_picker_0//Frame/**/Button[*].name=='StagePrimPickerItem'"
        )
        self.assertEqual(
            len(prim_buttons),
            25,
            "Pagination MUST limit to 25 items. If this shows 500, optimization is broken.",
        )

        # ASSERT - "Show more" indicates more prims available
        show_more = ui_test.find(
            "StagePrimPickerDropdown_test_picker_0//Frame/**/Button[*].name=='StagePrimPickerFieldShowMore'"
        )
        self.assertIsNotNone(show_more, "Show more must appear when 475 prims remain")
        self.assertIn("Show more", show_more.widget.text)

    async def test_deep_hierarchy_doesnt_traverse_all_upfront(self):
        """O2: Deep nested prims don't cause full traversal on open."""
        # ARRANGE - Create 20-level deep hierarchy with prims at each level
        UsdGeom.Xform.Define(self.stage, "/World")
        current_path = "/World"

        for level in range(20):
            for i in range(10):  # 10 prims per level = 200 total
                prim_path = f"{current_path}/Level{level}_Prim{i}"
                UsdGeom.Mesh.Define(self.stage, prim_path)
            current_path = f"{current_path}/Level{level}_Prim0"

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            self._picker = StagePrimPickerField(identifier="test_picker", initial_items=30)
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT - Open dropdown (should not hang)
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='test_picker_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Only 30 prims loaded despite 200+ available (in dropdown window)
        prim_buttons = ui_test.find_all(
            "StagePrimPickerDropdown_test_picker_0//Frame/**/Button[*].name=='StagePrimPickerItem'"
        )
        self.assertEqual(
            len(prim_buttons),
            30,
            "Generator must stop at 30, not traverse entire 20-level hierarchy",
        )

    async def test_type_filter_with_large_stage(self):
        """O1: Type filtering still respects pagination limits."""
        # ARRANGE - 1000 prims of mixed types
        UsdGeom.Xform.Define(self.stage, "/World")

        # 500 Meshes, 500 Spheres
        for i in range(500):
            UsdGeom.Mesh.Define(self.stage, f"/World/Mesh_{i:03d}")
        for i in range(500):
            UsdGeom.Sphere.Define(self.stage, f"/World/Sphere_{i:03d}")

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            # Filter to Meshes only, limit to 20
            self._picker = StagePrimPickerField(identifier="test_picker", prim_types=["Mesh"], initial_items=20)
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='test_picker_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Still limited to 20, not all 500 Meshes (in dropdown window)
        prim_buttons = ui_test.find_all(
            "StagePrimPickerDropdown_test_picker_0//Frame/**/Button[*].name=='StagePrimPickerItem'"
        )
        self.assertEqual(
            len(prim_buttons),
            20,
            "Type filter + pagination: should load 20 Meshes, not all 500",
        )

        # ASSERT - All shown prims are Meshes (verify filter worked)
        prim_paths = [b.widget.text for b in prim_buttons]
        for path in prim_paths:
            self.assertIn("Mesh_", path, f"Path {path} should be a Mesh, not Sphere")

    async def test_pagination_reset_on_dropdown_reopen(self):
        """O1: Pagination resets to initial_items when dropdown reopens."""
        # ARRANGE
        UsdGeom.Xform.Define(self.stage, "/World")
        for i in range(100):
            UsdGeom.Mesh.Define(self.stage, f"/World/Mesh_{i:03d}")

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            self._picker = StagePrimPickerField(identifier="test_picker", initial_items=15, page_size=10)
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='test_picker_button'"
        )

        # ACT - Open, load more, close
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        show_more = ui_test.find(
            "StagePrimPickerDropdown_test_picker_0//Frame/**/Button[*].name=='StagePrimPickerFieldShowMore'"
        )
        show_more.widget.call_clicked_fn()
        await omni.kit.app.get_app().next_update_async()
        await omni.kit.app.get_app().next_update_async()

        # Now should have 25 items (in dropdown window)
        prim_buttons = ui_test.find_all(
            "StagePrimPickerDropdown_test_picker_0//Frame/**/Button[*].name=='StagePrimPickerItem'"
        )
        self.assertEqual(len(prim_buttons), 25, "After 'Show more': 15 + 10 = 25")

        # Close dropdown
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ACT - Reopen dropdown
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Reset to 15 items (in dropdown window)
        prim_buttons = ui_test.find_all(
            "StagePrimPickerDropdown_test_picker_0//Frame/**/Button[*].name=='StagePrimPickerItem'"
        )
        self.assertEqual(len(prim_buttons), 15, "Should reset to initial 15 items on reopen")
