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
import omni.appwindow
import omni.kit.clipboard
import omni.kit.undo
import omni.ui as ui
import omni.usd
from omni.flux.property_widget_builder.model.usd import USDAttributeItem as _USDAttributeItem
from omni.flux.properties_pane.properties.usd.widget import PropertyWidget as _PropertyWidget
from omni.flux.utils.common.interactive_usd_notices import register_objects_changed_listener as _register_listener
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
        await ui_test.human_delay()

    @staticmethod
    def __find_item_by_attribute_path(widget: "_PropertyWidget", attribute_path: str) -> _USDAttributeItem | None:
        for item in widget.property_model.get_all_items(include_hidden=True):
            if not isinstance(item, _USDAttributeItem):
                continue
            for path in item.attribute_paths:
                if str(path) == attribute_path:
                    return item
        return None

    @staticmethod
    async def __press_keyboard_key(key: carb.input.KeyboardInput) -> None:
        await omni.kit.ui_test.emulate_keyboard_press(key)
        await omni.kit.ui_test.wait_n_updates(1)

    @staticmethod
    async def __type_text(text: str) -> None:
        for char in text:
            await omni.kit.ui_test.emulate_char_press(char)
            await omni.kit.ui_test.wait_n_updates(1)

    @staticmethod
    def __find_selected_visible_string_field(window_title: str):
        for field in ui_test.find_all(f"{window_title}//Frame/**/StringField[*]"):
            if field.widget.visible and field.widget.selected:
                return field
        return None

    def __assert_visible_numeric_editor_text(self, window_title: str, target_widget, expected_value: float) -> None:
        field = self.__find_selected_visible_string_field(window_title)
        self.assertIsNotNone(field)
        text = field.widget.model.get_value_as_string().strip()
        self.assertNotEqual(text, "")
        self.assertAlmostEqual(float(text), expected_value, places=5)
        self.assertAlmostEqual(target_widget.widget.model.get_value_as_float(), expected_value, places=5)

    def __assert_visible_numeric_editor_target(self, window_title: str, target_widget) -> None:
        field = self.__find_selected_visible_string_field(window_title)
        self.assertIsNotNone(field)
        self.assertLessEqual(abs(field.center.x - target_widget.center.x), target_widget.widget.computed_width / 2)
        self.assertLessEqual(abs(field.center.y - target_widget.center.y), target_widget.widget.computed_height / 2)

    def __find_xform_widgets(self, window_title: str, xform_op_name: str):
        attribute_path = f"/Xform/Cube.xformOp:{xform_op_name}"
        widgets = ui_test.find_all(
            f"{window_title}//Frame/**/FloatBoundedDrag[*].identifier=="
            f"'{attribute_path},{attribute_path},{attribute_path}'"
        )
        self.assertEqual(len(widgets), 3)
        return widgets

    def __find_translate_widgets(self, window_title: str):
        return self.__find_xform_widgets(window_title, "translate")

    async def test_setting_a_value_by_script_update_ui(self):
        """
        Test that if we set a value not from the UI (for example here, directly in USD), check that the UI is updated
        """
        # setup
        _window, _widget = await self.__setup_widget()  # Keep in memory during test
        _widget.refresh(["/Xform/Cube"])

        # find the translate field UI
        property_branches = self.__find_translate_widgets(_window.title)

        # Set the value of the cube and wait for the listener-driven rebuild.
        usd_context = omni.usd.get_context(_CONTEXT_NAME)
        stage = usd_context.get_stage()
        prim = stage.GetPrimAtPath("/Xform/Cube")
        xf_tr = prim.GetAttribute("xformOp:translate")
        xf_tr.Set(Gf.Vec3d(123456789.0, 0.0, 0.0))
        await omni.kit.ui_test.wait_n_updates(5)

        # Re-query because the property panel rebuilds widgets on USD change.
        property_branches = self.__find_translate_widgets(_window.title)

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
        usd_context = omni.usd.get_context(_CONTEXT_NAME)
        stage = usd_context.get_stage()
        expected_last_selected_value = stage.GetPrimAtPath("/Xform/Cube2").GetAttribute("doubleSided").Get()
        self.assertEqual(double_sided_widget.widget.model.is_mixed, True)
        self.assertEqual(double_sided_widget.widget.model.get_value(), expected_last_selected_value)
        self.assertEqual(double_sided_widget.widget.model.get_value_as_bool(), expected_last_selected_value)

        # Act: toggle bool widget
        self.assertEqual(double_sided_widget.widget.checked, expected_last_selected_value)
        await omni.kit.ui_test.emulate_mouse_move(double_sided_widget.position + omni.kit.ui_test.Vec2(3, 3))
        await omni.kit.ui_test.emulate_mouse_click()

        # Re-query because the property panel rebuilds widgets after the USD write.
        double_sided_widget = ui_test.find(
            f"{_window.title}//Frame/**/CheckBox[*].identifier=='/Xform/Cube.doubleSided,/Xform/Cube2.doubleSided'"
        )
        self.assertIsNotNone(double_sided_widget, "CheckBox should still exist after click")
        self.assertEqual(double_sided_widget.widget.checked, True)

        # we check that the value of the UI element changed
        self.assertEqual(double_sided_widget.widget.model.get_value(), True)
        self.assertEqual(double_sided_widget.widget.model.get_value_as_bool(), True)
        self.assertEqual(double_sided_widget.widget.model.is_mixed, False)
        # and that both cubes now have the correct value
        usd_context = omni.usd.get_context(_CONTEXT_NAME)
        stage = usd_context.get_stage()
        for prim_path in ("/Xform/Cube", "/Xform/Cube2"):
            prim = stage.GetPrimAtPath(prim_path)
            xf_tr = prim.GetAttribute("doubleSided")
            self.assertEqual(xf_tr.Get(), True)

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
        usd_context = omni.usd.get_context(_CONTEXT_NAME)
        stage = usd_context.get_stage()
        expected_last_selected_translate_x = (
            stage.GetPrimAtPath("/Xform/Cube2").GetAttribute("xformOp:translate").Get()[0]
        )
        self.assertEqual(translate_x_widget.widget.model.is_mixed, True)
        self.assertAlmostEqual(
            translate_x_widget.widget.model.get_value_as_float(), expected_last_selected_translate_x, places=5
        )
        # Act: click on field, set a value and then click off of it
        await translate_x_widget.double_click()
        await ui_test.human_delay()
        for _ in range(8):
            await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.BACKSPACE)
        await self.__type_text("2.2")
        await ui_test.human_delay()
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

    async def test_numeric_expression_and_arrow_step_update_usd_during_edit_and_notify_once_on_enter(self):
        """A numeric expression should write immediately; Arrow Up should step from that value."""
        _window, _widget = await self.__setup_widget()
        _widget.refresh(["/Xform/Cube"])
        await omni.kit.ui_test.wait_n_updates(15)

        widgets = self.__find_translate_widgets(_window.title)
        x_step = widgets[0].widget.step

        stage = omni.usd.get_context(_CONTEXT_NAME).get_stage()
        prim = stage.GetPrimAtPath("/Xform/Cube")
        translate_attr = prim.GetAttribute("xformOp:translate")
        notices = []
        subscription = _register_listener(stage, lambda notice, stage: notices.append((notice, stage)))
        try:
            # Type a math expression into translate X; USD should update while the edit is still active.
            await widgets[0].double_click()
            await omni.kit.ui_test.wait_n_updates(2)
            await self.__type_text("2*100")
            await omni.kit.ui_test.wait_n_updates(5)
            self.assertAlmostEqual(translate_attr.Get()[0], 200.0, places=5)
            self.assertEqual(len(notices), 0)

            # Arrow Up steps from the evaluated expression without ending the grouped edit.
            await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.UP)
            await omni.kit.ui_test.wait_n_updates(5)
            self.assertAlmostEqual(translate_attr.Get()[0], 200.0 + x_step, places=5)
            self.assertEqual(len(notices), 0)

            # Pressing Enter ends the edit, normalizes the field text, and emits one refresh.
            await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.ENTER)
            await omni.kit.ui_test.wait_n_updates(5)

            self.assertEqual(len(notices), 1)
            widgets = self.__find_translate_widgets(_window.title)
            self.assertAlmostEqual(widgets[0].widget.model.get_value_as_float(), 200.0 + x_step, places=5)
        finally:
            subscription.Revoke()
            await self.__destroy(_window, _widget)

    async def test_double_click_numeric_field_selects_existing_value_for_replacement(self):
        """Double-clicking a numeric field should show the existing value selected for replacement."""
        _window, _widget = await self.__setup_widget()
        _widget.refresh(["/Xform/Cube"])
        await omni.kit.ui_test.wait_n_updates(15)

        widgets = self.__find_translate_widgets(_window.title)

        stage = omni.usd.get_context(_CONTEXT_NAME).get_stage()
        prim = stage.GetPrimAtPath("/Xform/Cube")
        translate_attr = prim.GetAttribute("xformOp:translate")
        original_value = translate_attr.Get()

        try:
            # Double-click into X and verify the editor is pre-filled with the current value.
            await widgets[0].double_click()
            await omni.kit.ui_test.wait_n_updates(2)
            self.__assert_visible_numeric_editor_text(_window.title, widgets[0], original_value[0])

            # Typing should replace the selected value immediately, not append to it.
            await self.__type_text("12")
            await omni.kit.ui_test.wait_n_updates(5)
            self.assertEqual(translate_attr.Get(), Gf.Vec3d(12.0, original_value[1], original_value[2]))
        finally:
            await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.ENTER)
            await self.__destroy(_window, _widget)

    async def test_tabbing_vector_fields_loops_and_keeps_arrow_edit_text_visible(self):
        """Tabbing through X/Y/Z/X then stepping with arrows should keep active editor text visible."""
        _window, _widget = await self.__setup_widget()
        _widget.refresh(["/Xform/Cube"])
        await omni.kit.ui_test.wait_n_updates(15)

        widgets = self.__find_translate_widgets(_window.title)
        x_step = widgets[0].widget.step
        y_step = widgets[1].widget.step
        z_step = widgets[2].widget.step

        stage = omni.usd.get_context(_CONTEXT_NAME).get_stage()
        prim = stage.GetPrimAtPath("/Xform/Cube")
        translate_attr = prim.GetAttribute("xformOp:translate")
        original_value = translate_attr.Get()
        notices = []
        subscription = _register_listener(stage, lambda notice, stage: notices.append((notice, stage)))

        try:
            # Start on X, then step it once.
            await widgets[0].double_click()
            await omni.kit.ui_test.wait_n_updates(2)
            await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.UP)
            await omni.kit.ui_test.wait_n_updates(5)
            self.__assert_visible_numeric_editor_text(_window.title, widgets[0], original_value[0] + x_step)

            # Tab to Y and step Y while keeping the edit session open.
            await self.__press_keyboard_key(carb.input.KeyboardInput.TAB)
            await omni.kit.ui_test.wait_n_updates(5)
            self.__assert_visible_numeric_editor_text(_window.title, widgets[1], original_value[1])

            await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.UP)
            await omni.kit.ui_test.wait_n_updates(5)
            self.__assert_visible_numeric_editor_text(_window.title, widgets[1], original_value[1] + y_step)

            # Tab to Z and step Z down.
            await self.__press_keyboard_key(carb.input.KeyboardInput.TAB)
            await omni.kit.ui_test.wait_n_updates(5)
            self.__assert_visible_numeric_editor_text(_window.title, widgets[2], original_value[2])

            await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.DOWN)
            await omni.kit.ui_test.wait_n_updates(5)
            self.__assert_visible_numeric_editor_text(_window.title, widgets[2], original_value[2] - z_step)

            # Tabbing after Z should loop back to X instead of leaving an invisible focused field.
            await self.__press_keyboard_key(carb.input.KeyboardInput.TAB)
            await omni.kit.ui_test.wait_n_updates(5)
            self.__assert_visible_numeric_editor_text(_window.title, widgets[0], original_value[0] + x_step)

            await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.UP)
            await omni.kit.ui_test.wait_n_updates(5)
            self.__assert_visible_numeric_editor_text(_window.title, widgets[0], original_value[0] + (2 * x_step))

            # Continue the X/Y/Z/X loop to prove field text stays visible through repeated Tabs.
            await self.__press_keyboard_key(carb.input.KeyboardInput.TAB)
            await omni.kit.ui_test.wait_n_updates(5)
            self.__assert_visible_numeric_editor_text(_window.title, widgets[1], original_value[1] + y_step)

            await self.__press_keyboard_key(carb.input.KeyboardInput.TAB)
            await omni.kit.ui_test.wait_n_updates(5)
            self.__assert_visible_numeric_editor_text(_window.title, widgets[2], original_value[2] - z_step)

            await self.__press_keyboard_key(carb.input.KeyboardInput.TAB)
            await omni.kit.ui_test.wait_n_updates(5)
            self.__assert_visible_numeric_editor_text(_window.title, widgets[0], original_value[0] + (2 * x_step))

            # Move the mouse away from X, then hold Arrow Up; the focused X field should keep stepping.
            await ui_test.emulate_mouse_move(widgets[1].position + ui_test.Vec2(3, 3))
            keyboard = omni.appwindow.get_default_app_window().get_keyboard()
            input_provider = carb.input.acquire_input_provider()
            input_provider.buffer_keyboard_key_event(
                keyboard, carb.input.KeyboardEventType.KEY_PRESS, carb.input.KeyboardInput.UP, 0
            )
            for _ in range(8):
                input_provider.buffer_keyboard_key_event(
                    keyboard, carb.input.KeyboardEventType.KEY_REPEAT, carb.input.KeyboardInput.UP, 0
                )
                await omni.kit.ui_test.wait_n_updates(1)
            input_provider.buffer_keyboard_key_event(
                keyboard, carb.input.KeyboardEventType.KEY_RELEASE, carb.input.KeyboardInput.UP, 0
            )
            await omni.kit.ui_test.wait_n_updates(5)
            self.__assert_visible_numeric_editor_text(_window.title, widgets[0], original_value[0] + (11 * x_step))

            # The grouped edit should not notify Stage Manager until the user commits it.
            self.assertEqual(
                translate_attr.Get(),
                Gf.Vec3d(original_value[0] + (11 * x_step), original_value[1] + y_step, original_value[2] - z_step),
            )
            self.assertEqual(len(notices), 0)
            input_provider.buffer_keyboard_key_event(
                keyboard, carb.input.KeyboardEventType.KEY_PRESS, carb.input.KeyboardInput.ENTER, 0
            )
            input_provider.buffer_keyboard_key_event(
                keyboard, carb.input.KeyboardEventType.KEY_RELEASE, carb.input.KeyboardInput.ENTER, 0
            )
            await omni.kit.ui_test.wait_n_updates(5)
            self.assertEqual(len(notices), 1)
        finally:
            subscription.Revoke()
            await self.__destroy(_window, _widget)

    async def test_ctrl_click_middle_xform_field_targets_that_row_and_loops(self):
        """Ctrl+clicking a different xform row's middle field should edit that field and loop in that row."""
        _window, _widget = await self.__setup_widget()
        _widget.refresh(["/Xform/Cube"])
        await omni.kit.ui_test.wait_n_updates(15)

        translate_widgets = self.__find_translate_widgets(_window.title)
        scale_widgets = self.__find_xform_widgets(_window.title, "scale")
        y_step = scale_widgets[1].widget.step
        z_step = scale_widgets[2].widget.step
        x_step = scale_widgets[0].widget.step

        stage = omni.usd.get_context(_CONTEXT_NAME).get_stage()
        prim = stage.GetPrimAtPath("/Xform/Cube")
        translate_attr = prim.GetAttribute("xformOp:translate")
        scale_attr = prim.GetAttribute("xformOp:scale")
        original_translate = translate_attr.Get()
        original_scale = scale_attr.Get()

        try:
            await translate_widgets[0].double_click()
            await omni.kit.ui_test.wait_n_updates(2)
            self.__assert_visible_numeric_editor_text(_window.title, translate_widgets[0], original_translate[0])

            async with omni.kit.ui_test.KeyDownScope(carb.input.KeyboardInput.LEFT_CONTROL):
                await ui_test.emulate_mouse_move(scale_widgets[1].center)
                await omni.kit.ui_test.wait_n_updates(1)
                await ui_test.emulate_mouse_click()
            await omni.kit.ui_test.wait_n_updates(5)
            self.__assert_visible_numeric_editor_target(_window.title, scale_widgets[1])
            self.__assert_visible_numeric_editor_text(_window.title, scale_widgets[1], original_scale[1])

            await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.UP)
            await omni.kit.ui_test.wait_n_updates(5)
            self.__assert_visible_numeric_editor_target(_window.title, scale_widgets[1])
            self.__assert_visible_numeric_editor_text(_window.title, scale_widgets[1], original_scale[1] + y_step)
            self.assertEqual(translate_attr.Get(), original_translate)

            await self.__press_keyboard_key(carb.input.KeyboardInput.TAB)
            await omni.kit.ui_test.wait_n_updates(5)
            self.__assert_visible_numeric_editor_target(_window.title, scale_widgets[2])
            self.__assert_visible_numeric_editor_text(_window.title, scale_widgets[2], original_scale[2])

            await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.UP)
            await omni.kit.ui_test.wait_n_updates(5)
            self.__assert_visible_numeric_editor_text(_window.title, scale_widgets[2], original_scale[2] + z_step)

            await self.__press_keyboard_key(carb.input.KeyboardInput.TAB)
            await omni.kit.ui_test.wait_n_updates(5)
            self.__assert_visible_numeric_editor_target(_window.title, scale_widgets[0])
            self.__assert_visible_numeric_editor_text(_window.title, scale_widgets[0], original_scale[0])

            await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.UP)
            await omni.kit.ui_test.wait_n_updates(5)
            self.__assert_visible_numeric_editor_text(_window.title, scale_widgets[0], original_scale[0] + x_step)
            self.assertEqual(
                scale_attr.Get(),
                Gf.Vec3d(original_scale[0] + x_step, original_scale[1] + y_step, original_scale[2] + z_step),
            )
        finally:
            await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.ENTER)
            await self.__destroy(_window, _widget)

    async def test_double_clicking_scale_y_after_scale_z_edit_targets_only_scale_y(self):
        """Double-clicking scale Y after scale Z should move typed input to Y without editing Z."""
        _window, _widget = await self.__setup_widget()
        _widget.refresh(["/Xform/Cube"])
        await omni.kit.ui_test.wait_n_updates(15)

        scale_widgets = self.__find_xform_widgets(_window.title, "scale")

        stage = omni.usd.get_context(_CONTEXT_NAME).get_stage()
        prim = stage.GetPrimAtPath("/Xform/Cube")
        scale_attr = prim.GetAttribute("xformOp:scale")
        original_scale = scale_attr.Get()
        typed_y_value = 12.25

        try:
            await scale_widgets[2].double_click()
            await omni.kit.ui_test.wait_n_updates(2)
            self.__assert_visible_numeric_editor_target(_window.title, scale_widgets[2])
            self.__assert_visible_numeric_editor_text(_window.title, scale_widgets[2], original_scale[2])

            await scale_widgets[1].double_click()
            await omni.kit.ui_test.wait_n_updates(2)
            self.__assert_visible_numeric_editor_target(_window.title, scale_widgets[1])
            self.__assert_visible_numeric_editor_text(_window.title, scale_widgets[1], original_scale[1])

            await self.__type_text(str(typed_y_value))
            await omni.kit.ui_test.wait_n_updates(5)

            self.__assert_visible_numeric_editor_target(_window.title, scale_widgets[1])
            self.__assert_visible_numeric_editor_text(_window.title, scale_widgets[1], typed_y_value)
            self.assertEqual(scale_attr.Get(), Gf.Vec3d(original_scale[0], typed_y_value, original_scale[2]))
        finally:
            await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.ENTER)
            await self.__destroy(_window, _widget)

    async def test_tab_after_numeric_expression_commits_expression_and_focuses_next_field(self):
        """Tab after a math expression should commit the value and move focus to the next vector field."""
        _window, _widget = await self.__setup_widget()
        _widget.refresh(["/Xform/Cube"])
        await omni.kit.ui_test.wait_n_updates(15)

        widgets = self.__find_translate_widgets(_window.title)

        stage = omni.usd.get_context(_CONTEXT_NAME).get_stage()
        prim = stage.GetPrimAtPath("/Xform/Cube")
        translate_attr = prim.GetAttribute("xformOp:translate")
        original_value = translate_attr.Get()

        try:
            # Type a math expression in X and verify the real USD attribute updates before commit.
            await widgets[0].double_click()
            await omni.kit.ui_test.wait_n_updates(2)
            await self.__type_text("3*10")
            await omni.kit.ui_test.wait_n_updates(5)
            self.assertAlmostEqual(translate_attr.Get()[0], 30.0, places=5)

            # A real Tab key press/release should normalize X and leave Y visibly focused for the next edit.
            await self.__press_keyboard_key(carb.input.KeyboardInput.TAB)
            await omni.kit.ui_test.wait_n_updates(5)
            widgets = self.__find_translate_widgets(_window.title)
            self.assertAlmostEqual(widgets[0].widget.model.get_value_as_float(), 30.0, places=5)
            self.__assert_visible_numeric_editor_text(_window.title, widgets[1], original_value[1])

            # The next typed value should go into Y without requiring a second Tab.
            await self.__type_text("12")
            await omni.kit.ui_test.wait_n_updates(5)
            self.assertEqual(translate_attr.Get(), Gf.Vec3d(30.0, 12.0, original_value[2]))
        finally:
            await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.ENTER)
            await self.__destroy(_window, _widget)

    async def test_repeated_arrow_taps_step_by_exact_float_increment(self):
        """Repeated Arrow Up taps should not write propagated float rounding errors to USD."""
        _window, _widget = await self.__setup_widget()
        _widget.refresh(["/Xform/Cube"])
        await omni.kit.ui_test.wait_n_updates(15)

        widgets = self.__find_translate_widgets(_window.title)
        x_step = widgets[0].widget.step

        stage = omni.usd.get_context(_CONTEXT_NAME).get_stage()
        prim = stage.GetPrimAtPath("/Xform/Cube")
        translate_attr = prim.GetAttribute("xformOp:translate")
        initial_translate = translate_attr.Get()

        try:
            # Repeated real key presses should move by exact step counts, not accumulated binary float noise.
            await widgets[0].double_click()
            await omni.kit.ui_test.wait_n_updates(2)
            for _ in range(84):
                await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.UP)
            await omni.kit.ui_test.wait_n_updates(5)

            value = translate_attr.Get()
            self.assertAlmostEqual(value[0], initial_translate[0] + (84 * x_step), places=5)
            self.assertEqual(value[1], initial_translate[1])
            self.assertEqual(value[2], initial_translate[2])
        finally:
            await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.ENTER)
            await self.__destroy(_window, _widget)

    async def test_undo_reverts_typed_value_and_refreshes_ui(self):
        """Typing a value then undoing or redoing should keep USD and the UI in sync."""
        # Build the property panel and wait for the float fields to appear.
        _window, _widget = await self.__setup_widget()
        _widget.refresh(["/Xform/Cube"])
        await omni.kit.ui_test.wait_n_updates(15)

        widgets = self.__find_translate_widgets(_window.title)

        # Capture the original USD value so undo can be validated against the real source of truth.
        usd_context = omni.usd.get_context(_CONTEXT_NAME)
        stage = usd_context.get_stage()
        prim = stage.GetPrimAtPath("/Xform/Cube")
        original_value = prim.GetAttribute("xformOp:translate").Get()

        # Type a new value, commit it, then undo it from the global undo stack.
        await widgets[0].double_click()
        await ui_test.human_delay()
        await self.__type_text("99.5")
        await ui_test.human_delay()
        await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.ENTER)
        await ui_test.human_delay()
        omni.kit.undo.undo()
        await ui_test.human_delay()

        # Re-query because undo can rebuild the property row while the model refreshes.
        self.assertEqual(prim.GetAttribute("xformOp:translate").Get(), original_value)
        widgets = self.__find_translate_widgets(_window.title)
        self.assertAlmostEqual(widgets[0].widget.model.get_value_as_float(), original_value[0], places=5)

        # Redo should restore the typed value in both USD and the rebuilt property row.
        omni.kit.undo.redo()
        await ui_test.human_delay()
        widgets = self.__find_translate_widgets(_window.title)
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

        widgets = self.__find_translate_widgets(_window.title)

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

        widgets = self.__find_translate_widgets(_window.title)
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
