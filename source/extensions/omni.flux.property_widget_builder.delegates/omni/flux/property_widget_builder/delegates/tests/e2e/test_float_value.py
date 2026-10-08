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

__all__ = ("TestColorField",)

import uuid
from contextlib import nullcontext
from math import isclose

import omni.kit.test
import omni.kit.ui_test
import omni.ui as ui
from carb.input import KeyboardInput, MouseEventType
from carb.logging import acquire_logging
from omni.flux.property_widget_builder.model.usd import (
    USDAttributeItem,
    USDDelegate,
    USDModel,
    USDPropertyWidget,
    VirtualUSDAttributeItem,
)
from omni.flux.utils.common.interactive_usd_notices import is_any_interaction_active, register_objects_changed_listener
from omni.kit.commands import execute
from omni.kit.app import get_app
from omni.kit.ui_test.input import emulate_mouse
from omni.kit.undo import can_redo, can_undo, clear_stack, group, redo, undo
from omni.usd import get_context
from pxr import Gf, Sdf, Tf, Usd


class TestColorField(omni.kit.test.AsyncTestCase):
    """Exercise live color picker edits and cleanup through real USD property rows."""

    async def setUp(self):
        """Build a production color row backed by an in-memory USD attribute."""
        self.context = get_context("")
        await self.context.new_stage_async()
        prim = self.context.get_stage().DefinePrim("/World/Color", "Xform")
        self.color_attribute = prim.CreateAttribute("color", Sdf.ValueTypeNames.Color3f)
        self.color_attribute.Set(Gf.Vec3f(0.2, 0.2, 0.2))
        self.other_attribute = prim.CreateAttribute("intensity", Sdf.ValueTypeNames.Float)
        self.other_attribute.Set(1.0)
        self.model = USDModel(context_name="")
        self.window = ui.Window(
            f"{self.__class__.__name__}_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        with self.window.frame:
            self.property_widget = USDPropertyWidget(context_name="", model=self.model, delegate=USDDelegate())
        self.model.set_items([USDAttributeItem("", [self.color_attribute.GetPath()])])
        await omni.kit.ui_test.human_delay(human_delay_speed=1)

    async def tearDown(self):
        """Cancel active edits before releasing the UI and temporary stage."""
        self.model.set_items([])
        self.property_widget.destroy()
        self.model.destroy()
        self.window.destroy()
        clear_stack()
        await self.context.close_stage_async()

    async def test_edit_color_with_picker_open_updates_usd_and_dismissal_groups_undo(self):
        """Successive picker edits update USD live and undo as one completed session."""
        shared_notices = []

        def record_shared_color_notice(notice, _stage):
            """Record actual shared application notifications affecting the scene color."""
            if self.color_attribute.GetPath() in notice.GetChangedInfoOnlyPaths():
                shared_notices.append(tuple(notice.GetChangedInfoOnlyPaths()))

        subscription = register_objects_changed_listener(self.context.get_stage(), record_shared_color_notice)
        self.addCleanup(subscription.Revoke)
        widget_ref = omni.kit.ui_test.find(
            f"{self.window.title}//Frame/**/ColorWidget[*].name=='ColorsWidgetFieldRead'"
        )
        # Keep the popup open while each RGB field changes the scene color.
        await widget_ref.click()
        await omni.kit.ui_test.human_delay()
        await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.TAB)
        await omni.kit.ui_test.human_delay()
        expected_color = [0.2, 0.2, 0.2]
        for index, value in enumerate((0.8, 0.5, 0.4)):
            await omni.kit.ui_test.emulate_char_press(str(value))
            await omni.kit.ui_test.human_delay()
            await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.TAB)
            await omni.kit.ui_test.human_delay()
            expected_color[index] = value
            self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(*expected_color))
            self.assertEqual(shared_notices, [])

        # Dismissing the popup must leave one undo step for all three component edits.
        await omni.kit.ui_test.emulate_mouse_move_and_click(widget_ref.offset(-3, -3))
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.5, 0.4))
        self.assertEqual(len(shared_notices), 1)
        self.assertFalse(is_any_interaction_active())
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.5, 0.4))

    async def test_edit_missing_virtual_color_uses_custom_creation_and_undo_restores_attribute_lifetime(self):
        """Live native editing preserves virtual attribute creation callbacks and their undoable setup."""
        stage = self.context.get_stage()
        color_path = Sdf.Path("/World/Color.virtual_color")
        setup_path = Sdf.Path("/World/Color.custom_color_setup")
        creations = []

        def create_color_with_setup(attribute, value):
            """Create the missing color and its companion setup through real public commands."""
            creations.append((attribute.GetPath(), value))
            prim = stage.GetPrimAtPath(attribute.GetPath().GetPrimPath())
            execute(
                "CreateUsdAttributeCommand",
                prim=prim,
                attr_name=attribute.GetPath().name,
                attr_type=Sdf.ValueTypeNames.Color3f,
                attr_value=value,
            )
            execute(
                "CreateUsdAttributeCommand",
                prim=prim,
                attr_name=setup_path.name,
                attr_type=Sdf.ValueTypeNames.Bool,
                attr_value=True,
            )

        self.model.set_items(
            [
                VirtualUSDAttributeItem(
                    "",
                    [color_path],
                    value_type_name=Sdf.ValueTypeNames.Color3f,
                    default_value=Gf.Vec3f(0.2, 0.2, 0.2),
                    create_callback=create_color_with_setup,
                )
            ]
        )
        await omni.kit.ui_test.human_delay()

        # Editing the native picker creates the virtual color before the popup closes.
        widget_ref = await self._open_picker_and_edit_red(0.8)
        self.assertEqual(creations, [(color_path, Gf.Vec3f(0.8, 0.2, 0.2))])
        self.assertEqual(stage.GetAttributeAtPath(color_path).Get(), Gf.Vec3f(0.8, 0.2, 0.2))
        self.assertTrue(stage.GetAttributeAtPath(setup_path).Get())
        await omni.kit.ui_test.emulate_char_press("0.5")
        await omni.kit.ui_test.human_delay()
        await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.TAB)
        await omni.kit.ui_test.human_delay()
        self.assertEqual(stage.GetAttributeAtPath(color_path).Get(), Gf.Vec3f(0.8, 0.5, 0.2))
        self.assertEqual(creations, [(color_path, Gf.Vec3f(0.8, 0.2, 0.2))])
        await omni.kit.ui_test.emulate_mouse_move_and_click(widget_ref.offset(-3, -3))
        await omni.kit.ui_test.human_delay()

        # One undo restores the missing attributes; redo restores the custom-created setup and color.
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertFalse(stage.GetAttributeAtPath(color_path).IsValid())
        self.assertFalse(stage.GetAttributeAtPath(setup_path).IsValid())
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(stage.GetAttributeAtPath(color_path).Get(), Gf.Vec3f(0.8, 0.5, 0.2))
        self.assertTrue(stage.GetAttributeAtPath(setup_path).Get())

    async def test_live_virtual_color_creation_failure_rolls_back_setup_and_preserves_prior_undo(self):
        """A custom creation exception removes its authored specs and leaves earlier undo history intact."""
        stage = self.context.get_stage()
        color_path = Sdf.Path("/World/Color.virtual_color")
        setup_path = Sdf.Path("/World/Color.custom_color_setup")

        def create_color_then_fail(attribute, value):
            """Author real custom setup before reporting that creation could not complete."""
            prim = stage.GetPrimAtPath(attribute.GetPath().GetPrimPath())
            for path, value_type, authored_value in (
                (color_path, Sdf.ValueTypeNames.Color3f, value),
                (setup_path, Sdf.ValueTypeNames.Bool, True),
            ):
                execute(
                    "CreateUsdAttributeCommand",
                    prim=prim,
                    attr_name=path.name,
                    attr_type=value_type,
                    attr_value=authored_value,
                )
            raise RuntimeError("Custom color setup failed")

        item = VirtualUSDAttributeItem(
            "",
            [color_path],
            value_type_name=Sdf.ValueTypeNames.Color3f,
            default_value=Gf.Vec3f(0.2, 0.2, 0.2),
            create_callback=create_color_then_fail,
        )
        self.model.set_items([item])
        value_model = item.value_models[0]
        execute(
            "ChangeProperty",
            prop_path=self.other_attribute.GetPath(),
            value=2.0,
            prev=1.0,
            usd_context_name="",
        )

        # Exercise the public API so the expected callback exception reaches this test directly.
        value_model.begin_batch_edit(live=True)
        try:
            with self.assertRaisesRegex(RuntimeError, "Custom color setup failed"):
                value_model.set_value(Gf.Vec3f(0.8, 0.2, 0.2))
            self.assertFalse(value_model.is_batch_editing)
        finally:
            value_model.end_batch_edit()
        self.assertFalse(stage.GetAttributeAtPath(color_path).IsValid())
        self.assertFalse(stage.GetAttributeAtPath(setup_path).IsValid())
        self.assertFalse(can_redo())

        # Undo and redo still target the completed intensity operation, with no failed creation step.
        undo()
        self.assertEqual(self.other_attribute.Get(), 1.0)
        redo()
        self.assertEqual(self.other_attribute.Get(), 2.0)
        self.assertFalse(stage.GetAttributeAtPath(color_path).IsValid())
        self.assertFalse(stage.GetAttributeAtPath(setup_path).IsValid())
        self.assertFalse(can_redo())

    async def test_remove_color_row_with_picker_open_keeps_later_command_undo_separate(self):
        """Removing an actively edited row releases its undo group before the next command."""
        await self._open_picker_and_edit_red(0.8)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))

        # Replacing the property selection cancels the row while its picker is still open.
        self.model.set_items([])
        await omni.kit.ui_test.human_delay()
        self.assertFalse(is_any_interaction_active())
        execute(
            "ChangeProperty",
            prop_path=self.other_attribute.GetPath(),
            value=2.0,
            prev=1.0,
            usd_context_name="",
        )
        self.assertEqual(self.other_attribute.Get(), 2.0)
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.other_attribute.Get(), 1.0)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))

    async def test_edit_read_only_color_preserves_pending_redo(self):
        """A rejected picker edit leaves the scene color and unrelated redo step intact."""
        self.model.set_items([USDAttributeItem("", [self.color_attribute.GetPath()], read_only=True)])
        await omni.kit.ui_test.human_delay()
        execute(
            "ChangeProperty",
            prop_path=self.other_attribute.GetPath(),
            value=2.0,
            prev=1.0,
            usd_context_name="",
        )
        undo()
        self.assertTrue(can_redo())

        # Trying to edit a locked row must not consume the pending intensity redo.
        widget_ref = await self._open_picker_and_edit_red(0.8)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))
        await omni.kit.ui_test.emulate_mouse_move_and_click(widget_ref.offset(-3, -3))
        await omni.kit.ui_test.human_delay()
        self.assertTrue(can_redo())
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.other_attribute.Get(), 2.0)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))

    async def test_undo_with_picker_open_preserves_restored_color_after_dismissal(self):
        """Undo automatically dismisses focused RGB editing while preserving the restored color and redo."""
        widget_ref = await self._open_picker_and_edit_red(0.8)
        await omni.kit.ui_test.emulate_char_press("0.5")
        await omni.kit.ui_test.human_delay()
        await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.TAB)
        await omni.kit.ui_test.human_delay()
        await omni.kit.ui_test.emulate_char_press("0.4")
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.5, 0.4))
        colors_at_dismissal = []
        end_edit_callback = widget_ref.model.add_end_edit_fn(
            lambda _model, _item: colors_at_dismissal.append(self.color_attribute.Get())
        )
        self.addCleanup(widget_ref.model.remove_end_edit_fn, end_edit_callback)

        # Undo closes the native popup without letting focused blue text overwrite the restored color.
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(colors_at_dismissal, [Gf.Vec3f(0.2, 0.2, 0.2)])
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))
        # The backing model releases its interaction after two application updates.
        await omni.kit.ui_test.human_delay()
        self.assertFalse(is_any_interaction_active())
        self.assertTrue(can_redo())
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.5, 0.4))
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))

        # The restored row accepts a fresh native picker session after the interrupted edit.
        widget_ref = await self._open_picker_and_edit_red(0.6)
        await omni.kit.ui_test.emulate_mouse_move_and_click(widget_ref.offset(-3, -3))
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.6, 0.2, 0.2))
        self.assertFalse(is_any_interaction_active())

    async def test_undo_unrelated_command_with_queued_picker_color_discards_input_and_preserves_redo(self):
        """Undo dismisses an open picker and discards its queued color before another update can author it."""
        execute(
            "ChangeProperty",
            prop_path=self.other_attribute.GetPath(),
            value=2.0,
            prev=1.0,
            usd_context_name="",
        )
        widget_ref = omni.kit.ui_test.find(
            f"{self.window.title}//Frame/**/ColorWidget[*].name=='ColorsWidgetFieldRead'"
        )
        picker_model = widget_ref.model
        component_models = [picker_model.get_item_value_model(child) for child in picker_model.get_item_children()]
        colors_at_dismissal = []
        end_edit_callback = picker_model.add_end_edit_fn(
            lambda _model, _item: colors_at_dismissal.append(self.color_attribute.Get())
        )
        self.addCleanup(picker_model.remove_end_edit_fn, end_edit_callback)
        await widget_ref.click()
        await omni.kit.ui_test.human_delay()

        # Queue a complete color through the public picker model, then undo before yielding another update.
        for component_model, value in zip(component_models, (0.8, 0.5, 0.4)):
            component_model.set_value(value)
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(colors_at_dismissal, [Gf.Vec3f(0.2, 0.2, 0.2)])
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))
        self.assertEqual(self.other_attribute.Get(), 1.0)
        # The backing model releases its interaction after two application updates.
        await omni.kit.ui_test.human_delay()
        self.assertFalse(is_any_interaction_active())
        self.assertTrue(can_redo())

        # The retained redo remains the intensity command and cannot replay discarded picker values.
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.other_attribute.Get(), 2.0)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))

    async def test_external_color_command_with_picker_open_survives_dismissal(self):
        """An external USD edit wins over the open picker's cached color on dismissal."""
        widget_ref = await self._open_picker_and_edit_red(0.8)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))

        # Another public command changes the same attribute without another picker gesture.
        execute(
            "ChangeProperty",
            prop_path=self.color_attribute.GetPath(),
            value=Gf.Vec3f(0.1, 0.4, 0.7),
            prev=Gf.Vec3f(0.8, 0.2, 0.2),
            usd_context_name="",
        )
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.1, 0.4, 0.7))
        await omni.kit.ui_test.emulate_mouse_move_and_click(widget_ref.offset(-3, -3))
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.1, 0.4, 0.7))
        self.assertFalse(is_any_interaction_active())

        # The next native edit starts from the externally authored color.
        widget_ref = await self._open_picker_and_edit_red(0.6)
        await omni.kit.ui_test.emulate_mouse_move_and_click(widget_ref.offset(-3, -3))
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.6, 0.4, 0.7))
        self.assertFalse(is_any_interaction_active())

    async def test_edit_selected_colors_with_locked_target_rolls_back_failed_session(self):
        """A failed selection edit preserves the previous completed picker session and its undo."""
        stage = self.context.get_stage()
        session_layer = stage.GetSessionLayer()
        with Usd.EditContext(stage, session_layer):
            second_prim = stage.DefinePrim("/World/LockedColor", "Xform")
            second_attribute = second_prim.CreateAttribute("color", Sdf.ValueTypeNames.Color3f)
            second_attribute.Set(Gf.Vec3f(0.2, 0.2, 0.2))
        self.model.set_items([USDAttributeItem("", [self.color_attribute.GetPath(), second_attribute.GetPath()])])
        await omni.kit.ui_test.human_delay()

        # Complete a valid multi-selection edit before a later session encounters a locked target.
        widget_ref = await self._open_picker_and_edit_red(0.8)
        await omni.kit.ui_test.emulate_mouse_move_and_click(widget_ref.offset(-3, -3))
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))
        self.assertEqual(second_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))

        session_layer.SetPermissionToEdit(False)
        try:
            # The first target remains writable; the second genuinely rejects the same live edit.
            widget_ref = await self._open_picker_and_edit_red(0.5)
            self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))
            self.assertEqual(second_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))
        finally:
            session_layer.SetPermissionToEdit(True)

        # The same row remains usable after the rejected edit and keeps the corrected picker value.
        await omni.kit.ui_test.emulate_mouse_move_and_click(widget_ref.offset(-3, -3))
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))
        self.assertEqual(second_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))
        self.assertFalse(is_any_interaction_active())
        widget_ref = await self._open_picker_and_edit_red(0.6)
        await omni.kit.ui_test.emulate_mouse_move_and_click(widget_ref.offset(-3, -3))
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.6, 0.2, 0.2))
        self.assertEqual(second_attribute.Get(), Gf.Vec3f(0.6, 0.2, 0.2))
        self.model.set_items([])
        await omni.kit.ui_test.human_delay()

        # The next command and the two completed picker sessions each retain their own undo step.
        execute(
            "ChangeProperty",
            prop_path=self.other_attribute.GetPath(),
            value=2.0,
            prev=1.0,
            usd_context_name="",
        )
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.other_attribute.Get(), 1.0)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.6, 0.2, 0.2))
        self.assertEqual(second_attribute.Get(), Gf.Vec3f(0.6, 0.2, 0.2))
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))
        self.assertEqual(second_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))
        self.assertEqual(second_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))

    async def test_failed_live_selection_edit_preserves_prior_command_without_empty_undo_or_redo_step(self):
        """A failed later preview rolls back its first write without consuming another undo step."""
        stage = self.context.get_stage()
        session_layer = stage.GetSessionLayer()
        original_color = Gf.Vec3f(0.2, 0.2, 0.2)
        second_color = Gf.Vec3f(0.8, 0.2, 0.2)
        with Usd.EditContext(stage, session_layer):
            second_prim = stage.DefinePrim("/World/LockedColor", "Xform")
            second_attribute = second_prim.CreateAttribute("color", Sdf.ValueTypeNames.Color3f)
            second_attribute.Set(second_color)

        for caller_owns_group in (False, True):
            with self.subTest(caller_owns_group=caller_owns_group):
                clear_stack()
                self.color_attribute.Set(original_color)
                self.other_attribute.Set(1.0)
                item = USDAttributeItem("", [self.color_attribute.GetPath(), second_attribute.GetPath()])
                self.model.set_items([item])
                value_model = item.value_models[0]

                # The first preview skips the already matching session-layer color.
                with group() if caller_owns_group else nullcontext():
                    execute(
                        "ChangeProperty",
                        prop_path=self.other_attribute.GetPath(),
                        value=2.0,
                        prev=1.0,
                        usd_context_name="",
                    )
                    value_model.begin_batch_edit(live=True)
                    try:
                        value_model.set_value(second_color)
                        self.assertEqual(self.color_attribute.Get(), second_color)
                        self.assertEqual(second_attribute.Get(), second_color)

                        # A later preview now needs the locked target and must cancel the whole live edit.
                        session_layer.SetPermissionToEdit(False)
                        value_model.set_value(Gf.Vec3f(0.5, 0.2, 0.2))
                        self.assertFalse(value_model.is_batch_editing)
                    finally:
                        session_layer.SetPermissionToEdit(True)
                        value_model.end_batch_edit()

                self.assertEqual(self.color_attribute.Get(), original_color)
                self.assertEqual(second_attribute.Get(), second_color)
                self.assertEqual(self.other_attribute.Get(), 2.0)
                self.assertFalse(can_redo())

                # The next undo and redo operate only on the completed unrelated intensity command.
                undo()
                self.assertEqual(self.other_attribute.Get(), 1.0)
                self.assertFalse(can_undo())
                redo()
                self.assertEqual(self.other_attribute.Get(), 2.0)
                self.assertFalse(can_redo())
                self.assertEqual(self.color_attribute.Get(), original_color)
                self.assertEqual(second_attribute.Get(), second_color)

    async def test_live_batch_inside_caller_group_preserves_outer_operation_and_later_undo(self):
        """A live color batch preserves its caller's undo group and the subsequent undo step."""
        value_model = self.model.get_all_items()[0].value_models[0]
        with group():
            execute(
                "ChangeProperty",
                prop_path=self.other_attribute.GetPath(),
                value=2.0,
                prev=1.0,
                usd_context_name="",
            )
            value_model.begin_batch_edit(live=True)
            try:
                value_model.set_value(Gf.Vec3f(0.6, 0.2, 0.2))
                value_model.set_value(Gf.Vec3f(0.8, 0.2, 0.2))
            finally:
                value_model.end_batch_edit()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))
        execute(
            "ChangeProperty",
            prop_path=self.other_attribute.GetPath(),
            value=3.0,
            prev=2.0,
            usd_context_name="",
        )
        undo()
        self.assertEqual(self.other_attribute.Get(), 2.0)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))
        undo()
        self.assertEqual(self.other_attribute.Get(), 1.0)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))

    async def test_drag_picker_applies_complete_colors_once_per_frame_and_groups_undo(self):
        """Native picker dragging writes complete live colors once per frame in one undo session."""
        widget_ref = omni.kit.ui_test.find(
            f"{self.window.title}//Frame/**/ColorWidget[*].name=='ColorsWidgetFieldRead'"
        )
        component_models = [
            widget_ref.model.get_item_value_model(child) for child in widget_ref.model.get_item_children()
        ]
        app = get_app()
        writes = []

        def record_color_write(notice, _stage):
            """Record actual color authoring and the picker state visible at that frame."""
            if self.color_attribute.GetPath() in notice.GetChangedInfoOnlyPaths():
                writes.append(
                    (
                        app.get_update_number(),
                        self.color_attribute.Get(),
                        Gf.Vec3f(*(model.get_value_as_float() for model in component_models)),
                    )
                )

        listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, record_color_write, self.context.get_stage())
        try:
            # The native popup is not queryable; its saturation/value square sits beside the swatch.
            await widget_ref.click()
            await omni.kit.ui_test.human_delay()
            start = widget_ref.offset(100, 100)
            await emulate_mouse(MouseEventType.MOVE, start)
            await omni.kit.ui_test.human_delay()
            await emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN)
            await omni.kit.ui_test.human_delay()
            for index in range(1, 6):
                await emulate_mouse(MouseEventType.MOVE, start + omni.kit.ui_test.Vec2(index * 4, 0))
                await omni.kit.ui_test.human_delay()
                self.assertEqual(
                    self.color_attribute.Get(), Gf.Vec3f(*(model.get_value_as_float() for model in component_models))
                )
            await emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
            await omni.kit.ui_test.human_delay()
        finally:
            listener.Revoke()

        self.assertGreater(len(writes), 1)
        self.assertEqual(len({frame for frame, _value, _picker in writes}), len(writes), writes)
        for _frame, value, picker in writes:
            self.assertEqual(value, picker)
        final_color = self.color_attribute.Get()
        self.assertNotEqual(final_color, Gf.Vec3f(0.2, 0.2, 0.2))
        await omni.kit.ui_test.emulate_mouse_move_and_click(widget_ref.offset(-3, -3))
        await omni.kit.ui_test.human_delay()
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), final_color)

    async def test_drag_picker_undo_dismisses_popup_and_reopened_wheel_preserves_color_and_undo(self):
        """Each released wheel drag has its own undo step, including after undo dismisses the popup."""
        widget_ref = omni.kit.ui_test.find(
            f"{self.window.title}//Frame/**/ColorWidget[*].name=='ColorsWidgetFieldRead'"
        )
        original_color = Gf.Vec3f(0.2, 0.2, 0.2)
        component_models = [
            widget_ref.model.get_item_value_model(child) for child in widget_ref.model.get_item_children()
        ]
        colors_at_dismissal = []
        end_edit_callback = widget_ref.model.add_end_edit_fn(
            lambda _model, _item: colors_at_dismissal.append(self.color_attribute.Get())
        )
        self.addCleanup(widget_ref.model.remove_end_edit_fn, end_edit_callback)

        async def drag_square(start):
            """Drag the native saturation/value square through public mouse input."""
            await emulate_mouse(MouseEventType.MOVE, start)
            await omni.kit.ui_test.human_delay()
            await emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN)
            await omni.kit.ui_test.human_delay()
            await emulate_mouse(MouseEventType.MOVE, start + omni.kit.ui_test.Vec2(20, 0))
            await omni.kit.ui_test.human_delay()
            await emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
            await omni.kit.ui_test.human_delay()

        # Complete three separate drags without dismissing the popup between cursor releases.
        await widget_ref.click()
        await omni.kit.ui_test.human_delay()
        gesture_colors = []
        for x, y in ((100, 100), (140, 120), (110, 140)):
            await drag_square(widget_ref.offset(x, y))
            color = self.color_attribute.Get()
            self.assertNotEqual(color, original_color)
            self.assertNotIn(color, gesture_colors)
            self.assertEqual(color, Gf.Vec3f(*(model.get_value_as_float() for model in component_models)))
            gesture_colors.append(color)
        first_color, second_color, third_color = gesture_colors
        self.assertEqual(colors_at_dismissal, [])

        # Undo closes the popup and restores the second release, then walks the earlier checkpoints.
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(colors_at_dismissal, [second_color])
        self.assertEqual(self.color_attribute.Get(), second_color)
        # The backing model releases its interaction after two application updates.
        await omni.kit.ui_test.human_delay()
        self.assertFalse(is_any_interaction_active())
        self.assertTrue(can_redo())
        for expected_color in (first_color, original_color):
            undo()
            await omni.kit.ui_test.human_delay()
            self.assertEqual(self.color_attribute.Get(), expected_color)
        for expected_color in (first_color, second_color, third_color):
            redo()
            await omni.kit.ui_test.human_delay()
            self.assertEqual(self.color_attribute.Get(), expected_color)
        self.assertEqual(colors_at_dismissal, [second_color])
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), second_color)

        # Reopening the picker starts a fresh wheel edit from the restored scene color.
        widget_ref = omni.kit.ui_test.find(
            f"{self.window.title}//Frame/**/ColorWidget[*].name=='ColorsWidgetFieldRead'"
        )
        await widget_ref.click()
        await omni.kit.ui_test.human_delay()
        await drag_square(widget_ref.offset(120, 150))
        reopened_color = self.color_attribute.Get()
        self.assertNotEqual(reopened_color, original_color)
        self.assertNotIn(reopened_color, gesture_colors)
        await omni.kit.ui_test.emulate_mouse_move_and_click(widget_ref.offset(-3, -3))
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), reopened_color)
        self.assertFalse(is_any_interaction_active())
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), second_color)
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), reopened_color)

    async def test_close_picker_before_next_frame_flushes_latest_complete_color(self):
        """Native dismissal flushes same-frame RGB edits before its end-edit observers run."""
        widget_ref = omni.kit.ui_test.find(
            f"{self.window.title}//Frame/**/ColorWidget[*].name=='ColorsWidgetFieldRead'"
        )
        picker_model = widget_ref.model
        component_models = [picker_model.get_item_value_model(child) for child in picker_model.get_item_children()]
        await widget_ref.click()
        await omni.kit.ui_test.human_delay()
        await emulate_mouse(MouseEventType.MOVE, widget_ref.offset(-3, -3))
        await omni.kit.ui_test.human_delay()
        colors_at_dismissal = []
        another_update_occurred = False
        intervening_update_subscription = None
        input_update_processed = False

        def record_dismissed_color(_model, _item):
            """Observe the authored color when the real popup finishes editing."""
            colors_at_dismissal.append((another_update_occurred, self.color_attribute.Get()))

        def record_intervening_update(_event):
            """Detect a later update that could flush the queued color before dismissal."""
            nonlocal another_update_occurred, intervening_update_subscription
            another_update_occurred = True
            intervening_update_subscription = None

        def queue_component_edits(_event):
            """Queue complete RGB edits during the update preceding native popup dismissal."""
            nonlocal queue_subscription, intervening_update_subscription, input_update_processed
            # The buffered native click is forwarded one update before the popup's dismissal frame.
            if not input_update_processed:
                input_update_processed = True
                return
            queue_subscription = None
            intervening_update_subscription = (
                get_app().get_update_event_stream().create_subscription_to_pop(record_intervening_update)
            )
            for model, value in zip(component_models, (0.8, 0.5, 0.4)):
                model.set_value(value)

        # Queue RGB in the closing frame, before the queued write can receive another update.
        end_subscription = picker_model.subscribe_end_edit_fn(record_dismissed_color)
        queue_subscription = get_app().get_update_event_stream().create_subscription_to_pop(queue_component_edits)
        try:
            await emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN)
            await omni.kit.ui_test.human_delay()
            await emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
            await omni.kit.ui_test.human_delay()
        finally:
            queue_subscription = None
            intervening_update_subscription = None
            del end_subscription
        self.assertEqual(colors_at_dismissal, [(False, Gf.Vec3f(0.8, 0.5, 0.4))])
        undo()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))
        redo()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.5, 0.4))

    async def test_remove_color_row_before_next_frame_discards_queued_edits_and_preserves_redo(self):
        """Removing a row discards unflushed component edits without consuming unrelated redo."""
        # Leave a real redo step pending before queueing changes on a row that will disappear.
        execute(
            "ChangeProperty",
            prop_path=self.other_attribute.GetPath(),
            value=2.0,
            prev=1.0,
            usd_context_name="",
        )
        undo()
        widget_ref = omni.kit.ui_test.find(
            f"{self.window.title}//Frame/**/ColorWidget[*].name=='ColorsWidgetFieldRead'"
        )
        red_model = widget_ref.model.get_item_value_model(widget_ref.model.get_item_children()[0])
        row_removed = False

        def remove_row_during_native_edit(_component_model):
            """Replace the selection during real picker input before its queued write can run."""
            nonlocal row_removed
            if not row_removed:
                row_removed = True
                self.model.set_items([])

        subscription = red_model.subscribe_value_changed_fn(remove_row_during_native_edit)
        try:
            await self._open_picker_and_edit_red(0.8)
        finally:
            del subscription
        self.assertTrue(row_removed)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))
        self.assertFalse(is_any_interaction_active())
        self.assertTrue(can_redo())
        redo()
        self.assertEqual(self.other_attribute.Get(), 2.0)

    async def test_update_backing_color_before_next_frame_supersedes_queued_picker_edits(self):
        """An external USD command during native input cancels queued picker edits and refreshes the picker."""
        picker_model = omni.kit.ui_test.find(
            f"{self.window.title}//Frame/**/ColorWidget[*].name=='ColorsWidgetFieldRead'"
        ).model
        component_models = [picker_model.get_item_value_model(child) for child in picker_model.get_item_children()]

        external_edit_applied = False

        def change_usd_during_native_edit(component_model):
            """Author a newer public USD edit while the native red change is still queued."""
            nonlocal external_edit_applied
            if external_edit_applied or not isclose(component_model.get_value_as_float(), 0.8, abs_tol=1e-6):
                return
            external_edit_applied = True
            execute(
                "ChangeProperty",
                prop_path=self.color_attribute.GetPath(),
                value=Gf.Vec3f(0.6, 0.7, 0.9),
                prev=self.color_attribute.Get(),
                usd_context_name="",
            )

        # Observe actual picker input; the competing scene edit uses the public command API.
        subscription = component_models[0].subscribe_value_changed_fn(change_usd_during_native_edit)
        try:
            await self._open_picker_and_edit_red(0.8)
        finally:
            del subscription
        self.assertTrue(external_edit_applied)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.6, 0.7, 0.9))
        picker_model = omni.kit.ui_test.find(
            f"{self.window.title}//Frame/**/ColorWidget[*].name=='ColorsWidgetFieldRead'"
        ).model
        component_models = [picker_model.get_item_value_model(child) for child in picker_model.get_item_children()]
        self.assertEqual(Gf.Vec3f(*(model.get_value_as_float() for model in component_models)), Gf.Vec3f(0.6, 0.7, 0.9))
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.6, 0.7, 0.9))

    async def test_write_color_vectors_and_tuples_preserves_usd_types_without_conversion_warnings(self):
        """Write supported color vectors and tuples through real models without scalar-conversion warnings."""
        conversion_warnings = []

        def record_conversion_warning(source, _level, _file, _line, message):
            """Observe actual attribute-model conversion warnings without replacing logging."""
            if source.endswith("item_model.attr_value") and "Failed to use convert type" in message:
                conversion_warnings.append(message)

        logging = acquire_logging()
        logger = logging.add_logger(record_conversion_warning)
        try:
            # Every supported color precision and dimension must accept both public input forms.
            for color_type, vector_type, dimension in (
                (Sdf.ValueTypeNames.Color3d, Gf.Vec3d, 3),
                (Sdf.ValueTypeNames.Color3f, Gf.Vec3f, 3),
                (Sdf.ValueTypeNames.Color3h, Gf.Vec3h, 3),
                (Sdf.ValueTypeNames.Color4d, Gf.Vec4d, 4),
                (Sdf.ValueTypeNames.Color4f, Gf.Vec4f, 4),
                (Sdf.ValueTypeNames.Color4h, Gf.Vec4h, 4),
            ):
                with self.subTest(color_type=str(color_type)):
                    attribute = self.color_attribute.GetPrim().CreateAttribute(f"color_{color_type}", color_type)
                    attribute.Set(vector_type(0.0))
                    item = USDAttributeItem("", [attribute.GetPath()])
                    self.model.set_items([item])
                    value_model = item.value_models[0]
                    value_model.set_value(vector_type(*(0.25, 0.5, 0.75, 1.0)[:dimension]))
                    self.assertIsInstance(attribute.Get(), vector_type)
                    self.assertEqual(attribute.Get(), vector_type(*(0.25, 0.5, 0.75, 1.0)[:dimension]))
                    value_model.set_value((0.125, 0.25, 0.5, 0.75)[:dimension])
                    self.assertIsInstance(attribute.Get(), vector_type)
                    self.assertEqual(attribute.Get(), vector_type(*(0.125, 0.25, 0.5, 0.75)[:dimension]))
        finally:
            logging.remove_logger(logger)
        self.assertEqual(conversion_warnings, [])

    async def _open_picker_and_edit_red(self, value):
        """Open the native color popup and edit its red numeric field.

        Args:
            value: Red component entered through the picker keyboard control.

        Returns:
            Swatch reference used to dismiss the popup after the workflow.
        """
        widget_ref = omni.kit.ui_test.find(
            f"{self.window.title}//Frame/**/ColorWidget[*].name=='ColorsWidgetFieldRead'"
        )
        await widget_ref.click()
        await omni.kit.ui_test.human_delay()
        await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.TAB)
        await omni.kit.ui_test.human_delay()
        await omni.kit.ui_test.emulate_char_press(str(value))
        await omni.kit.ui_test.human_delay()
        await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.TAB)
        await omni.kit.ui_test.human_delay()
        return widget_ref
