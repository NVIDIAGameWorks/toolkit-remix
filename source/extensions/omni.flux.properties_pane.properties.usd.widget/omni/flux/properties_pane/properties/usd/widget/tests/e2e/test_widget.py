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

import carb.input
import omni.kit.clipboard
import omni.kit.undo
import omni.ui as ui
import omni.usd
from omni.flux.property_widget_builder.model.usd import USDAttributeItem as _USDAttributeItem
from omni.flux.properties_pane.properties.usd.widget import PropertyWidget as _PropertyWidget
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import get_test_data_path, open_stage, wait_stage_loading
from pxr import Gf, Sdf

WINDOW_HEIGHT = 1000
WINDOW_WIDTH = 1436

_CONTEXT_NAME = ""


class TestUSDPropertiesWidget(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await open_stage(get_test_data_path(__name__, "usd/cubes.usda"))

    # After running each test
    async def tearDown(self):
        # Note: this func seems to be context independent (same val for both contexts)
        await wait_stage_loading()

    async def __setup_widget(self, width=WINDOW_WIDTH, height=WINDOW_HEIGHT) -> (ui.Window, "_PropertyWidget"):
        window = ui.Window("TestPropertyWidget", width=width, height=height)
        with window.frame:
            with omni.ui.HStack():
                widget1 = _PropertyWidget(_CONTEXT_NAME)

        await ui_test.human_delay(human_delay_speed=1)

        return window, widget1

    async def __destroy(self, window, widget):
        # if we destroy viewports before the stage is fully loaded than it will be stuck in loading state.
        await wait_stage_loading()

        widget.destroy()
        window.destroy()

    @staticmethod
    def __find_item_by_attribute_path(widget: "_PropertyWidget", attribute_path: str) -> _USDAttributeItem | None:
        for item in widget.property_model.get_all_items(include_hidden=True):
            if not isinstance(item, _USDAttributeItem):
                continue
            for path in item.attribute_paths:
                if str(path) == attribute_path:
                    return item
        return None

    async def test_setting_a_value_by_script_update_ui(self):
        """
        Test that if we set a value not from the UI (for example here, directly in USD), check that the UI is updated
        """
        # setup
        _window, _widget = await self.__setup_widget()  # Keep in memory during test
        _widget.refresh(["/Xform/Cube"])

        # find the translate field UI
        property_branches = ui_test.find_all(
            f"{_window.title}//Frame/**/FloatBoundedDrag[*].identifier=='/Xform/Cube.xformOp:translate,/Xform/Cube.xformOp:translate,/Xform/Cube.xformOp:translate'"
        )
        self.assertEqual(len(property_branches), 3)

        # Set the value of the cube and wait for the listener-driven rebuild.
        usd_context = omni.usd.get_context(_CONTEXT_NAME)
        stage = usd_context.get_stage()
        prim = stage.GetPrimAtPath("/Xform/Cube")
        xf_tr = prim.GetAttribute("xformOp:translate")
        xf_tr.Set(Gf.Vec3d(123456789.0, 0.0, 0.0))
        await omni.kit.ui_test.wait_n_updates(5)

        # Re-query because the property panel rebuilds widgets on USD change.
        property_branches = ui_test.find_all(
            f"{_window.title}//Frame/**/FloatBoundedDrag[*].identifier=='/Xform/Cube.xformOp:translate,/Xform/Cube.xformOp:translate,/Xform/Cube.xformOp:translate'"
        )
        self.assertEqual(len(property_branches), 3)

        # we check that the value of the UI element changed
        self.assertAlmostEqual(property_branches[0].widget.model.get_value_as_float(), 123456789.0, places=5)

        await self.__destroy(_window, _widget)

    async def test_multi_prim_bool_widget(self):
        """
        Test that a property can be edited on multiple prims and that it will be accurately represented.
        """
        # setup
        _window, _widget = await self.__setup_widget()  # Keep in memory during test
        _widget.refresh(["/Xform/Cube", "/Xform/Cube2"])
        await omni.kit.ui_test.wait_n_updates(15)

        double_sided_widget = ui_test.find(
            f"{_window.title}//Frame/**/CheckBox[*].identifier=='/Xform/Cube.doubleSided,/Xform/Cube2.doubleSided'"
        )
        # one cube is double sided and the other is not, so this should be mixed
        self.assertEqual(double_sided_widget.widget.model.is_mixed, True)
        self.assertEqual(double_sided_widget.widget.model.get_value(), True)
        self.assertEqual(double_sided_widget.widget.model.get_value_as_bool(), True)

        # Act: toggle bool widget
        self.assertEqual(double_sided_widget.widget.checked, True)
        await omni.kit.ui_test.emulate_mouse_move(double_sided_widget.position + omni.kit.ui_test.Vec2(3, 3))
        await omni.kit.ui_test.emulate_mouse_click()

        # Re-query because the property panel rebuilds widgets after the USD write.
        double_sided_widget = ui_test.find(
            f"{_window.title}//Frame/**/CheckBox[*].identifier=='/Xform/Cube.doubleSided,/Xform/Cube2.doubleSided'"
        )
        self.assertIsNotNone(double_sided_widget, "CheckBox should still exist after click")
        self.assertEqual(double_sided_widget.widget.checked, False)

        # we check that the value of the UI element changed
        self.assertEqual(double_sided_widget.widget.model.get_value(), False)
        self.assertEqual(double_sided_widget.widget.model.get_value_as_bool(), False)
        self.assertEqual(double_sided_widget.widget.model.is_mixed, False)
        # and that both cubes now have the correct value
        usd_context = omni.usd.get_context(_CONTEXT_NAME)
        stage = usd_context.get_stage()
        for prim_path in ("/Xform/Cube", "/Xform/Cube2"):
            prim = stage.GetPrimAtPath(prim_path)
            xf_tr = prim.GetAttribute("doubleSided")
            self.assertEqual(xf_tr.Get(), False)

        await self.__destroy(_window, _widget)

    async def test_multi_prim_xform_widget(self):
        """
        Test that a property can be edited on multiple prims and that it will be accurately represented.
        """
        # setup
        _window, _widget = await self.__setup_widget()  # Keep in memory during test
        _widget.refresh(["/Xform/Cube", "/Xform/Cube2"])
        await omni.kit.ui_test.wait_n_updates(15)

        # find the translate field UI
        property_branches = ui_test.find_all(
            f"{_window.title}//Frame/**/FloatBoundedDrag[*].identifier=='/Xform/Cube.xformOp:translate,"
            f"/Xform/Cube2.xformOp:translate,/Xform/Cube.xformOp:translate,/Xform/Cube2.xformOp:translate,"
            f"/Xform/Cube.xformOp:translate,/Xform/Cube2.xformOp:translate'"
        )
        self.assertEqual(len(property_branches), 3)
        translate_x_widget = property_branches[0]
        self.assertEqual(translate_x_widget.widget.model.is_mixed, True)
        # Act: click on field, set a value and then click off of it
        await translate_x_widget.double_click()
        await omni.kit.ui_test.emulate_char_press("2.2")
        await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.ENTER)
        await omni.kit.ui_test.wait_n_updates(5)

        # Re-query because the property row may be rebuilt after the edit commits.
        property_branches = ui_test.find_all(
            f"{_window.title}//Frame/**/FloatBoundedDrag[*].identifier=='/Xform/Cube.xformOp:translate,"
            f"/Xform/Cube2.xformOp:translate,/Xform/Cube.xformOp:translate,/Xform/Cube2.xformOp:translate,"
            f"/Xform/Cube.xformOp:translate,/Xform/Cube2.xformOp:translate'"
        )
        self.assertEqual(len(property_branches), 3)

        # we check that the value of the UI element changed
        self.assertAlmostEqual(property_branches[0].widget.model.get_value_as_float(), 2.2, places=5)
        self.assertEqual(property_branches[0].widget.model.is_mixed, False)
        # and that both cubes now have the correct value
        usd_context = omni.usd.get_context(_CONTEXT_NAME)
        stage = usd_context.get_stage()
        for prim_path in ("/Xform/Cube", "/Xform/Cube2"):
            prim = stage.GetPrimAtPath(prim_path)
            xf_tr = prim.GetAttribute("xformOp:translate")
            self.assertEqual(xf_tr.Get(), Gf.Vec3d(2.2, 0.0, 0.0))

        await self.__destroy(_window, _widget)

    async def test_undo_reverts_typed_value_and_refreshes_ui(self):
        """Typing a value then undoing or redoing should keep USD and the UI in sync."""
        # Build the property panel and wait for the float fields to appear.
        _window, _widget = await self.__setup_widget()
        _widget.refresh(["/Xform/Cube"])
        await omni.kit.ui_test.wait_n_updates(15)

        selector = (
            f"{_window.title}//Frame/**/FloatBoundedDrag[*].identifier=="
            f"'/Xform/Cube.xformOp:translate,/Xform/Cube.xformOp:translate,/Xform/Cube.xformOp:translate'"
        )
        widgets = ui_test.find_all(selector)
        self.assertEqual(len(widgets), 3)

        # Capture the original USD value so undo can be validated against the real source of truth.
        usd_context = omni.usd.get_context(_CONTEXT_NAME)
        stage = usd_context.get_stage()
        prim = stage.GetPrimAtPath("/Xform/Cube")
        original_value = prim.GetAttribute("xformOp:translate").Get()

        # Type a new value, commit it, then undo it from the global undo stack.
        await widgets[0].double_click()
        await ui_test.human_delay()
        await omni.kit.ui_test.emulate_char_press("99.5")
        await ui_test.human_delay()
        await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.ENTER)
        await ui_test.human_delay()
        omni.kit.undo.undo()
        await ui_test.human_delay()

        # Re-query because undo can rebuild the property row while the model refreshes.
        self.assertEqual(prim.GetAttribute("xformOp:translate").Get(), original_value)
        widgets = ui_test.find_all(selector)
        self.assertGreater(len(widgets), 0)
        self.assertAlmostEqual(widgets[0].widget.model.get_value_as_float(), original_value[0], places=5)

        # Redo should restore the typed value in both USD and the rebuilt property row.
        omni.kit.undo.redo()
        await ui_test.human_delay()
        widgets = ui_test.find_all(selector)
        self.assertGreater(len(widgets), 0)
        self.assertAlmostEqual(prim.GetAttribute("xformOp:translate").Get()[0], 99.5, places=5)
        self.assertAlmostEqual(widgets[0].widget.model.get_value_as_float(), 99.5, places=5)

        await self.__destroy(_window, _widget)

    async def test_undo_reverts_bool_toggle_and_refreshes_ui(self):
        """Toggling a checkbox then undoing should revert both USD and the UI."""
        # Build the property panel and locate the checkbox bound to doubleSided.
        _window, _widget = await self.__setup_widget()
        _widget.refresh(["/Xform/Cube"])
        await omni.kit.ui_test.wait_n_updates(15)

        selector = f"{_window.title}//Frame/**/CheckBox[*].identifier=='/Xform/Cube.doubleSided'"
        checkbox = ui_test.find(selector)
        self.assertIsNotNone(checkbox)

        # Capture the original USD value so the undo path can be checked against it.
        usd_context = omni.usd.get_context(_CONTEXT_NAME)
        stage = usd_context.get_stage()
        prim = stage.GetPrimAtPath("/Xform/Cube")
        original_value = prim.GetAttribute("doubleSided").Get()

        # Click the checkbox, then undo so both USD and the rebuilt UI must roll back together.
        await omni.kit.ui_test.emulate_mouse_move(checkbox.position + omni.kit.ui_test.Vec2(3, 3))
        await ui_test.human_delay()
        await omni.kit.ui_test.emulate_mouse_click()
        await ui_test.human_delay()

        # The click path should still write through immediately before any undo happens.
        checkbox = ui_test.find(selector)
        self.assertIsNotNone(checkbox)
        self.assertNotEqual(checkbox.widget.checked, original_value)
        self.assertNotEqual(prim.GetAttribute("doubleSided").Get(), original_value)

        omni.kit.undo.undo()
        await ui_test.human_delay()

        # Re-query because checkbox widgets are recreated when the panel refreshes.
        checkbox = ui_test.find(selector)
        self.assertIsNotNone(checkbox)
        self.assertEqual(checkbox.widget.model.get_value_as_bool(), original_value)
        self.assertEqual(checkbox.widget.checked, original_value)
        self.assertEqual(prim.GetAttribute("doubleSided").Get(), original_value)

        await self.__destroy(_window, _widget)

    async def test_drag_float_undo_is_single_operation(self):
        """Dragging a float field should undo as one operation and refresh the UI."""
        # Build the property panel and locate the translate drag widgets.
        _window, _widget = await self.__setup_widget()
        _widget.refresh(["/Xform/Cube"])
        await omni.kit.ui_test.wait_n_updates(15)

        selector = (
            f"{_window.title}//Frame/**/FloatBoundedDrag[*].identifier=="
            f"'/Xform/Cube.xformOp:translate,/Xform/Cube.xformOp:translate,/Xform/Cube.xformOp:translate'"
        )
        widgets = ui_test.find_all(selector)
        self.assertEqual(len(widgets), 3)

        usd_context = omni.usd.get_context(_CONTEXT_NAME)
        stage = usd_context.get_stage()
        prim = stage.GetPrimAtPath("/Xform/Cube")
        original_value = prim.GetAttribute("xformOp:translate").Get()

        # Snapshot the current undo history so the drag can be inspected in isolation.
        latest_history_key = max(omni.kit.undo.get_history().keys(), default=0)

        # Drag the X field far enough to generate multiple intermediate UI updates.
        widget_ref = widgets[0]
        target = widget_ref.center
        target.x = target.x + 200
        await omni.kit.ui_test.human_delay(30)
        await omni.kit.ui_test.emulate_mouse_drag_and_drop(widget_ref.center, target)
        await ui_test.human_delay()

        # The minimal fix should collapse the drag into a single ChangeProperty write.
        drag_history_entries = [entry for key, entry in omni.kit.undo.get_history().items() if key > latest_history_key]
        change_property_entries = [entry for entry in drag_history_entries if entry.name == "ChangeProperty"]
        self.assertEqual(len(change_property_entries), 1)
        self.assertNotEqual(prim.GetAttribute("xformOp:translate").Get()[0], original_value[0])

        # One undo should restore both USD and the property panel value.
        omni.kit.undo.undo()
        await ui_test.human_delay()

        widgets = ui_test.find_all(selector)
        self.assertGreater(len(widgets), 0)
        self.assertAlmostEqual(prim.GetAttribute("xformOp:translate").Get()[0], original_value[0], places=5)
        self.assertAlmostEqual(widgets[0].widget.model.get_value_as_float(), original_value[0], places=5)

        await self.__destroy(_window, _widget)

    async def test_refresh_uses_custom_data_bounds_adapter_for_real_attribute(self):
        """Producer should pass per-attribute customData through bounds_adapter for real USD attrs."""
        # Arrange
        stage = omni.usd.get_context(_CONTEXT_NAME).get_stage()
        prim = stage.GetPrimAtPath("/Xform/Cube")
        attr = prim.CreateAttribute("testBounded", Sdf.ValueTypeNames.Float)
        attr.Set(2.0)
        attr.SetMetadata("customData", {"range": {"min": 1.0, "max": 9.0}, "ui:step": 0.25})

        _window, _widget = await self.__setup_widget()

        # Act
        _widget.refresh(["/Xform/Cube"])
        await omni.kit.ui_test.wait_n_updates(10)
        item = self.__find_item_by_attribute_path(_widget, "/Xform/Cube.testBounded")

        # Assert
        self.assertIsNotNone(item, "Expected bound test item to be present in the property model.")
        self.assertEqual(item.get_min_max_bounds(), (1.0, 9.0, None, None))
        self.assertEqual(item.get_step_value(), 0.25)

        await self.__destroy(_window, _widget)

    async def test_refresh_accepts_custom_data_without_bounds_or_step(self):
        """Missing bounds keys in customData should remain valid and return None bounds/step."""
        # Arrange
        stage = omni.usd.get_context(_CONTEXT_NAME).get_stage()
        prim = stage.GetPrimAtPath("/Xform/Cube")
        attr = prim.CreateAttribute("testNoBoundsMetadata", Sdf.ValueTypeNames.Float)
        attr.Set(5.0)
        attr.SetMetadata("customData", {"author": "unit-test"})

        _window, _widget = await self.__setup_widget()

        # Act
        _widget.refresh(["/Xform/Cube"])
        await omni.kit.ui_test.wait_n_updates(10)
        item = self.__find_item_by_attribute_path(_widget, "/Xform/Cube.testNoBoundsMetadata")

        # Assert
        self.assertIsNotNone(item, "Expected no-bounds test item to be present in the property model.")
        self.assertIsNone(item.get_min_max_bounds())
        self.assertIsNone(item.get_step_value())

        await self.__destroy(_window, _widget)

    async def test_refresh_intersects_bounds_for_multi_selected_real_attributes(self):
        """Multi-selection should merge real-attribute customData into one safe intersected adapter payload."""
        # Arrange
        stage = omni.usd.get_context(_CONTEXT_NAME).get_stage()
        cube = stage.GetPrimAtPath("/Xform/Cube")
        cube2 = stage.GetPrimAtPath("/Xform/Cube2")

        cube_attr = cube.CreateAttribute("testMultiBounds", Sdf.ValueTypeNames.Float)
        cube_attr.Set(2.0)
        cube_attr.SetMetadata("customData", {"range": {"min": 1.0, "max": 4.0}, "ui:step": 0.5})

        cube2_attr = cube2.CreateAttribute("testMultiBounds", Sdf.ValueTypeNames.Float)
        cube2_attr.Set(3.0)
        cube2_attr.SetMetadata("customData", {"range": {"min": -3.0, "max": 10.0}, "ui:step": 1.5})

        _window, _widget = await self.__setup_widget()

        # Act
        _widget.refresh(["/Xform/Cube", "/Xform/Cube2"])
        await omni.kit.ui_test.wait_n_updates(10)
        item = self.__find_item_by_attribute_path(_widget, "/Xform/Cube.testMultiBounds")

        # Assert
        self.assertIsNotNone(item, "Expected merged multi-select bounds item to be present.")
        self.assertEqual(item.get_min_max_bounds(), (1.0, 4.0, None, None))
        self.assertEqual(item.get_step_value(), 1.5)

        await self.__destroy(_window, _widget)

    async def test_refresh_preserves_vector_bounds_for_single_selected_real_attribute(self):
        """Single selection should pass through vector range metadata unchanged."""
        # Arrange
        stage = omni.usd.get_context(_CONTEXT_NAME).get_stage()
        prim = stage.GetPrimAtPath("/Xform/Cube")
        attr = prim.CreateAttribute("testVectorBounds", Sdf.ValueTypeNames.Float2)
        attr.Set(Gf.Vec2f(2.0, 3.0))
        attr.SetMetadata("customData", {"range": {"min": Gf.Vec2f(1.0, 2.0), "max": Gf.Vec2f(4.0, 9.0)}})

        _window, _widget = await self.__setup_widget()

        # Act
        _widget.refresh(["/Xform/Cube"])
        await omni.kit.ui_test.wait_n_updates(10)
        item = self.__find_item_by_attribute_path(_widget, "/Xform/Cube.testVectorBounds")

        # Assert
        self.assertIsNotNone(item, "Expected vector-bounds test item to be present in the property model.")
        self.assertEqual(item.get_min_max_bounds(), (Gf.Vec2f(1.0, 2.0), Gf.Vec2f(4.0, 9.0), None, None))
        self.assertIsNone(item.get_step_value())

        await self.__destroy(_window, _widget)
