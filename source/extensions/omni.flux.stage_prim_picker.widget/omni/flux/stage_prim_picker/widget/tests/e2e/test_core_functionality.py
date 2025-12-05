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

import asyncio
import random

import omni.kit.app
import omni.kit.test
import omni.kit.ui_test as ui_test
import omni.ui as ui
import omni.usd
from omni.flux.stage_prim_picker.widget import StagePrimPickerField
from pxr import UsdGeom


class MockValueModel(ui.AbstractValueModel):
    """Mock value model for testing."""

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
    """Mock item for field builder testing."""

    def __init__(self, name: str, value: str = ""):
        self.name = name
        self.element_count = 1
        self.value_models = [MockValueModel(value)]


class TestCoreFunctionality(omni.kit.test.AsyncTestCase):
    """Critical functionality tests."""

    async def setUp(self):
        # ARRANGE - Fresh USD context for each test
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()
        self._test_window = None
        self._picker = None
        # Unique identifier per test to prevent window conflicts between tests
        self._test_id = f"test_{random.randint(10000, 99999)}"

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

    async def test_select_prim_from_populated_stage(self):
        """C1: Basic prim selection updates value model correctly."""
        # ARRANGE - Create stage with known prims
        UsdGeom.Xform.Define(self.stage, "/World")
        UsdGeom.Mesh.Define(self.stage, "/World/Cube")
        UsdGeom.Sphere.Define(self.stage, "/World/Sphere")

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            self._picker = StagePrimPickerField(identifier=self._test_id)
            item = MockItem("test_prim_path")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT - Open dropdown
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='{self._test_id}_button'"
        )
        self.assertIsNotNone(dropdown_button, "Dropdown button must exist")
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ACT - Click a prim (search in dropdown window using unique ID)
        dropdown_id = f"StagePrimPickerDropdown_{self._test_id}_0"
        prim_buttons = ui_test.find_all(f"{dropdown_id}//Frame/**/Button[*].name=='StagePrimPickerItem'")
        self.assertGreater(len(prim_buttons), 0, "Should have prim buttons")

        cube_button = next((b for b in prim_buttons if "/World/Cube" in b.widget.text), None)
        self.assertIsNotNone(cube_button, "Cube button must exist")
        await cube_button.click()
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Value model updated
        self.assertEqual(item.value_models[0].get_value_as_string(), "/World/Cube")

    async def test_empty_stage_shows_no_prims_message(self):
        """C1: Empty stage displays appropriate message."""
        # ARRANGE - Empty stage
        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            self._picker = StagePrimPickerField(identifier=self._test_id)
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT - Open dropdown
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='{self._test_id}_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - No prims message appears (search in unique dropdown window)
        dropdown_id = f"StagePrimPickerDropdown_{self._test_id}_0"
        no_prims_label = ui_test.find(f"{dropdown_id}//Frame/**/Label[*].text=='No prims found'")
        self.assertIsNotNone(no_prims_label, "Should show 'No prims found' message")

        # ASSERT - No prim buttons exist
        prim_buttons = ui_test.find_all(f"{dropdown_id}//Frame/**/Button[*].name=='StagePrimPickerItem'")
        self.assertEqual(len(prim_buttons), 0, "Should have no prim buttons")

    async def test_search_filters_results_after_debounce(self):
        """C2: Search filters prims after 300ms debounce."""
        # ARRANGE - Stage with searchable prims
        UsdGeom.Xform.Define(self.stage, "/World")
        UsdGeom.Mesh.Define(self.stage, "/World/UniqueCube")
        UsdGeom.Sphere.Define(self.stage, "/World/Sphere")
        UsdGeom.Cylinder.Define(self.stage, "/World/Cylinder")

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            self._picker = StagePrimPickerField(identifier=self._test_id)
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT - Open dropdown
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='{self._test_id}_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ACT - Type in search field (in unique dropdown window)
        dropdown_id = f"StagePrimPickerDropdown_{self._test_id}_0"
        search_field = ui_test.find(f"{dropdown_id}//Frame/**/StringField[*].name=='StagePrimPickerSearch'")
        self.assertIsNotNone(search_field, "Search field must exist")
        search_field.widget.model.set_value("UniqueCube")

        # Wait for debounce (300ms) + processing
        await asyncio.sleep(0.4)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Only matching prim appears (in unique dropdown window)
        prim_buttons = ui_test.find_all(f"{dropdown_id}//Frame/**/Button[*].name=='StagePrimPickerItem'")
        self.assertEqual(len(prim_buttons), 1, "Should filter to 1 matching prim")
        self.assertIn("UniqueCube", prim_buttons[0].widget.text)

    async def test_pagination_loads_only_initial_items(self):
        """C3: Pagination loads initial_items, not all prims."""
        # ARRANGE - Stage with 100 prims
        UsdGeom.Xform.Define(self.stage, "/World")
        for i in range(100):
            UsdGeom.Mesh.Define(self.stage, f"/World/Mesh_{i:03d}")

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            self._picker = StagePrimPickerField(identifier=self._test_id, initial_items=20)
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT - Open dropdown
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='{self._test_id}_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Only 20 prims loaded (in unique dropdown window)
        dropdown_id = f"StagePrimPickerDropdown_{self._test_id}_0"
        prim_buttons = ui_test.find_all(f"{dropdown_id}//Frame/**/Button[*].name=='StagePrimPickerItem'")
        self.assertEqual(len(prim_buttons), 20, "Should load exactly 20 prims, not all 100")

        # ASSERT - "Show more" button exists
        show_more = ui_test.find(f"{dropdown_id}//Frame/**/Button[*].name=='StagePrimPickerFieldShowMore'")
        self.assertIsNotNone(show_more, "Show more button must appear when more prims exist")

    async def test_show_more_loads_additional_page(self):
        """C3: Show more button loads page_size additional prims."""
        # ARRANGE - Stage with 100 prims
        UsdGeom.Xform.Define(self.stage, "/World")
        for i in range(100):
            UsdGeom.Mesh.Define(self.stage, f"/World/Mesh_{i:03d}")

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            self._picker = StagePrimPickerField(identifier=self._test_id, initial_items=20, page_size=15)
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='{self._test_id}_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Initially 20 items (use unique dropdown ID to avoid conflicts)
        dropdown_id = f"StagePrimPickerDropdown_{self._test_id}_0"
        prim_buttons_before = ui_test.find_all(f"{dropdown_id}//Frame/**/Button[*].name=='StagePrimPickerItem'")
        self.assertEqual(len(prim_buttons_before), 20, "Should have 20 items initially")

        # ACT - Scroll to bottom so "Show more" button is clickable
        scroll_frame = ui_test.find(f"{dropdown_id}//Frame/**/ScrollingFrame[*]")
        if scroll_frame:
            scroll_frame.widget.scroll_y = 1.0
            await omni.kit.app.get_app().next_update_async()

        # ACT - Click "Show more" button
        show_more = ui_test.find(f"{dropdown_id}//Frame/**/Button[*].name=='StagePrimPickerFieldShowMore'")
        show_more.widget.call_clicked_fn()

        # Wait for async rebuild (container.clear() + repopulate in async task)
        await asyncio.sleep(0.15)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Re-query after rebuild to get fresh widget references
        prim_buttons_after = ui_test.find_all(f"{dropdown_id}//Frame/**/Button[*].name=='StagePrimPickerItem'")
        self.assertEqual(
            len(prim_buttons_after),
            35,
            "Should have 20 + 15 = 35 prims after 'Show more'",
        )

    async def test_value_model_updates_bidirectionally(self):
        """C4: Value model syncs from widget to model and model to widget."""
        # ARRANGE
        UsdGeom.Mesh.Define(self.stage, "/World/TestMesh")

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            self._picker = StagePrimPickerField(identifier=self._test_id)
            item = MockItem("test", "/World/TestMesh")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Button shows initial value
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='{self._test_id}_button'"
        )
        self.assertIn(
            "/World/TestMesh",
            dropdown_button.widget.model.get_value_as_string(),
            "Button should show initial value",
        )

        # ACT - Change value externally
        item.value_models[0].set_value("/World/NewValue")
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Button updates
        self.assertIn(
            "/World/NewValue",
            dropdown_button.widget.model.get_value_as_string(),
            "Button should reflect model changes",
        )

    async def test_clear_button_clears_selection(self):
        """C1: Clear button (X) resets value to empty."""
        # ARRANGE
        UsdGeom.Mesh.Define(self.stage, "/World/Cube")

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            self._picker = StagePrimPickerField(identifier=self._test_id)
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT - Select a prim first
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='{self._test_id}_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        dropdown_id = f"StagePrimPickerDropdown_{self._test_id}_0"
        prim_buttons = ui_test.find_all(f"{dropdown_id}//Frame/**/Button[*].name=='StagePrimPickerItem'")
        self.assertGreater(len(prim_buttons), 0, "Should have prim buttons")
        await prim_buttons[0].click()
        await omni.kit.app.get_app().next_update_async()

        self.assertNotEqual(item.value_models[0].get_value_as_string(), "", "Value should be set")

        # ACT - Click clear button (in main window, not dropdown)
        clear_button = ui_test.find(f"{self._test_window.title}//Frame/**/Image[*].name=='StagePrimPickerClear'")
        self.assertIsNotNone(clear_button, "Clear button should be visible when value is set")
        self.assertTrue(clear_button.widget.visible, "Clear button must be visible")

        await clear_button.click()
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Value cleared
        self.assertEqual(item.value_models[0].get_value_as_string(), "", "Value should be cleared")

        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='{self._test_id}_button'"
        )
        self.assertIn(
            "Select a prim",
            dropdown_button.widget.model.get_value_as_string(),
            "Button should show placeholder text",
        )

    async def test_single_prim_stage(self):
        """C1: Edge case - stage with only one prim."""
        # ARRANGE
        UsdGeom.Mesh.Define(self.stage, "/OnlyPrim")

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            self._picker = StagePrimPickerField(identifier=self._test_id)
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='{self._test_id}_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - One prim appears (in unique dropdown window)
        dropdown_id = f"StagePrimPickerDropdown_{self._test_id}_0"
        prim_buttons = ui_test.find_all(f"{dropdown_id}//Frame/**/Button[*].name=='StagePrimPickerItem'")
        self.assertEqual(len(prim_buttons), 1, "Should show exactly 1 prim")
        self.assertIn("/OnlyPrim", prim_buttons[0].widget.text)

        # ASSERT - "Show more" container is hidden for single prim (no more prims to load)
        show_more_container = ui_test.find(
            f"{dropdown_id}//Frame/**/VStack[*].name=='StagePrimPickerShowMoreContainer'"
        )
        self.assertIsNotNone(show_more_container, "Show more container should exist")
        self.assertFalse(show_more_container.widget.visible, "'Show more' should be hidden for single prim")

    async def test_usd_context_isolation(self):
        """C5: Widget respects specified USD context."""
        # ARRANGE - Default context
        default_context = omni.usd.get_context("")
        await default_context.new_stage_async()
        default_stage = default_context.get_stage()
        UsdGeom.Mesh.Define(default_stage, "/DefaultPrim")

        self._test_window = ui.Window("Test", width=300, height=200)
        self._test_window.position_x = 100
        self._test_window.position_y = 100
        with self._test_window.frame:
            self._picker = StagePrimPickerField(identifier=self._test_id, context_name="")
            item = MockItem("test")
            self._picker.build_ui(item)

        await omni.kit.app.get_app().next_update_async()

        # ACT
        dropdown_button = ui_test.find(
            f"{self._test_window.title}//Frame/**/StringField[*].identifier=='{self._test_id}_button'"
        )
        dropdown_button.widget.call_mouse_pressed_fn(0, 0, 0, 0)
        await omni.kit.app.get_app().next_update_async()

        # ASSERT - Shows prim from correct context (in unique dropdown window)
        dropdown_id = f"StagePrimPickerDropdown_{self._test_id}_0"
        prim_buttons = ui_test.find_all(f"{dropdown_id}//Frame/**/Button[*].name=='StagePrimPickerItem'")
        prim_texts = [b.widget.text for b in prim_buttons]
        self.assertIn("/DefaultPrim", prim_texts, "Should show prim from default context")

        # Clean up default context stage before tearDown to avoid conflict
        await default_context.close_stage_async()
        await omni.kit.app.get_app().next_update_async()
