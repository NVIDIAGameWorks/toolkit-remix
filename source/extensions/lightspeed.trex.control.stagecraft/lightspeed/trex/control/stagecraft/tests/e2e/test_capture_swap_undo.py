"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from __future__ import annotations

import shutil
from pathlib import Path

import carb.input
import omni.kit.undo
import omni.ui as ui
import omni.usd
from lightspeed.common.constants import GlobalEventNames
from lightspeed.common.constants import WindowNames as _WindowNames
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.contexts.extension import get_instance as _get_context_manager
from lightspeed.trex.contexts.setup import Contexts as _Contexts
from lightspeed.trex.viewports.shared.widget import get_instance as _get_viewport_instance
from omni.flux.utils.tests.context_managers import open_test_project
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.ui_test import Vec2
from pxr import Usd

_ALT_CAPTURE_NAME = "capture_alt.usda"
_UNDO_CAPTURE_CHANGE_DIALOG_TITLE = "Undo Capture Change"
_TEST_SELECTION_PRIM = (
    "/RootNode/instances/inst_BAC90CAA733B0859_0/ref_c89e0497f4ff4dc4a7b70b79c85692da/XForms/Root/Cube"
)
_TEST_EDITOR_PRIM = "/RootNode/meshes/mesh_BAC90CAA733B0859/ref_c89e0497f4ff4dc4a7b70b79c85692da/XForms/Root/Cube_01"
_TEST_EDITOR_LABEL = "Cube_01"


class TestCaptureSwapUndo(AsyncTestCase):
    async def tearDown(self):
        omni.kit.undo.clear_stack()
        omni.kit.undo.clear_history()
        await self._close_open_stage()

    async def test_capture_swap_undo_has_no_ghost_entries_in_real_ui_flow(self):
        self._context_name = _Contexts.STAGE_CRAFT.value
        _get_context_manager().set_current_context(_Contexts.STAGE_CRAFT)
        self._usd_context = omni.usd.get_context(self._context_name)

        omni.kit.undo.clear_stack()
        omni.kit.undo.clear_history()

        async with open_test_project(
            "usd/project_example/combined.usda",
            "lightspeed.trex.app.resources",
            self._context_name,
        ) as temp_project_url:
            await self._close_open_stage()
            temp_project = Path(temp_project_url.path)

            captures_dir = temp_project.parent / "deps" / "captures"
            original_capture_path = captures_dir / "capture.usda"
            replacement_capture_path = captures_dir / _ALT_CAPTURE_NAME
            shutil.copy(original_capture_path, replacement_capture_path)
            replacement_stage = Usd.Stage.Open(str(replacement_capture_path))
            replacement_stage.Save()

            # Load the copied project through the same StageCraft event path a real project-open action uses.
            approvals = _get_event_manager_instance().call_global_custom_event(
                GlobalEventNames.LOAD_PROJECT_PATH.value, str(temp_project)
            )
            self.assertNotIn(False, approvals or [])

            # Wait until StageCraft has finished loading the real workspace layout and the initial capture.
            expected_windows = (
                _WindowNames.VIEWPORT.value,
                _WindowNames.CAPTURES.value,
                _WindowNames.PROPERTIES.value,
                _WindowNames.STAGE_MANAGER.value,
                _WindowNames.SIDEBAR.value,
            )
            for _ in range(120):
                windows = {title: ui.Workspace.get_window(title) for title in expected_windows}
                viewport_widget = _get_viewport_instance(self._context_name)
                if all(window is not None for window in windows.values()) and viewport_widget is not None:
                    break
                await ui_test.wait_n_updates(1)
            else:
                self.fail("StageCraft workspace did not load the expected windows")

            for title in expected_windows:
                ui.Workspace.show_window(title, True)
            await ui_test.wait_n_updates(20)
            await ui_test.human_delay(human_delay_speed=10)

            for _ in range(40):
                if self._get_current_capture_path() == original_capture_path.resolve():
                    break
                await ui_test.human_delay(human_delay_speed=5)
            else:
                self.fail(f"Initial capture layer did not resolve to {original_capture_path.resolve()}")

            # Select the known prim in USD, then wait until the real Properties pane exposes the mesh checkbox.
            self._usd_context.get_selection().clear_selected_prim_paths()
            await ui_test.wait_n_updates(10)
            self._usd_context.get_selection().set_selected_prim_paths([_TEST_SELECTION_PRIM], False)
            await ui_test.wait_n_updates(20)
            await ui_test.human_delay(human_delay_speed=5)

            ui.Workspace.show_window(_WindowNames.PROPERTIES.value, True)
            properties_window = ui.Workspace.get_window(_WindowNames.PROPERTIES.value)
            self.assertIsNotNone(properties_window)
            if hasattr(properties_window, "focus"):
                properties_window.focus()

            checkbox_selector = (
                f"{_WindowNames.PROPERTIES.value}//Frame/**/CheckBox[*].identifier=='{_TEST_EDITOR_PRIM}.doubleSided'"
            )
            for _ in range(80):
                checkbox = ui_test.find(checkbox_selector)
                if checkbox is not None and checkbox.widget.visible:
                    break

                item_prims = [
                    widget
                    for widget in ui_test.find_all(
                        f"{_WindowNames.PROPERTIES.value}//Frame/**/Label[*].identifier=='item_prim'"
                    )
                    if widget.widget.visible
                ]
                if len(item_prims) >= 2:
                    self.assertEqual(_TEST_EDITOR_LABEL, item_prims[-1].widget.text)
                    await item_prims[-1].click()
                    await ui_test.human_delay(human_delay_speed=5)
                else:
                    expand_buttons = [
                        widget
                        for widget in ui_test.find_all(
                            f"{_WindowNames.PROPERTIES.value}//Frame/**/Image[*].identifier=='Expand'"
                        )
                        if widget.widget.visible
                    ]
                    if expand_buttons:
                        await expand_buttons[0].click()
                        await ui_test.human_delay(human_delay_speed=5)
                await ui_test.human_delay(human_delay_speed=5)
            else:
                self.fail(f"Properties pane did not expose {_TEST_EDITOR_PRIM}.doubleSided")

            original_double_sided = self._get_prim_bool_attribute(_TEST_EDITOR_PRIM, "doubleSided")

            # First real user edit: toggle the checkbox in the Properties pane.
            checkbox = ui_test.find(checkbox_selector)
            self.assertIsNotNone(checkbox)
            await ui_test.emulate_mouse_move(checkbox.position + Vec2(3, 3))
            await ui_test.human_delay()
            await ui_test.emulate_mouse_click()
            await ui_test.human_delay()

            for _ in range(80):
                first_toggle_value = self._get_prim_bool_attribute(_TEST_EDITOR_PRIM, "doubleSided")
                if first_toggle_value != original_double_sided:
                    break
                await ui_test.wait_n_updates(2)
            else:
                self.fail("First property toggle did not change the USD value")

            self.assertEqual(1, len(self._get_undo_stack_names()), msg=f"undo_stack={self._get_undo_stack_names()}")

            # Change capture through the visible Captures panel: refresh, hover the item, click the hover window row,
            # then confirm the built-in Load dialog.
            ui.Workspace.show_window(_WindowNames.CAPTURES.value, True)
            captures_window = ui.Workspace.get_window(_WindowNames.CAPTURES.value)
            self.assertIsNotNone(captures_window)
            if hasattr(captures_window, "focus"):
                captures_window.focus()

            refresh_button = None
            for _ in range(40):
                refresh_button = ui_test.find(f"{_WindowNames.CAPTURES.value}//Frame/**/Image[*].name=='Refresh'")
                if refresh_button is not None and refresh_button.widget.visible:
                    break
                await ui_test.human_delay(human_delay_speed=5)
            self.assertIsNotNone(refresh_button)
            await refresh_button.click()
            await ui_test.human_delay(human_delay_speed=5)

            capture_item = None
            for _ in range(80):
                for item in ui_test.find_all(
                    f"{_WindowNames.CAPTURES.value}//Frame/**/Label[*].identifier=='item_title'"
                ):
                    if item.widget.visible and item.widget.text == replacement_capture_path.name:
                        capture_item = item
                        break
                if capture_item is not None:
                    break
                await ui_test.human_delay(human_delay_speed=5)
            self.assertIsNotNone(capture_item)

            await ui_test.emulate_mouse_move(capture_item.position)
            await ui_test.human_delay(human_delay_speed=10)

            for _ in range(40):
                capture_tree_window = ui_test.find("Capture tree window")
                if capture_tree_window is not None and capture_tree_window.widget.visible:
                    break
                await ui_test.human_delay(human_delay_speed=5)
            else:
                self.fail("Capture hover window did not appear")

            hover_capture_item = None
            for _ in range(80):
                for item in ui_test.find_all("Capture tree window//Frame/**/Label[*].identifier=='item_title'"):
                    if item.widget.visible and item.widget.text == replacement_capture_path.name:
                        hover_capture_item = item
                        break
                if hover_capture_item is not None:
                    break
                await ui_test.human_delay(human_delay_speed=5)
            self.assertIsNotNone(hover_capture_item)
            await hover_capture_item.click()
            await ui_test.human_delay(human_delay_speed=5)

            load_button = None
            for _ in range(40):
                for window in ui.Workspace.get_windows():
                    if not isinstance(window, ui.Window) or not window.visible:
                        continue
                    load_query = (
                        f"{window.title}//Frame/**/Button[*].text=='Load'"
                        if window.title
                        else "//Frame/**/Button[*].text=='Load'"
                    )
                    button = ui_test.find(load_query)
                    if button is not None and button.widget.visible:
                        load_button = button
                        break
                if load_button is not None:
                    break
                await ui_test.human_delay(human_delay_speed=5)
            self.assertIsNotNone(load_button)
            await load_button.click()
            await ui_test.human_delay(human_delay_speed=5)

            for _ in range(40):
                if self._get_current_capture_path() == replacement_capture_path.resolve():
                    break
                await ui_test.human_delay(human_delay_speed=5)
            else:
                self.fail(f"Capture layer did not resolve to {replacement_capture_path.resolve()}")

            for _ in range(5):
                await ui_test.wait_n_updates(2)

            # Re-select the same prim after the capture swap and wait for the checkbox to rebuild.
            self._usd_context.get_selection().clear_selected_prim_paths()
            await ui_test.wait_n_updates(10)
            self._usd_context.get_selection().set_selected_prim_paths([_TEST_SELECTION_PRIM], False)
            await ui_test.wait_n_updates(20)
            await ui_test.human_delay(human_delay_speed=5)

            for _ in range(80):
                checkbox = ui_test.find(checkbox_selector)
                if checkbox is not None and checkbox.widget.visible:
                    break

                item_prims = [
                    widget
                    for widget in ui_test.find_all(
                        f"{_WindowNames.PROPERTIES.value}//Frame/**/Label[*].identifier=='item_prim'"
                    )
                    if widget.widget.visible
                ]
                if len(item_prims) >= 2:
                    self.assertEqual(_TEST_EDITOR_LABEL, item_prims[-1].widget.text)
                    await item_prims[-1].click()
                    await ui_test.human_delay(human_delay_speed=5)
                else:
                    expand_buttons = [
                        widget
                        for widget in ui_test.find_all(
                            f"{_WindowNames.PROPERTIES.value}//Frame/**/Image[*].identifier=='Expand'"
                        )
                        if widget.widget.visible
                    ]
                    if expand_buttons:
                        await expand_buttons[0].click()
                        await ui_test.human_delay(human_delay_speed=5)
                await ui_test.human_delay(human_delay_speed=5)
            else:
                self.fail(f"Properties pane did not rebuild {_TEST_EDITOR_PRIM}.doubleSided after capture swap")

            replacement_capture_double_sided = self._get_prim_bool_attribute(_TEST_EDITOR_PRIM, "doubleSided")
            self.assertEqual(2, len(self._get_undo_stack_names()), msg=f"undo_stack={self._get_undo_stack_names()}")
            self.assertEqual("SwitchCaptureCommand", self._get_undo_stack_names()[-1])

            # Second real user edit: toggle the same checkbox after the capture swap.
            checkbox = ui_test.find(checkbox_selector)
            self.assertIsNotNone(checkbox)
            await ui_test.emulate_mouse_move(checkbox.position + Vec2(3, 3))
            await ui_test.human_delay()
            await ui_test.emulate_mouse_click()
            await ui_test.human_delay()

            for _ in range(80):
                second_toggle_value = self._get_prim_bool_attribute(_TEST_EDITOR_PRIM, "doubleSided")
                if second_toggle_value != replacement_capture_double_sided:
                    break
                await ui_test.wait_n_updates(2)
            else:
                self.fail("Second property toggle did not change the USD value")

            # First Ctrl+Z should only revert the second checkbox edit.
            await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.Z, carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
            await ui_test.human_delay(human_delay_speed=5)
            self.assertEqual(replacement_capture_path.resolve(), self._get_current_capture_path())
            self.assertEqual(
                replacement_capture_double_sided,
                self._get_prim_bool_attribute(_TEST_EDITOR_PRIM, "doubleSided"),
            )

            # Second Ctrl+Z must immediately show the capture confirmation dialog.
            await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.Z, carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
            await ui_test.human_delay(human_delay_speed=5)

            for _ in range(40):
                dialog_window = next(
                    (
                        window
                        for window in ui.Workspace.get_windows()
                        if isinstance(window, ui.Window)
                        and window.visible
                        and window.title.startswith(_UNDO_CAPTURE_CHANGE_DIALOG_TITLE)
                    ),
                    None,
                )
                if dialog_window is not None:
                    break
                await ui_test.human_delay(human_delay_speed=5)
            else:
                self.fail("Undo Capture Change dialog did not appear on the second Ctrl+Z")

            change_capture_button = None
            for _ in range(40):
                for button in ui_test.find_all(f"{_UNDO_CAPTURE_CHANGE_DIALOG_TITLE}//Frame/**/Button[*]"):
                    if button.widget.visible and button.widget.text == "Load Capture":
                        change_capture_button = button
                        break
                if change_capture_button is not None:
                    break
                await ui_test.human_delay(human_delay_speed=5)
            self.assertIsNotNone(change_capture_button)
            await change_capture_button.click()
            await ui_test.human_delay(human_delay_speed=5)

            for _ in range(40):
                has_visible_dialog = any(
                    isinstance(window, ui.Window)
                    and window.visible
                    and window.title.startswith(_UNDO_CAPTURE_CHANGE_DIALOG_TITLE)
                    for window in ui.Workspace.get_windows()
                )
                if not has_visible_dialog:
                    break
                await ui_test.human_delay(human_delay_speed=5)
            else:
                self.fail("Undo Capture Change dialog did not close after confirmation")

            for _ in range(40):
                if self._get_current_capture_path() == original_capture_path.resolve():
                    break
                await ui_test.human_delay(human_delay_speed=5)
            else:
                self.fail(f"Capture layer did not restore to {original_capture_path.resolve()}")

            # Re-select the same prim again and confirm the first checkbox edit is still the next undoable action.
            self._usd_context.get_selection().clear_selected_prim_paths()
            await ui_test.wait_n_updates(10)
            self._usd_context.get_selection().set_selected_prim_paths([_TEST_SELECTION_PRIM], False)
            await ui_test.wait_n_updates(20)
            await ui_test.human_delay(human_delay_speed=5)

            for _ in range(80):
                checkbox = ui_test.find(checkbox_selector)
                if checkbox is not None and checkbox.widget.visible:
                    break

                item_prims = [
                    widget
                    for widget in ui_test.find_all(
                        f"{_WindowNames.PROPERTIES.value}//Frame/**/Label[*].identifier=='item_prim'"
                    )
                    if widget.widget.visible
                ]
                if len(item_prims) >= 2:
                    self.assertEqual(_TEST_EDITOR_LABEL, item_prims[-1].widget.text)
                    await item_prims[-1].click()
                    await ui_test.human_delay(human_delay_speed=5)
                else:
                    expand_buttons = [
                        widget
                        for widget in ui_test.find_all(
                            f"{_WindowNames.PROPERTIES.value}//Frame/**/Image[*].identifier=='Expand'"
                        )
                        if widget.widget.visible
                    ]
                    if expand_buttons:
                        await expand_buttons[0].click()
                        await ui_test.human_delay(human_delay_speed=5)
                await ui_test.human_delay(human_delay_speed=5)
            else:
                self.fail(f"Properties pane did not rebuild {_TEST_EDITOR_PRIM}.doubleSided after capture undo")

            self.assertEqual(first_toggle_value, self._get_prim_bool_attribute(_TEST_EDITOR_PRIM, "doubleSided"))
            self.assertEqual(1, len(self._get_undo_stack_names()), msg=f"undo_stack={self._get_undo_stack_names()}")

            # Final Ctrl+Z must go straight to the original checkbox edit with no ghost undo in between.
            await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.Z, carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
            await ui_test.human_delay(human_delay_speed=5)
            self.assertEqual(original_double_sided, self._get_prim_bool_attribute(_TEST_EDITOR_PRIM, "doubleSided"))
            self.assertFalse(omni.kit.undo.can_undo(), msg=f"undo_stack={self._get_undo_stack_names()}")

    def _get_current_capture_path(self) -> Path:
        capture_layer = _LayerManagerCore(context_name=self._context_name).get_layer_of_type(_LayerType.capture)
        self.assertIsNotNone(capture_layer)
        return Path(capture_layer.realPath).resolve()

    def _get_prim_bool_attribute(self, prim_path: str, attribute_name: str) -> bool:
        stage = self._usd_context.get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        self.assertTrue(prim.IsValid(), msg=f"Missing prim {prim_path}")
        attribute = prim.GetAttribute(attribute_name)
        self.assertTrue(attribute.IsValid(), msg=f"Missing attribute '{attribute_name}' on {prim_path}")
        return bool(attribute.Get())

    @staticmethod
    def _get_undo_stack_names() -> list[str]:
        return [entry.name for entry in omni.kit.undo.get_undo_stack()]

    async def _close_open_stage(self):
        usd_context = getattr(self, "_usd_context", None)
        if usd_context and usd_context.can_close_stage():
            usd_context.get_selection().clear_selected_prim_paths()
            await ui_test.wait_n_updates(10)
            omni.usd.release_all_hydra_engines(self._usd_context)
            await ui_test.wait_n_updates(10)
            await usd_context.close_stage_async()
            await ui_test.wait_n_updates(10)
