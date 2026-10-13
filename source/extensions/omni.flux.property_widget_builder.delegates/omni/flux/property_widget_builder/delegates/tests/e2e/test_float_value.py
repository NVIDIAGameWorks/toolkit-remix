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

import sys
import uuid
from contextlib import nullcontext
from math import isclose

import omni.kit.test
import omni.kit.ui_test
import omni.ui as ui
from carb.input import KEYBOARD_MODIFIER_FLAG_CONTROL, KeyboardEventType, KeyboardInput, MouseEventType
from carb.logging import acquire_logging
from omni.flux.property_widget_builder.model.usd import (
    USDAttributeItem,
    USDDelegate,
    USDModel,
    USDPropertyWidget,
    VirtualUSDAttributeItem,
    get_usd_listener_instance,
)
from omni.flux.utils.common.interactive_usd_notices import is_any_interaction_active, register_objects_changed_listener
from omni.kit.commands import execute
from omni.kit.app import get_app
from omni.kit.ui_test.input import emulate_keyboard, emulate_mouse
from omni.kit.undo import can_redo, can_undo, clear_stack, group, redo, undo
from omni.usd import get_context
from pxr import Gf, Sdf, Tf, Usd, UsdLux


class TestColorField(omni.kit.test.AsyncTestCase):
    """Exercise live color picker edits and cleanup through real USD property rows."""

    async def setUp(self):
        """Build a production color row backed by an in-memory USD attribute."""
        self.context = get_context("")
        await self.context.new_stage_async()
        prim = self.context.get_stage().DefinePrim("/World/Color", "Xform")
        self.color_attribute = prim.CreateAttribute("color", Sdf.ValueTypeNames.Color3f)
        self.color_attribute.Set(Gf.Vec3f(0.2, 0.2, 0.2))
        other_prim = self.context.get_stage().DefinePrim("/World/Other", "Xform")
        self.other_attribute = other_prim.CreateAttribute("intensity", Sdf.ValueTypeNames.Float)
        self.other_attribute.Set(1.0)
        self.model = USDModel(context_name="")
        self.window = ui.Window(
            f"{self.__class__.__name__}_{str(uuid.uuid1())}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        self.picker_window_title = None
        self.delegate = USDDelegate()
        with self.window.frame:
            self.property_widget = USDPropertyWidget(context_name="", model=self.model, delegate=self.delegate)
        self.model.set_items([USDAttributeItem("", [self.color_attribute.GetPath()])])
        self.model.set_prim_paths([self.color_attribute.GetPrim().GetPath()])
        self.usd_listener = get_usd_listener_instance()
        self.assertIsNotNone(self.usd_listener)
        self.usd_listener.add_model(self.model)
        await omni.kit.ui_test.human_delay(human_delay_speed=1)

    async def tearDown(self):
        """Close the owned picker before releasing the UI and temporary stage."""
        await self._close_picker()
        self.usd_listener.remove_model(self.model)
        self.model.set_items([])
        self.property_widget.destroy()
        self.model.destroy()
        self.window.destroy()
        clear_stack()
        await self.context.close_stage_async()

    async def test_edit_rgb_fields_with_picker_open_preserves_live_updates_and_per_edit_undo(self):
        """Committed RGB edits update the open picker and retain independent undo steps."""
        shared_notices = []

        def record_shared_color_notice(notice, _stage):
            """Record actual application notifications affecting the scene color."""
            if self.color_attribute.GetPath() in notice.GetChangedInfoOnlyPaths():
                shared_notices.append(tuple(notice.GetChangedInfoOnlyPaths()))

        subscription = register_objects_changed_listener(self.context.get_stage(), record_shared_color_notice)
        self.addCleanup(subscription.Revoke)
        await self._open_picker()
        expected_colors = [Gf.Vec3f(0.2, 0.2, 0.2)]
        components = [0.2, 0.2, 0.2]
        for index, (component, value) in enumerate(zip(("red", "green", "blue"), (0.8, 0.5, 0.4))):
            await self._edit_picker_component(component, value)
            components[index] = value
            expected_colors.append(Gf.Vec3f(*components))
            self.assertEqual(self.color_attribute.Get(), expected_colors[-1])
        await self._close_picker()
        self.assertTrue(shared_notices)
        self.assertFalse(is_any_interaction_active())
        for color in reversed(expected_colors[:-1]):
            undo()
            await omni.kit.ui_test.human_delay()
            self.assertEqual(self.color_attribute.Get(), color)
        for color in expected_colors[1:]:
            redo()
            await omni.kit.ui_test.human_delay()
            self.assertEqual(self.color_attribute.Get(), color)

    async def test_edit_missing_virtual_color_uses_custom_creation_and_undo_restores_attribute_lifetime(self):
        """Owned RGB editing preserves virtual attribute creation callbacks and their undoable setup."""
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

        # Actual RGB input creates the virtual color before the popup closes.
        await self._open_picker_and_edit_red(0.8)
        self.assertEqual(creations, [(color_path, Gf.Vec3f(0.8, 0.2, 0.2))])
        self.assertEqual(stage.GetAttributeAtPath(color_path).Get(), Gf.Vec3f(0.8, 0.2, 0.2))
        self.assertTrue(stage.GetAttributeAtPath(setup_path).Get())
        await self._edit_picker_component("green", 0.5)
        self.assertEqual(stage.GetAttributeAtPath(color_path).Get(), Gf.Vec3f(0.8, 0.5, 0.2))
        self.assertEqual(creations, [(color_path, Gf.Vec3f(0.8, 0.2, 0.2))])
        await self._close_picker()
        await omni.kit.ui_test.human_delay()

        # The later green gesture undoes separately from the original undoable attribute creation.
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(stage.GetAttributeAtPath(color_path).Get(), Gf.Vec3f(0.8, 0.2, 0.2))
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertFalse(stage.GetAttributeAtPath(color_path).IsValid())
        self.assertFalse(stage.GetAttributeAtPath(setup_path).IsValid())
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(stage.GetAttributeAtPath(color_path).Get(), Gf.Vec3f(0.8, 0.2, 0.2))
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
        """Removing an edited row preserves color history independently from the next command."""
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
        """A disabled color swatch leaves the scene color and unrelated redo intact."""
        self.model.set_items([USDAttributeItem("", [self.color_attribute.GetPath()], read_only=True)])
        await omni.kit.ui_test.human_delay()
        execute("ChangeProperty", prop_path=self.other_attribute.GetPath(), value=2.0, prev=1.0, usd_context_name="")
        undo()
        self.assertTrue(can_redo())
        await self._open_picker()
        self._assert_picker_closed()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))
        self.assertTrue(can_redo())
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.other_attribute.Get(), 2.0)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))

    async def test_undo_with_picker_open_preserves_restored_rgb_values_and_reopening(self):
        """Undo restores the preceding RGB gesture and reopening accepts another edit."""
        await self._open_picker_and_edit_red(0.8)
        await self._edit_picker_component("green", 0.5)
        await self._edit_picker_component("blue", 0.4)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.5, 0.4))
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertTrue(ui.Workspace.get_window(self.picker_window_title).visible)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.5, 0.2))

        self.assertFalse(is_any_interaction_active())
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.5, 0.4))
        undo()
        await omni.kit.ui_test.human_delay()
        await self._close_picker()
        await self._open_picker_and_edit_red(0.6)
        await self._close_picker()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.6, 0.5, 0.2))
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
        picker_model = await self._open_picker()
        red_model = picker_model.get_item_value_model(picker_model.get_item_children()[0])
        undo_applied = False

        def undo_during_native_edit(component_model):
            """Undo the preceding command while native RGB input is still queued."""
            nonlocal undo_applied
            if undo_applied or not isclose(component_model.get_value_as_float(), 0.8, abs_tol=1e-6):
                return
            undo_applied = True
            undo()

        # The native value-change callback interrupts input before its deferred USD write.
        subscription = red_model.subscribe_value_changed_fn(undo_during_native_edit)
        try:
            await self._edit_picker_component("red", 0.8)
        finally:
            del subscription
        self.assertTrue(undo_applied)
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
        await self._open_picker_and_edit_red(0.8)
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
        await self._close_picker()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.1, 0.4, 0.7))
        self.assertFalse(is_any_interaction_active())

        # The next native edit starts from the externally authored color.
        await self._open_picker_and_edit_red(0.6)
        await self._close_picker()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.6, 0.4, 0.7))
        self.assertFalse(is_any_interaction_active())

    async def test_edit_selected_colors_with_locked_target_rolls_back_failed_gesture(self):
        """A rejected selection edit preserves completed color gestures and their undo history."""
        stage = self.context.get_stage()
        session_layer = stage.GetSessionLayer()
        with Usd.EditContext(stage, session_layer):
            second_prim = stage.DefinePrim("/World/LockedColor", "Xform")
            second_attribute = second_prim.CreateAttribute("color", Sdf.ValueTypeNames.Color3f)
            second_attribute.Set(Gf.Vec3f(0.2, 0.2, 0.2))
        self.model.set_items([USDAttributeItem("", [self.color_attribute.GetPath(), second_attribute.GetPath()])])
        await omni.kit.ui_test.human_delay()

        # Complete a valid multi-selection gesture before a later gesture encounters a locked target.
        await self._open_picker_and_edit_red(0.8)
        await self._close_picker()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))
        self.assertEqual(second_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))

        session_layer.SetPermissionToEdit(False)
        try:
            # The first target remains writable; the second genuinely rejects the same live edit.
            await self._open_picker_and_edit_red(0.5)
            self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))
            self.assertEqual(second_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))
        finally:
            session_layer.SetPermissionToEdit(True)

        # The same row remains usable after the rejected edit and keeps the corrected picker value.
        await self._close_picker()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))
        self.assertEqual(second_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))
        self.assertFalse(is_any_interaction_active())
        await self._open_picker_and_edit_red(0.6)
        await self._close_picker()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.6, 0.2, 0.2))
        self.assertEqual(second_attribute.Get(), Gf.Vec3f(0.6, 0.2, 0.2))
        self.model.set_items([])
        await omni.kit.ui_test.human_delay()

        # The next command and the two completed color gestures each retain their own undo step.
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
        """One SV drag writes complete live colors once per frame and undoes as one gesture."""
        picker_model = await self._open_picker()
        component_models = [picker_model.get_item_value_model(child) for child in picker_model.get_item_children()]
        app = get_app()
        writes = []

        def record_color_write(notice, _stage):
            """Record actual color authoring and the control values visible in that frame."""
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
            await self._drag_picker_control("sv", (0.4, 0.4), (0.7, 0.5))
        finally:
            listener.Revoke()
        self.assertGreater(len(writes), 1)
        self.assertEqual(len({frame for frame, _value, _control in writes}), len(writes), writes)
        for _frame, value, control in writes:
            self.assertEqual(value, control)
        final_color = self.color_attribute.Get()
        self.assertNotEqual(final_color, Gf.Vec3f(0.2, 0.2, 0.2))
        await self._close_picker()
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), final_color)

    async def test_drag_light_color_with_shared_usd_listener_preserves_live_updates_and_per_release_undo(self):
        """Shared USD refresh preserves the same open light picker and each released drag's history."""
        original_color = Gf.Vec3f(0.2, 0.2, 0.2)
        stage = self.context.get_stage()
        light_layer = Sdf.Layer.CreateAnonymous("light.usda")
        authoring_layer = stage.GetRootLayer()
        authoring_layer.subLayerPaths.append(light_layer.identifier)
        with Usd.EditContext(stage, light_layer):
            light = UsdLux.SphereLight.Define(stage, "/World/Light")
            color_attribute = UsdLux.LightAPI(light.GetPrim()).CreateColorAttr(original_color)
        stage.SetEditTarget(authoring_layer)
        self.assertIsNone(authoring_layer.GetPropertyAtPath(color_attribute.GetPath()))
        self.model.set_prim_paths([light.GetPath()])
        self.model.set_items([USDAttributeItem("", [color_attribute.GetPath()])])
        await omni.kit.ui_test.human_delay()
        await self._open_picker()
        await self._drag_picker_control("sv", (0.3, 0.3), (0.5, 0.4), color_attribute)
        first_color = color_attribute.Get()
        self.assertNotEqual(first_color, original_color)
        self.assertIsNotNone(authoring_layer.GetPropertyAtPath(color_attribute.GetPath()))
        for _ in range(3):
            await omni.kit.ui_test.human_delay()
        self.assertTrue(ui.Workspace.get_window(self.picker_window_title).visible)
        await self._drag_picker_control("hue", (0.5, 0.2), (0.5, 0.6), color_attribute)
        final_color = color_attribute.Get()
        self.assertNotEqual(final_color, first_color)
        await self._close_picker()
        self.assertFalse(is_any_interaction_active())
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(color_attribute.Get(), first_color)
        self.assertIsNotNone(authoring_layer.GetPropertyAtPath(color_attribute.GetPath()))
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(color_attribute.Get(), original_color)
        self.assertIsNone(authoring_layer.GetPropertyAtPath(color_attribute.GetPath()))
        self.assertFalse(can_undo())
        for color in (first_color, final_color):
            redo()
            await omni.kit.ui_test.human_delay()
            self.assertEqual(color_attribute.Get(), color)
            self.assertIsNotNone(authoring_layer.GetPropertyAtPath(color_attribute.GetPath()))
        self.assertFalse(can_redo())

    async def test_drag_rebuilt_color_row_reusing_value_model_preserves_live_edits_and_reopening(self):
        """Repeated row rebuilding preserves live gestures on the same backing value model."""
        original_color = self.color_attribute.Get()
        item = USDAttributeItem("", [self.color_attribute.GetPath()])
        self.model.set_prim_paths([self.color_attribute.GetPrim().GetPath()])
        for _ in range(3):
            self.model.set_items([item])
            await omni.kit.ui_test.human_delay()
        await self._open_picker()
        await self._drag_picker_control("sv", (0.3, 0.3), (0.5, 0.4))
        first_color = self.color_attribute.Get()
        self.assertNotEqual(first_color, original_color)
        undo()
        await omni.kit.ui_test.human_delay()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), original_color)
        await self._close_picker()
        await self._open_picker()
        await self._drag_picker_control("sv", (0.5, 0.5), (0.7, 0.6))
        second_color = self.color_attribute.Get()
        self.assertNotIn(second_color, (original_color, first_color))
        await self._close_picker()
        self.assertEqual(self.color_attribute.Get(), second_color)
        self.assertFalse(is_any_interaction_active())
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), original_color)
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), second_color)

    async def test_drag_picker_undo_keeps_popup_open_and_reopening_preserves_per_release_history(self):
        """Each released drag retains its own history across Undo, Redo, and reopening."""
        original_color = self.color_attribute.Get()
        await self._open_picker()
        gesture_colors = []
        for start, end in (((0.3, 0.3), (0.5, 0.4)), ((0.5, 0.5), (0.7, 0.6)), ((0.2, 0.6), (0.4, 0.7))):
            await self._drag_picker_control("sv", start, end)
            color = self.color_attribute.Get()
            self.assertNotEqual(color, original_color)
            self.assertNotIn(color, gesture_colors)
            gesture_colors.append(color)
        for expected_color in reversed([original_color, *gesture_colors[:-1]]):
            undo()
            await omni.kit.ui_test.human_delay()
            self.assertTrue(ui.Workspace.get_window(self.picker_window_title).visible)
            self.assertEqual(self.color_attribute.Get(), expected_color)
        self.assertFalse(can_undo())
        for expected_color in gesture_colors:
            redo()
            await omni.kit.ui_test.human_delay()
            self.assertEqual(self.color_attribute.Get(), expected_color)
        self.assertFalse(can_redo())
        await self._close_picker()
        await self._open_picker()
        await self._drag_picker_control("hue", (0.5, 0.2), (0.5, 0.6))
        reopened_color = self.color_attribute.Get()
        self.assertNotIn(reopened_color, [original_color, *gesture_colors])
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertTrue(ui.Workspace.get_window(self.picker_window_title).visible)
        self.assertEqual(self.color_attribute.Get(), gesture_colors[-1])
        self.assertFalse(is_any_interaction_active())
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), reopened_color)

    async def test_undo_open_picker_after_two_released_drags_restores_previous_drag(self):
        """Undo returns to the preceding released drag without replaying discarded input."""
        await self._open_picker()
        await self._drag_picker_control("sv", (0.3, 0.3), (0.5, 0.4))
        first_color = self.color_attribute.Get()
        await self._drag_picker_control("hue", (0.5, 0.2), (0.5, 0.6))
        second_color = self.color_attribute.Get()
        self.assertNotEqual(first_color, Gf.Vec3f(0.2, 0.2, 0.2))
        self.assertNotEqual(first_color, second_color)
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertTrue(ui.Workspace.get_window(self.picker_window_title).visible)
        self.assertEqual(self.color_attribute.Get(), first_color)
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), second_color)

    async def test_close_picker_before_next_frame_flushes_latest_complete_color(self):
        """Closing during actual RGB input flushes its complete color before another update."""
        await self._open_picker()
        swatch = omni.kit.ui_test.find(
            f"{self.window.title}//Frame/**/ColorPicker[*].identifier=='color_swatch'"
        ).widget
        red_model = self._picker_control("FloatDrag", "red").model
        colors_at_close = []
        close_requested = False

        def close_during_component_input(component_model):
            """Close the public picker while its actual red input remains queued."""
            nonlocal close_requested
            if close_requested or not isclose(component_model.get_value_as_float(), 0.8, abs_tol=1e-6):
                return
            close_requested = True
            frame = get_app().get_update_number()
            swatch.close()
            colors_at_close.append((frame, get_app().get_update_number(), self.color_attribute.Get()))

        subscription = red_model.subscribe_value_changed_fn(close_during_component_input)
        try:
            await self._edit_picker_component("red", 0.8)
        finally:
            del subscription
        self.assertEqual(len(colors_at_close), 1)
        before_frame, after_frame, color = colors_at_close[0]
        self.assertEqual(before_frame, after_frame)
        self.assertEqual(color, Gf.Vec3f(0.8, 0.2, 0.2))
        self._assert_picker_closed()
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))

        # A cancelled numeric control must not leave stale editing state in a reopened image gesture.
        await self._open_picker()
        await self._drag_picker_control("sv", (0.3, 0.3), (0.5, 0.4))
        released_color = self.color_attribute.Get()
        self.assertNotEqual(released_color, Gf.Vec3f(0.8, 0.2, 0.2))
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))
        self.assertTrue(ui.Workspace.get_window(self.picker_window_title).visible)

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
        picker_model = await self._open_picker()
        red_model = picker_model.get_item_value_model(picker_model.get_item_children()[0])
        row_removed = False

        def remove_row_during_native_edit(_component_model):
            """Replace the selection during real picker input before its queued write can run."""
            nonlocal row_removed
            if not row_removed:
                row_removed = True
                self.model.set_items([])

        subscription = red_model.subscribe_value_changed_fn(remove_row_during_native_edit)
        try:
            await self._edit_picker_component("red", 0.8)
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
            f"{self.window.title}//Frame/**/ColorPicker[*].identifier=='color_swatch'"
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
            f"{self.window.title}//Frame/**/ColorPicker[*].identifier=='color_swatch'"
        ).model
        component_models = [picker_model.get_item_value_model(child) for child in picker_model.get_item_children()]
        self.assertEqual(Gf.Vec3f(*(model.get_value_as_float() for model in component_models)), Gf.Vec3f(0.6, 0.7, 0.9))
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.6, 0.7, 0.9))

    async def test_undo_focused_component_before_first_setter_preserves_restored_color_on_blur(self):
        """Undo cancels a focused component before its first setter can replay stale text on blur."""
        await self._open_picker_and_edit_red(0.8)
        await self._focus_picker_component("red")
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))
        self._assert_picker_closed()
        await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
        await omni.kit.ui_test.human_delay()
        await self._close_picker()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))
        self.assertFalse(is_any_interaction_active())
        self.assertTrue(can_redo())
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))

    async def test_undo_after_popup_opens_and_history_returns_to_same_command_discards_queued_input(self):
        """An intervening command and Undo invalidate queued RGB input even when the old stack head returns."""
        execute("ChangeProperty", prop_path=self.other_attribute.GetPath(), value=2.0, prev=1.0, usd_context_name="")
        picker_model = await self._open_picker()
        red_model = picker_model.get_item_value_model(picker_model.get_item_children()[0])
        intervening_undo_applied = False

        def change_history_during_component_input(component_model):
            """Return the undo stack to its old head while actual RGB input is still queued."""
            nonlocal intervening_undo_applied
            if intervening_undo_applied or not isclose(component_model.get_value_as_float(), 0.8, abs_tol=1e-6):
                return
            intervening_undo_applied = True
            execute(
                "ChangeProperty", prop_path=self.other_attribute.GetPath(), value=3.0, prev=2.0, usd_context_name=""
            )
            undo()

        subscription = red_model.subscribe_value_changed_fn(change_history_during_component_input)
        try:
            await self._edit_picker_component("red", 0.8)
        finally:
            del subscription
        self.assertTrue(intervening_undo_applied)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))
        self.assertEqual(self.other_attribute.Get(), 2.0)
        self.assertFalse(is_any_interaction_active())
        self.assertTrue(can_redo())
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.other_attribute.Get(), 3.0)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))

    async def test_edit_hdr_rgba_picker_preserves_alpha_range_and_released_gesture_undo(self):
        """Owned RGB and HSV controls preserve HDR values, alpha, and per-release Undo."""
        original_color = Gf.Vec4f(2.0, 0.5, 0.25, 0.4)
        attribute = self.color_attribute.GetPrim().CreateAttribute("color4", Sdf.ValueTypeNames.Color4f)
        attribute.Set(original_color)
        self.model.set_items([USDAttributeItem("", [attribute.GetPath()])])
        await omni.kit.ui_test.human_delay()
        await self._open_picker()
        await self._edit_picker_component("red", 3.5)
        typed_color = Gf.Vec4f(3.5, 0.5, 0.25, 0.4)
        self.assertEqual(attribute.Get(), typed_color)
        await self._drag_picker_control("sv", (0.3, 0.3), (0.5, 0.4), attribute)
        hsv_color = attribute.Get()
        self.assertNotEqual(hsv_color, typed_color)
        self.assertGreater(max(hsv_color[index] for index in range(3)), 1.0)
        self.assertAlmostEqual(hsv_color[3], 0.4, places=6)
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertTrue(ui.Workspace.get_window(self.picker_window_title).visible)
        self.assertEqual(attribute.Get(), typed_color)
        await self._drag_picker_control("hue", (0.5, 0.2), (0.5, 0.6), attribute)
        hue_color = attribute.Get()
        self.assertNotEqual(hue_color, typed_color)
        self.assertGreater(max(hue_color[index] for index in range(3)), 1.0)
        self.assertAlmostEqual(hue_color[3], 0.4, places=6)
        await self._close_picker()
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(attribute.Get(), typed_color)
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(attribute.Get(), original_color)
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(attribute.Get(), typed_color)
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(attribute.Get(), hue_color)

    async def test_edit_negative_rgb_picker_preserves_authored_values_and_undo(self):
        """Numeric RGB input preserves negative values without failing HSV preview conversion."""
        original_color = Gf.Vec3f(0.0, 0.0, 0.0)
        self.color_attribute.Set(original_color)
        self.model.set_items([USDAttributeItem("", [self.color_attribute.GetPath()])])
        await omni.kit.ui_test.human_delay()
        await self._open_picker_and_edit_red(-1.0)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(-1.0, 0.0, 0.0))
        self.assertTrue(ui.Workspace.get_window(self.picker_window_title).visible)
        await self._close_picker()
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), original_color)
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(-1.0, 0.0, 0.0))

    async def test_close_button_with_uncommitted_component_text_preserves_latest_value_and_single_undo(self):
        """Normal Close commits focused RGB text without creating another undo step."""
        await self._open_picker()
        await self._focus_picker_component("red")
        await omni.kit.ui_test.emulate_char_press("0.8")
        await omni.kit.ui_test.human_delay()
        await self._close_picker()
        self._assert_picker_closed()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))
        self.assertFalse(can_undo())
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))
        self.assertFalse(can_redo())

    async def test_open_picker_near_main_window_bottom_keeps_close_reachable_without_editing_color(self):
        """RGB and RGBA pickers opened near the viewport bottom remain dismissible without authoring color."""
        self.window.position_y = max(0, ui.Workspace.get_main_window_height() - self.window.height)
        await omni.kit.ui_test.human_delay()
        for name, value_type, color in (
            ("edge_color_rgb", Sdf.ValueTypeNames.Color3f, Gf.Vec3f(0.2)),
            ("edge_color_rgba", Sdf.ValueTypeNames.Color4f, Gf.Vec4f(0.2, 0.2, 0.2, 0.4)),
        ):
            with self.subTest(value_type=value_type):
                attribute = self.color_attribute.GetPrim().CreateAttribute(name, value_type)
                attribute.Set(color)
                self.model.set_items([USDAttributeItem("", [attribute.GetPath()])])
                await omni.kit.ui_test.human_delay()
                await self._open_picker()
                close_button = self._picker_control("Button", "close")
                close_presses = []
                # A click outside the viewport may dismiss through focus loss; require an actual Close-button hit.
                close_button.widget.set_mouse_pressed_fn(lambda *_args, presses=close_presses: presses.append(True))
                await close_button.click()
                await omni.kit.ui_test.human_delay()
                self.assertTrue(close_presses)
                self._assert_picker_closed()
                self.assertEqual(attribute.Get(), color)
                self.assertFalse(can_undo())

    async def test_drag_rgb_fields_applies_live_values_and_preserves_per_release_undo(self):
        """RGB field drags update live and undo independently without discarding other channels."""
        await self._open_picker()
        await self._drag_picker_control("red", (0.25, 0.5), (0.75, 0.5), widget_type="FloatDrag")
        first_color = self.color_attribute.Get()
        self.assertNotEqual(first_color[0], 0.2)
        await self._drag_picker_control("green", (0.25, 0.5), (0.75, 0.5), widget_type="FloatDrag")
        second_color = self.color_attribute.Get()
        self.assertEqual(second_color[0], first_color[0])
        self.assertNotEqual(second_color[1], first_color[1])
        self.assertEqual(second_color[2], first_color[2])
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertTrue(ui.Workspace.get_window(self.picker_window_title).visible)
        self.assertEqual(self.color_attribute.Get(), first_color)
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), second_color)
        await self._close_picker()

    async def test_close_and_reopen_during_component_setter_preserves_new_popup_and_gesture_history(self):
        """Rapid reopening isolates the new popup from the old numeric control's late callbacks."""
        await self._open_picker()
        swatch = omni.kit.ui_test.find(
            f"{self.window.title}//Frame/**/ColorPicker[*].identifier=='color_swatch'"
        ).widget
        red_model = self._picker_control("FloatDrag", "red").model
        reopened = False

        def reopen_during_component_input(component_model):
            """Reopen through public APIs while actual numeric input is dispatching."""
            nonlocal reopened
            if reopened or not isclose(component_model.get_value_as_float(), 0.8, abs_tol=1e-6):
                return
            reopened = True
            swatch.close()
            swatch.open()

        subscription = red_model.subscribe_value_changed_fn(reopen_during_component_input)
        try:
            await self._edit_picker_component("red", 0.8)
        finally:
            del subscription
        self.assertTrue(reopened)
        await omni.kit.ui_test.human_delay()
        self.assertTrue(ui.Workspace.get_window(self.picker_window_title).visible)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))
        await self._drag_picker_control("sv", (0.3, 0.3), (0.5, 0.4))
        released_color = self.color_attribute.Get()
        self.assertNotEqual(released_color, Gf.Vec3f(0.8, 0.2, 0.2))
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))
        self.assertTrue(ui.Workspace.get_window(self.picker_window_title).visible)
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), released_color)

    async def test_update_closed_picker_preserves_readouts_without_uploading_invisible_gradients(self):
        """Closed picker refresh updates USD and readouts without submitting invisible gradient textures."""
        updated_color = Gf.Vec3f(0.3, 0.55, 0.8)
        gradient_uploads = []
        observed_uploads = gradient_uploads

        def record_gradient_upload(frame, event, argument):
            """Observe actual gradient provider calls without replacing rendering or scene authoring."""
            if (
                event == "c_call"
                and frame.f_code.co_filename.replace("\\", "/").endswith("/float_value/color_picker.py")
                and argument.__name__ == "set_bytes_data"
            ):
                observed_uploads.append(frame.f_code.co_name)

        previous_profile = sys.getprofile()
        sys.setprofile(record_gradient_upload)
        try:
            execute(
                "ChangeProperty",
                prop_path=self.color_attribute.GetPath(),
                value=updated_color,
                prev=self.color_attribute.Get(),
                usd_context_name="",
            )
            await omni.kit.ui_test.human_delay()
            await omni.kit.ui_test.human_delay()
        finally:
            sys.setprofile(previous_profile)
        self.assertEqual(self.color_attribute.Get(), updated_color)
        readouts = omni.kit.ui_test.find_all(
            f"{self.window.title}//Frame/**/StringField[*].style_type_name_override=='ColorsWidgetFieldRead'"
        )
        self.assertEqual([field.model.get_value_as_string() for field in readouts], ["0.30", "0.55", "0.80"])

        # Opening after the authoritative refresh must still create usable gradients and gesture history.
        await self._open_picker()
        await self._drag_picker_control("sv", (0.3, 0.3), (0.5, 0.4))
        released_color = self.color_attribute.Get()
        self.assertNotEqual(released_color, updated_color)
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), updated_color)
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), released_color)

        # A visible hue change submits real gradient data, calibrating the observer before its zero-call assertion.
        visible_uploads = []
        observed_uploads = visible_uploads
        sys.setprofile(record_gradient_upload)
        try:
            await self._drag_picker_control("hue", (0.5, 0.2), (0.5, 0.6))
        finally:
            sys.setprofile(previous_profile)
        self.assertTrue(visible_uploads)
        self.assertEqual(gradient_uploads, [])

    async def test_drag_hue_to_bottom_authors_exact_red_and_preserves_release_undo(self):
        """Dragging hue to its lower endpoint authors red and retains the preceding blue gesture."""
        await self._open_picker()
        await self._edit_picker_component("blue", 0.8)
        blue_color = Gf.Vec3f(0.2, 0.2, 0.8)
        self.assertEqual(self.color_attribute.Get(), blue_color)
        await self._drag_picker_control("hue", (0.5, 0.95), (0.5, 1.0))
        red_color = Gf.Vec3f(0.8, 0.2, 0.2)
        for actual, expected in zip(self.color_attribute.Get(), red_color):
            self.assertAlmostEqual(actual, expected, places=6)
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), blue_color)
        redo()
        await omni.kit.ui_test.human_delay()
        for actual, expected in zip(self.color_attribute.Get(), red_color):
            self.assertAlmostEqual(actual, expected, places=6)

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
        """Open the owned popup and edit its actual red control.

        Args:
            value: Red component entered through the picker keyboard control.
        """
        await self._open_picker()
        await self._edit_picker_component("red", value)

    async def _open_picker(self):
        """Open the owned popup.

        Returns:
            Shared item model containing the color components.
        """
        await get_app().next_update_async()
        await get_app().next_update_async()
        swatch = omni.kit.ui_test.find(f"{self.window.title}//Frame/**/ColorPicker[*].identifier=='color_swatch'")
        self.picker_window_title = swatch.widget.window_title
        await swatch.click()
        await omni.kit.ui_test.human_delay()
        return swatch.model

    def _picker_control(self, widget_type, identifier):
        """Find an actual control in this property's owned picker window.

        Args:
            widget_type: Class name used by the UI test query.
            identifier: Control name after the color_picker prefix.

        Returns:
            UI test reference to the requested control.
        """
        return omni.kit.ui_test.find(
            f"{self.picker_window_title}//Frame/**/{widget_type}[*].identifier=='color_picker_{identifier}'"
        )

    async def _focus_picker_component(self, component):
        """Enter an actual FloatDrag text edit without committing its value.

        Args:
            component: Color channel identifier.
        """
        field = self._picker_control("FloatDrag", component)
        edit_events = []
        begin_subscription = field.model.subscribe_begin_edit_fn(lambda _model: edit_events.append("begin"))
        end_subscription = field.model.subscribe_end_edit_fn(lambda _model: edit_events.append("end"))
        try:
            # Kit's FloatDrag input helper uses CTRL-click rather than generic double-click activation.
            await field.click()
            await omni.kit.ui_test.human_delay()
            await emulate_keyboard(
                KeyboardEventType.KEY_PRESS, KeyboardInput.LEFT_CONTROL, KEYBOARD_MODIFIER_FLAG_CONTROL
            )
            await omni.kit.ui_test.human_delay()
            try:
                await field.click()
                await omni.kit.ui_test.human_delay()
            finally:
                await emulate_keyboard(KeyboardEventType.KEY_RELEASE, KeyboardInput.LEFT_CONTROL, 0)
                await omni.kit.ui_test.human_delay()
            self.assertTrue(edit_events)
            self.assertEqual(edit_events[-1], "begin", edit_events)
        finally:
            del begin_subscription, end_subscription

    async def _edit_picker_component(self, component, value):
        """Commit a component value through its real FloatDrag keyboard input.

        Args:
            component: Color channel identifier.
            value: Numeric value entered through keyboard input.
        """
        field = self._picker_control("FloatDrag", component)
        await field.input(str(value))
        await omni.kit.ui_test.human_delay()

    async def _close_picker(self):
        """Dismiss this property's open popup through its actual close button."""
        window = ui.Workspace.get_window(self.picker_window_title) if self.picker_window_title else None
        if window and window.visible:
            await self._picker_control("Button", "close").click()
            await omni.kit.ui_test.human_delay()

    def _assert_picker_closed(self):
        """Verify that the owned picker is absent or hidden."""
        window = ui.Workspace.get_window(self.picker_window_title) if self.picker_window_title else None
        self.assertFalse(window and window.visible)

    async def _drag_picker_control(self, identifier, start, end, attribute=None, widget_type="ImageWithProvider"):
        """Drag an owned control and verify changing live USD values.

        Args:
            identifier: Color picker control identifier.
            start: Fractional horizontal and vertical starting coordinates within the control.
            end: Fractional horizontal and vertical ending coordinates within the control.
            attribute: Optional backing attribute when the fixture's default color is unused.
            widget_type: Class name of the image or numeric control.
        """
        control = self._picker_control(widget_type, identifier)
        start_position = control.position + omni.kit.ui_test.Vec2(control.size.x * start[0], control.size.y * start[1])
        end_position = control.position + omni.kit.ui_test.Vec2(control.size.x * end[0], control.size.y * end[1])
        del control
        color_attribute = self.color_attribute if attribute is None else attribute
        picker_model = omni.kit.ui_test.find(
            f"{self.window.title}//Frame/**/ColorPicker[*].identifier=='color_swatch'"
        ).model
        component_models = [picker_model.get_item_value_model(child) for child in picker_model.get_item_children()]
        await emulate_mouse(MouseEventType.MOVE, start_position)
        await omni.kit.ui_test.human_delay()
        await emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN)
        await omni.kit.ui_test.human_delay()
        moved_colors = [tuple(color_attribute.Get())]
        for step in range(1, 6):
            await emulate_mouse(MouseEventType.MOVE, start_position + (end_position - start_position) * (step / 5))
            await omni.kit.ui_test.human_delay()
            self.assertEqual(
                color_attribute.Get(),
                type(color_attribute.Get())(*(model.get_value_as_float() for model in component_models)),
            )
            moved_colors.append(tuple(color_attribute.Get()))
        await emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
        await omni.kit.ui_test.human_delay()
        self.assertGreater(len(set(moved_colors)), 1, moved_colors)
