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
from asyncio import Event
from contextlib import AsyncExitStack, nullcontext
from math import isclose

import omni.kit.test
import omni.kit.ui_test
import omni.ui as ui
from carb.input import KEYBOARD_MODIFIER_FLAG_CONTROL, KeyboardEventType, KeyboardInput, MouseEventType
from omni.flux.property_widget_builder.delegates import FieldPopupWindow
from omni.flux.property_widget_builder.delegates.float_value.color import ColorField
from omni.flux.property_widget_builder.delegates.float_value.color_picker import ColorPickerWindow
from omni.flux.property_widget_builder.delegates.float_value.color_gradient import ColorGradientField
from omni.flux.property_widget_builder.model.usd import (
    USDAttributeItem,
    USDDelegate,
    USDModel,
    USDPropertyWidget,
    VirtualUSDAttributeItem,
    get_usd_listener_instance,
)
from omni.flux.utils.common.interactive_usd_notices import (
    is_any_interaction_active,
    register_interaction_end_listener,
    register_objects_changed_listener,
)
from omni.flux.utils.widget import InMemoryGroupedKeysModel
from omni.kit.commands import execute
from omni.kit.app import get_app
from omni.kit.ui_test.input import emulate_keyboard, emulate_mouse
from omni.kit.undo import can_redo, can_undo, clear_stack, group, redo, undo
from omni.usd import create_context, get_context
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
        self.addCleanup(clear_stack)
        self.addCleanup(self.window.destroy)
        self.addCleanup(self.model.destroy)
        self.addCleanup(self.property_widget.destroy)
        self.addCleanup(self.model.set_items, [])
        self.addCleanup(self.usd_listener.remove_model, self.model)
        await omni.kit.ui_test.human_delay(human_delay_speed=1)

    async def tearDown(self):
        """Close the owned picker before releasing the UI and temporary stage."""
        try:
            await self._close_picker()
        finally:
            self.doCleanups()
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
            await self._edit_picker_control(component, value)
            components[index] = value
            expected_colors.append(Gf.Vec3f(*components))
            self.assertEqual(self.color_attribute.Get(), expected_colors[-1])
        self.assertTrue(shared_notices)
        self.assertFalse(is_any_interaction_active())
        for color in reversed(expected_colors[:-1]):
            undo()
            await omni.kit.ui_test.human_delay()
            self.assertEqual(self.color_attribute.Get(), color)
            self.assertTrue(ui.Workspace.get_window(self.picker_window_title).visible)
            self.assertEqual(
                Gf.Vec3f(*(model.get_value_as_float() for model in self._picker_component_models())), color
            )
        await self._edit_picker_control("hex", "#GGGGGG")
        self.assertFalse(can_undo())
        self.assertTrue(can_redo())
        for color in expected_colors[1:]:
            redo()
            await omni.kit.ui_test.human_delay()
            self.assertEqual(self.color_attribute.Get(), color)
        await self._close_picker()
        await self._open_picker_and_edit_red(0.6)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.6, 0.5, 0.4))

    async def test_open_gradient_after_color_commits_pending_hex_and_preserves_undo_cancellation(self):
        """Shared-editor handoff commits normal input while cancelled text cannot replace an Undo-restored color."""
        launcher = ui.Window("ColorPickerGradientLauncher", width=400, height=120, position_x=0, position_y=240)
        gradient_model = InMemoryGroupedKeysModel(group_ids=["colors"])
        gradient_field = ColorGradientField(model=gradient_model, group_id="colors")
        self.addCleanup(launcher.destroy)
        self.addCleanup(gradient_model.destroy)
        self.addCleanup(gradient_field.destroy)
        with launcher.frame:
            gradient_field.build_ui(None)
        await omni.kit.ui_test.human_delay()
        gradient_launcher = omni.kit.ui_test.find(
            f"{launcher.title}//Frame/**/Rectangle[*].name=='ColorGradientBarOverlay'"
        )
        original_color = self.color_attribute.Get()
        await self._open_picker()
        await self._drag_picker_control("sv", (0.3, 0.3), (0.5, 0.4))
        released_color = self.color_attribute.Get()
        first_window = ui.Workspace.get_window(self.picker_window_title)
        await self._focus_picker_control("hex")
        await omni.kit.ui_test.emulate_char_press("#4080C0")
        await omni.kit.ui_test.human_delay()

        # Launch a different production editor through its real property control.
        await gradient_launcher.click()
        await omni.kit.ui_test.human_delay()
        self._assert_picker_closed()
        committed_color = Gf.Vec3f(64 / 255, 128 / 255, 192 / 255)
        self.assertEqual(self.color_attribute.Get(), committed_color)
        active_editors = [
            window for window in ui.Workspace.get_windows() if isinstance(window, FieldPopupWindow) and window.visible
        ]
        self.assertEqual(len(active_editors), 1)
        gradient_window = active_editors[0]
        self.addCleanup(gradient_window.close)
        self.assertIn("Gradient Editor", gradient_window.title)
        self.assertFalse(first_window.visible)
        self.assertFalse(is_any_interaction_active())
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), released_color)
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), original_color)
        self.assertFalse(can_undo())
        redo()
        await omni.kit.ui_test.human_delay()
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), committed_color)
        self.assertFalse(can_redo())

        # Undo while another hex edit is buffered must discard it before the next editor takes ownership.
        await self._open_picker()
        self.assertFalse(gradient_window.visible)
        await self._focus_picker_control("hex")
        await omni.kit.ui_test.emulate_char_press("#FF0000")
        await omni.kit.ui_test.human_delay()
        undo()
        await omni.kit.ui_test.human_delay()
        self._assert_picker_closed()
        self.assertEqual(self.color_attribute.Get(), released_color)
        await gradient_launcher.click()
        await omni.kit.ui_test.human_delay()
        active_editors = [
            window for window in ui.Workspace.get_windows() if isinstance(window, FieldPopupWindow) and window.visible
        ]
        self.assertEqual(len(active_editors), 1)
        self.addCleanup(active_editors[0].close)
        await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), released_color)
        self.assertTrue(can_redo())
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), committed_color)

    async def test_named_context_selection_commits_pending_color_only_on_owning_selection_change(self):
        """Named picker dismissal commits one edit without touching the default stage or its history."""
        context_name = f"{__name__}.named_context"
        named_context = get_context(context_name)
        if named_context is None:
            named_context = create_context(context_name)
        self.assertIsNone(named_context.get_stage())
        async with AsyncExitStack() as cleanup:
            cleanup.push_async_callback(named_context.close_stage_async)
            cleanup.callback(clear_stack)
            await named_context.new_stage_async()
            prim_path = str(self.color_attribute.GetPrim().GetPath())
            named_prim = named_context.get_stage().DefinePrim(prim_path, "Xform")
            named_attribute = named_prim.CreateAttribute("color", Sdf.ValueTypeNames.Color3f)
            original_named_color = Gf.Vec3f(0.6, 0.4, 0.2)
            named_attribute.Set(original_named_color)
            named_context.get_stage().DefinePrim("/World/Other", "Xform")
            model = USDModel(context_name=context_name)
            cleanup.callback(model.destroy)
            window = ui.Window("Named color context", width=400, height=200, position_x=0, position_y=240)
            cleanup.callback(window.destroy)
            delegate = USDDelegate()
            with window.frame:
                widget = USDPropertyWidget(context_name=context_name, model=model, delegate=delegate)
            cleanup.callback(widget.destroy)
            model.set_items([USDAttributeItem(context_name, [named_attribute.GetPath()])])
            cleanup.callback(model.set_items, [])
            model.set_prim_paths([named_prim.GetPath()])
            self.usd_listener.add_model(model)
            cleanup.callback(self.usd_listener.remove_model, model)
            cleanup.push_async_callback(self._close_picker)
            default_selection = self.context.get_selection()
            named_selection = named_context.get_selection()
            default_selection.set_selected_prim_paths([prim_path], False)
            named_selection.set_selected_prim_paths([prim_path], False)
            await omni.kit.ui_test.human_delay()

            # Identical property paths in both stages expose edits accidentally routed through the default context.
            clear_stack()
            original_default_color = self.color_attribute.Get()
            edited_default_color = Gf.Vec3f(0.3, 0.5, 0.7)
            execute(
                "ChangeProperty",
                prop_path=self.color_attribute.GetPath(),
                value=edited_default_color,
                prev=original_default_color,
                usd_context_name="",
            )
            await omni.kit.ui_test.human_delay()
            swatch = omni.kit.ui_test.find(f"{window.title}//Frame/**/_ColorSwatch[*].identifier=='color_swatch'")
            await swatch.click()
            await omni.kit.ui_test.human_delay()
            self._remember_picker_window()
            picker_window = ui.Workspace.get_window(self.picker_window_title)
            self.assertTrue(picker_window.visible)
            await self._focus_picker_control("hex")
            await omni.kit.ui_test.emulate_char_press("#4080C0")
            await omni.kit.ui_test.human_delay()

            # An unrelated stage selection must leave the named editor and its buffered input intact.
            default_selection.set_selected_prim_paths([], False)
            await self.context.selection_changed_async()
            await omni.kit.ui_test.human_delay()
            self.assertTrue(picker_window.visible)
            self.assertEqual(named_attribute.Get(), original_named_color)
            self.assertEqual(self.color_attribute.Get(), edited_default_color)

            # Owning selection dismissal finishes the original property's pending text exactly once.
            interaction_ended = Event()

            def record_interaction_end(stage):
                """Observe completion after the named model flushes its deferred USD notices."""
                if stage == named_context.get_stage():
                    interaction_ended.set()

            subscription = register_interaction_end_listener(record_interaction_end)
            cleanup.callback(subscription.revoke)
            named_selection.set_selected_prim_paths(["/World/Other"], False)
            await named_context.selection_changed_async()
            await interaction_ended.wait()
            await omni.kit.ui_test.human_delay()
            self._assert_picker_closed()
            committed_color = Gf.Vec3f(64 / 255, 128 / 255, 192 / 255)
            await self.assertTrueWithRetry(lambda: named_attribute.Get() == committed_color)
            self.assertEqual(self.color_attribute.Get(), edited_default_color)
            self.assertFalse(is_any_interaction_active())
            undo()
            await omni.kit.ui_test.human_delay()
            self.assertEqual(named_attribute.Get(), original_named_color)
            self.assertEqual(self.color_attribute.Get(), edited_default_color)
            undo()
            await omni.kit.ui_test.human_delay()
            self.assertEqual(named_attribute.Get(), original_named_color)
            self.assertEqual(self.color_attribute.Get(), original_default_color)
            self.assertFalse(can_undo())
            redo()
            await omni.kit.ui_test.human_delay()
            self.assertEqual(named_attribute.Get(), original_named_color)
            self.assertEqual(self.color_attribute.Get(), edited_default_color)
            redo()
            await omni.kit.ui_test.human_delay()
            self.assertEqual(named_attribute.Get(), committed_color)
            self.assertEqual(self.color_attribute.Get(), edited_default_color)
            self.assertFalse(can_redo())

    async def test_hold_color_drag_defers_undo_and_virtual_creation_until_release(self):
        """Held input previews existing USD colors while deferring Undo and custom attribute creation."""
        stage = self.context.get_stage()
        original_color = self.color_attribute.Get()
        virtual_path = Sdf.Path("/World/Color.deferred_virtual_color")
        setup_path = Sdf.Path("/World/Color.custom_color_setup")
        creations = []

        def create_color(attribute, value):
            """Create the missing attribute through its real application callback and command."""
            creations.append((attribute.GetPath(), value))
            execute(
                "CreateUsdAttributeCommand",
                prim=stage.GetPrimAtPath(attribute.GetPath().GetPrimPath()),
                attr_name=attribute.GetPath().name,
                attr_type=Sdf.ValueTypeNames.Color3f,
                attr_value=value,
            )
            execute(
                "CreateUsdAttributeCommand",
                prim=stage.GetPrimAtPath(attribute.GetPath().GetPrimPath()),
                attr_name=setup_path.name,
                attr_type=Sdf.ValueTypeNames.Bool,
                attr_value=True,
            )

        for virtual in (False, True):
            with self.subTest(virtual=virtual):
                path = virtual_path if virtual else self.color_attribute.GetPath()
                if virtual:
                    self.model.set_items(
                        [
                            VirtualUSDAttributeItem(
                                "",
                                [path],
                                value_type_name=Sdf.ValueTypeNames.Color3f,
                                default_value=original_color,
                                create_callback=create_color,
                            )
                        ]
                    )
                await omni.kit.ui_test.human_delay()
                clear_stack()
                picker_model = await self._open_picker()
                try:
                    await self._hold_picker_control("sv", (0.3, 0.3), (0.7, 0.5))
                    preview = Gf.Vec3f(*(model.get_value_as_float() for model in picker_model))
                    self.assertNotEqual(preview, original_color)
                    if virtual:
                        self.assertFalse(stage.GetAttributeAtPath(path).IsValid())
                        self.assertEqual(creations, [])
                        self.assertFalse(stage.GetAttributeAtPath(setup_path).IsValid())
                    else:
                        self.assertEqual(stage.GetAttributeAtPath(path).Get(), preview)
                    self.assertFalse(can_undo())
                finally:
                    await emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
                    await omni.kit.ui_test.human_delay()
                    await self._close_picker()
                self.assertEqual(stage.GetAttributeAtPath(path).Get(), preview)
                if virtual:
                    self.assertEqual(creations, [(path, preview)])
                    self.assertTrue(stage.GetAttributeAtPath(setup_path).Get())
                undo()
                await omni.kit.ui_test.human_delay()
                if virtual:
                    self.assertFalse(stage.GetAttributeAtPath(path).IsValid())
                    self.assertFalse(stage.GetAttributeAtPath(setup_path).IsValid())
                else:
                    self.assertEqual(stage.GetAttributeAtPath(path).Get(), original_color)
                self.assertFalse(can_undo())
                redo()
                await omni.kit.ui_test.human_delay()
                self.assertEqual(stage.GetAttributeAtPath(path).Get(), preview)
                if virtual:
                    self.assertTrue(stage.GetAttributeAtPath(setup_path).Get())
                    await self._open_picker()
                    await self._edit_picker_control("red", 0.9)
                    self.assertEqual(len(creations), 1)
                    undo()
                    await omni.kit.ui_test.human_delay()
                    self.assertEqual(stage.GetAttributeAtPath(path).Get(), preview)
                    self.assertTrue(stage.GetAttributeAtPath(setup_path).Get())

    async def test_remove_color_row_during_drag_commits_preview_and_keeps_later_command_undo_separate(self):
        """Removing a dragged row commits its latest preview independently from prior and later commands."""
        await self._open_picker_and_edit_red(0.8)
        released_color = Gf.Vec3f(0.8, 0.2, 0.2)
        self.assertEqual(self.color_attribute.Get(), released_color)

        # Removing the property row must retain the latest live preview even before mouse release.
        try:
            await self._hold_picker_control("sv", (0.3, 0.3), (0.7, 0.5))
            preview = self.color_attribute.Get()
            self.assertNotEqual(preview, released_color)
            self.model.set_items([])
            await omni.kit.ui_test.human_delay()
            self.assertEqual(self.color_attribute.Get(), preview)
        finally:
            await emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
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
        self.assertEqual(self.color_attribute.Get(), preview)
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), released_color)
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
        red_model = picker_model[0]
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
            await self._edit_picker_control("red", 0.8)
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

    async def test_failed_preview_selection_edit_preserves_prior_command_without_empty_undo_or_redo_step(self):
        """A failed later preview rolls back its first write without consuming another undo step."""
        stage = self.context.get_stage()
        session_layer = stage.GetSessionLayer()
        original_color = Gf.Vec3f(0.2, 0.2, 0.2)
        second_color = Gf.Vec3f(0.5, 0.25, 0.25)
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
                await omni.kit.ui_test.human_delay()
                await self._open_picker()

                # The first preview skips the already matching session-layer color.
                with group() if caller_owns_group else nullcontext():
                    execute(
                        "ChangeProperty",
                        prop_path=self.other_attribute.GetPath(),
                        value=2.0,
                        prev=1.0,
                        usd_context_name="",
                    )
                    try:
                        await self._hold_picker_control("sv", (0.5, 0.5), (0.5, 0.5))
                        await self.assertTrueWithRetry(lambda: self.color_attribute.Get() == second_color)
                        self.assertEqual(self.color_attribute.Get(), second_color)
                        self.assertEqual(second_attribute.Get(), second_color)

                        # A later preview now needs the locked target and must cancel the whole live edit.
                        session_layer.SetPermissionToEdit(False)
                        plane = self._picker_control("ImageWithProvider", "sv")
                        await emulate_mouse(
                            MouseEventType.MOVE,
                            plane.position + omni.kit.ui_test.Vec2(plane.size.x * 0.75, plane.size.y * 0.75),
                        )
                        await omni.kit.ui_test.human_delay()
                        await self.assertTrueWithRetry(lambda: self.color_attribute.Get() == original_color)
                    finally:
                        session_layer.SetPermissionToEdit(True)
                        await emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
                        await omni.kit.ui_test.human_delay()
                await self._close_picker()

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

    async def test_picker_drag_inside_caller_group_preserves_outer_operation_and_later_undo(self):
        """A released picker drag commits into its caller's undo group and preserves the subsequent step."""
        await self._open_picker()
        with group():
            execute(
                "ChangeProperty",
                prop_path=self.other_attribute.GetPath(),
                value=2.0,
                prev=1.0,
                usd_context_name="",
            )
            await self._drag_picker_control("sv", (0.3, 0.3), (0.5, 0.5))
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.5, 0.25, 0.25))
        await self._close_picker()
        execute(
            "ChangeProperty",
            prop_path=self.other_attribute.GetPath(),
            value=3.0,
            prev=2.0,
            usd_context_name="",
        )
        undo()
        self.assertEqual(self.other_attribute.Get(), 2.0)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.5, 0.25, 0.25))
        undo()
        self.assertEqual(self.other_attribute.Get(), 1.0)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))

    async def test_drag_picker_applies_complete_colors_once_per_frame_and_groups_undo(self):
        """Held selectors follow live color previews and retain independent Undo for each released gesture."""
        component_models = await self._open_picker()
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
            sv_pointer = await self._hold_picker_control("sv", (0.4, 0.4), (0.7, 0.5))
            self.assertGreater(len(writes), 1)
            self.assertEqual(len({frame for frame, _value, _control in writes}), len(writes), writes)
            for _frame, value, control in writes:
                self.assertEqual(value, control)
            final_color = self.color_attribute.Get()
            self.assertNotEqual(final_color, Gf.Vec3f(0.2, 0.2, 0.2))
            self.assertFalse(can_undo())
            marker = omni.kit.ui_test.find(f"{self.picker_window_title}//Frame/**/Image[*].name=='ColorPickerHandle'")
            self.assertAlmostEqual(marker.center.x, sv_pointer.x, delta=1)
            self.assertAlmostEqual(marker.center.y, sv_pointer.y, delta=1)
        finally:
            listener.Revoke()
            await emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
            await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), final_color)
        try:
            hue_pointer = await self._hold_picker_control("hue", (0.5, 0.25), (0.5, 0.75))
            self.assertNotEqual(self.color_attribute.Get(), final_color)
            marker = omni.kit.ui_test.find(
                f"{self.picker_window_title}//Frame/**/Image[*].name=='ColorPickerHueHandle'"
            )
            self.assertAlmostEqual(marker.center.y, hue_pointer.y, delta=1)
        finally:
            await emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
            await omni.kit.ui_test.human_delay()
        hue_color = self.color_attribute.Get()
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), final_color)
        marker = omni.kit.ui_test.find(f"{self.picker_window_title}//Frame/**/Image[*].name=='ColorPickerHueHandle'")
        self.assertAlmostEqual(marker.center.y, self._picker_control("ImageWithProvider", "hue").position.y, delta=1)
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))
        self.assertFalse(can_undo())
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), final_color)
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), hue_color)
        self.assertFalse(can_redo())
        await self._close_picker()

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

    async def test_cleanup_retained_rgba_picker_releases_components_and_providers_preserving_scene(self):
        """Retiring an edited RGBA field releases owned resources while retained native getters remain safe."""
        attribute = self.color_attribute.GetPrim().CreateAttribute("retired_color", Sdf.ValueTypeNames.Color4f)
        attribute.Set(Gf.Vec4f(0.2, 0.3, 0.4, 0.5))
        item = USDAttributeItem("", [attribute.GetPath()])
        self.model.set_items([item])
        await omni.kit.ui_test.human_delay()
        self.window.frame.clear()
        field = ColorField()
        self.addCleanup(field.cleanup)
        with self.window.frame:
            widgets = field.build_ui(item)
        self.addCleanup(widgets.clear)
        await omni.kit.ui_test.human_delay()
        await self._open_picker_and_edit_red(0.8)
        picker = ui.Workspace.get_window(self.picker_window_title)
        edited_color = Gf.Vec4f(0.8, 0.3, 0.4, 0.5)
        self.assertEqual(attribute.Get(), edited_color)
        self.assertTrue(picker._components)
        self.assertIsNotNone(picker._sv_provider)
        self.assertIsNotNone(picker._hue_provider)
        self.assertIsNotNone(picker._checker_provider)
        red_proxy = self._picker_control("FloatDrag", "red").model
        retained_value, retained_text = red_proxy.get_value_as_float(), red_proxy.get_value_as_string()

        # Generic UI callbacks may retain the retired picker after its owner releases the field.
        field.cleanup()
        await omni.kit.ui_test.human_delay()
        self._assert_picker_closed()
        self.assertFalse(field._components)
        self.assertFalse(picker._components)
        self.assertIsNone(picker._sv_provider)
        self.assertIsNone(picker._hue_provider)
        self.assertIsNone(picker._checker_provider)
        self.assertEqual(attribute.Get(), edited_color)
        self.assertEqual(red_proxy.get_value_as_float(), retained_value)
        self.assertEqual(red_proxy.get_value_as_string(), retained_text)
        updated_color = Gf.Vec4f(0.6, 0.7, 0.8, 0.9)
        item.value_models[0].set_value(updated_color)
        await omni.kit.ui_test.human_delay()
        self.assertEqual(attribute.Get(), updated_color)
        self.assertEqual(red_proxy.get_value_as_float(), retained_value)

    async def test_cleanup_active_color_with_failing_end_subscriber_releases_picker_and_model_updates(self):
        """A failing backing END observer does not retain the active picker or its model bridge."""
        item = USDAttributeItem("", [self.color_attribute.GetPath()])
        self.model.set_items([item])
        await omni.kit.ui_test.human_delay()
        self.window.frame.clear()
        field = ColorField()
        self.addCleanup(field.cleanup)
        with self.window.frame:
            widgets = field.build_ui(item)
        self.addCleanup(widgets.clear)
        await omni.kit.ui_test.human_delay()
        component_models = await self._open_picker()
        try:
            await self._hold_picker_control("sv", (0.3, 0.3), (0.5, 0.4))
            retained_color = Gf.Vec3f(*(model.get_value_as_float() for model in component_models))
            self.assertNotEqual(self.color_attribute.Get(), Gf.Vec3f(0.2))

            def fail_end_edit(_model):
                """Report an actual observer failure while the backing edit is ending."""
                raise RuntimeError("Color END observer failed")

            subscription = self.model.subscribe_item_model_end_edit(fail_end_edit)
            try:
                with self.assertRaisesRegex(RuntimeError, "Color END observer failed"):
                    field.cleanup()
                self.assertIsNone(field._picker)
                self.assertFalse(field._components)
                self.assertIsNone(field._value_model)
            finally:
                del subscription
        finally:
            await emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
            await omni.kit.ui_test.human_delay()
        self._assert_picker_closed()
        await self.assertTrueWithRetry(lambda: not is_any_interaction_active())
        self.assertFalse(is_any_interaction_active())
        updated_color = Gf.Vec3f(0.8, 0.5, 0.4)
        item.value_models[0].set_value(updated_color)
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), updated_color)
        self.assertEqual(Gf.Vec3f(*(model.get_value_as_float() for model in component_models)), retained_color)
        field.cleanup()

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
        await self._assert_single_color_edit_history(original_color)

    async def test_close_during_first_plane_component_notification_commits_complete_color_once(self):
        """Closing during an image gesture commits all RGB components before ending its undo step."""
        original_color = Gf.Vec3f(0.8, 0.2, 0.2)
        for control, start, end, expected in (
            ("sv", (0.5, 0.5), (0.7, 0.6), Gf.Vec3f(0.5, 0.25, 0.25)),
            ("hue", (0.5, 0.5), (0.5, 0.7), Gf.Vec3f(0.2, 0.8, 0.8)),
        ):
            with self.subTest(control=control):
                self.color_attribute.Set(original_color)
                await omni.kit.ui_test.human_delay()
                clear_stack()
                picker_model = await self._open_picker()
                picker = ui.Workspace.get_window(self.picker_window_title)
                red_model = picker_model[0]
                close_requested = False

                def close_on_first_component(_model, picker=picker):
                    """Request normal close from the first real plane-generated RGB notification."""
                    nonlocal close_requested
                    if not close_requested:
                        close_requested = True
                        picker.close()

                subscription = red_model.subscribe_value_changed_fn(close_on_first_component)
                try:
                    await self._hold_picker_control(control, start, end)
                finally:
                    del subscription
                    await emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
                    await omni.kit.ui_test.human_delay()
                self.assertTrue(close_requested)
                self._assert_picker_closed()
                for actual, value in zip(self.color_attribute.Get(), expected):
                    self.assertAlmostEqual(actual, value, places=6)
                self.assertFalse(is_any_interaction_active())
                await self._assert_single_color_edit_history(original_color)

    async def test_cancel_during_first_plane_component_notification_stops_abandoned_rgb_write(self):
        """Cancelling during image input restores authoritative components and prevents later RGB setters."""
        original_color = Gf.Vec3f(0.8, 0.2, 0.2)
        for control in ("sv", "hue"):
            with self.subTest(control=control):
                self.color_attribute.Set(original_color)
                await omni.kit.ui_test.human_delay()
                clear_stack()
                item = self.model.get_all_items()[0]
                component_models = await self._open_picker()
                cancelled = False

                def cancel_on_first_component(_model, item=item):
                    """Cancel the real backing interaction before the remaining plane RGB notifications."""
                    nonlocal cancelled
                    if not cancelled:
                        cancelled = True
                        item.value_models[0].cancel_property_edit_interaction()

                subscription = component_models[0].subscribe_value_changed_fn(cancel_on_first_component)
                try:
                    await self._hold_picker_control(control, (0.5, 0.4), (0.7, 0.6))
                finally:
                    del subscription
                    await emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
                    await omni.kit.ui_test.human_delay()
                self.assertTrue(cancelled)
                self._assert_picker_closed()
                self.assertEqual(self.color_attribute.Get(), original_color)
                self.assertEqual(Gf.Vec3f(*(model.get_value_as_float() for model in component_models)), original_color)
                self.assertFalse(is_any_interaction_active())
                self.assertFalse(can_undo())
                await self._open_picker()
                self.assertTrue(ui.Workspace.get_window(self.picker_window_title).visible)
                self.assertEqual(self.color_attribute.Get(), original_color)
                self.assertEqual(
                    Gf.Vec3f(*(model.get_value_as_float() for model in self._picker_component_models())), original_color
                )
                self.assertFalse(can_undo())
                await self._close_picker()

    async def test_undo_held_plane_drag_discards_preview_and_preserves_completed_gesture_redo(self):
        """Undo while dragging discards the preview and reverses the preceding completed color gesture."""
        original_color = Gf.Vec3f(0.8, 0.2, 0.2)
        committed_color = Gf.Vec3f(0.6, 0.2, 0.2)
        for control in ("sv", "hue"):
            with self.subTest(control=control):
                self.color_attribute.Set(original_color)
                await omni.kit.ui_test.human_delay()
                clear_stack()
                await self._open_picker()
                await self._edit_picker_control("red", committed_color[0])
                try:
                    end_position = await self._hold_picker_control(control, (0.3, 0.3), (0.5, 0.6))
                    dragged_color = self.color_attribute.Get()
                    self.assertNotEqual(dragged_color, original_color)
                    undo()
                    await omni.kit.ui_test.human_delay()
                    self.assertEqual(self.color_attribute.Get(), original_color)
                    self._assert_picker_closed()
                    self.assertTrue(can_redo())
                    # Continuing the held mouse after cancellation must not replay the discarded gesture.
                    await emulate_mouse(MouseEventType.MOVE, end_position + omni.kit.ui_test.Vec2(5, 5))
                    await omni.kit.ui_test.human_delay()
                    self.assertEqual(self.color_attribute.Get(), original_color)
                finally:
                    await emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
                    await omni.kit.ui_test.human_delay()
                self.assertFalse(is_any_interaction_active())
                redo()
                await omni.kit.ui_test.human_delay()
                self.assertEqual(self.color_attribute.Get(), committed_color)
                await self._open_picker()
                await self._drag_picker_control(control, (0.2, 0.2), (0.7, 0.7))
                reopened_color = self.color_attribute.Get()
                self.assertNotEqual(reopened_color, committed_color)
                undo()
                await omni.kit.ui_test.human_delay()
                self.assertEqual(self.color_attribute.Get(), committed_color)
                redo()
                await omni.kit.ui_test.human_delay()
                self.assertEqual(self.color_attribute.Get(), reopened_color)
                await self._close_picker()

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
        red_model = picker_model[0]
        row_removed = False

        def remove_row_during_native_edit(_component_model):
            """Replace the selection during real picker input before its queued write can run."""
            nonlocal row_removed
            if not row_removed:
                row_removed = True
                self.model.set_items([])

        subscription = red_model.subscribe_value_changed_fn(remove_row_during_native_edit)
        try:
            await self._edit_picker_control("red", 0.8)
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
        component_models = await self._open_picker()

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
            await self._edit_picker_control("red", 0.8)
        finally:
            del subscription
        self.assertTrue(external_edit_applied)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.6, 0.7, 0.9))
        self.assertEqual(Gf.Vec3f(*(model.get_value_as_float() for model in component_models)), Gf.Vec3f(0.6, 0.7, 0.9))
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.6, 0.7, 0.9))
        await self._close_picker()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.6, 0.7, 0.9))
        await self._open_picker_and_edit_red(0.4)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.4, 0.7, 0.9))

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

    async def test_unrelated_command_during_component_input_preserves_color_release_and_separate_undo_steps(self):
        """An unrelated command between component notifications preserves the color edit and independent history."""
        execute("ChangeProperty", prop_path=self.other_attribute.GetPath(), value=2.0, prev=1.0, usd_context_name="")
        picker_model = await self._open_picker()
        red_model = picker_model[0]
        unrelated_edit_applied = False

        def change_history_during_component_input(component_model):
            """Author an unrelated value while actual RGB input is still queued."""
            nonlocal unrelated_edit_applied
            if unrelated_edit_applied or not isclose(component_model.get_value_as_float(), 0.8, abs_tol=1e-6):
                return
            unrelated_edit_applied = True
            execute(
                "ChangeProperty", prop_path=self.other_attribute.GetPath(), value=3.0, prev=2.0, usd_context_name=""
            )

        subscription = red_model.subscribe_value_changed_fn(change_history_during_component_input)
        try:
            await self._edit_picker_control("red", 0.8)
        finally:
            del subscription
        self.assertTrue(unrelated_edit_applied)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.8, 0.2, 0.2))
        self.assertEqual(self.other_attribute.Get(), 3.0)
        await self._close_picker()
        self.assertFalse(is_any_interaction_active())
        for intensity in (3.0, 2.0, 1.0):
            undo()
            await omni.kit.ui_test.human_delay()
            self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2, 0.2, 0.2))
            self.assertEqual(self.other_attribute.Get(), intensity)
        self.assertFalse(can_undo())
        for intensity, color in (
            (2.0, Gf.Vec3f(0.2, 0.2, 0.2)),
            (3.0, Gf.Vec3f(0.2, 0.2, 0.2)),
            (3.0, Gf.Vec3f(0.8, 0.2, 0.2)),
        ):
            redo()
            await omni.kit.ui_test.human_delay()
            self.assertEqual(self.color_attribute.Get(), color)
            self.assertEqual(self.other_attribute.Get(), intensity)

    async def test_close_pending_hsv_hex_text_commits_once_and_undo_cancels_later_buffer(self):
        """Dismissal commits focused HSV or hex text, while Undo cancels later input without replaying it."""
        original_color = Gf.Vec3f(0.8, 0.2, 0.2)
        for identifier, text, pending, expected, edited_color in (
            (
                "hue_value",
                "0.5",
                "0.75",
                Gf.Vec3f(0.2, 0.8, 0.8),
                Gf.Vec3f(0.5, 0.2, 0.8),
            ),
            (
                "hex",
                "#0080FF",
                "#00FF",
                Gf.Vec3f(0, 128 / 255, 1),
                Gf.Vec3f(0, 128 / 255, 1),
            ),
            (
                "hex",
                "(0,.5,1)",
                "(0,1",
                Gf.Vec3f(0, 128 / 255, 1),
                Gf.Vec3f(0, 128 / 255, 1),
            ),
        ):
            with self.subTest(identifier=identifier, text=text):
                self.color_attribute.Set(original_color)
                await omni.kit.ui_test.human_delay()
                clear_stack()
                await self._open_picker()
                await self._focus_picker_control(identifier)
                await omni.kit.ui_test.emulate_char_press(text)
                await omni.kit.ui_test.human_delay()
                await self._close_picker()
                self._assert_picker_closed()
                self.assertEqual(self.color_attribute.Get(), expected)
                undo()
                await omni.kit.ui_test.human_delay()
                self.assertEqual(self.color_attribute.Get(), original_color)
                self.assertFalse(can_undo())
                redo()
                await omni.kit.ui_test.human_delay()
                await self._open_picker()
                await self._focus_picker_control(identifier)
                await omni.kit.ui_test.emulate_char_press(pending)
                await omni.kit.ui_test.human_delay()
                self.assertEqual(self.color_attribute.Get(), edited_color)
                undo()
                await omni.kit.ui_test.human_delay()
                self._assert_picker_closed()
                self.assertEqual(self.color_attribute.Get(), original_color)
                await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
                await omni.kit.ui_test.human_delay()
                self.assertEqual(self.color_attribute.Get(), original_color)
                self.assertTrue(can_redo())
                redo()
                await omni.kit.ui_test.human_delay()
                self.assertEqual(self.color_attribute.Get(), expected)

    async def test_reopen_after_close_during_component_input_preserves_color_and_gesture_history(self):
        """Reopening after interrupted numeric input preserves the committed color and later gesture history."""
        await self._open_picker()
        picker = ui.Workspace.get_window(self.picker_window_title)
        red_model = self._picker_control("FloatDrag", "red").model
        close_requested = False

        def close_during_component_input(component_model):
            """Close the popup while actual numeric input is dispatching."""
            nonlocal close_requested
            if close_requested or not isclose(component_model.get_value_as_float(), 0.8, abs_tol=1e-6):
                return
            close_requested = True
            picker.close()

        subscription = red_model.subscribe_value_changed_fn(close_during_component_input)
        try:
            await self._edit_picker_control("red", 0.8)
        finally:
            del subscription
        self.assertTrue(close_requested)
        self._assert_picker_closed()
        await self._open_picker()
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

    async def _assert_single_color_edit_history(self, original_color):
        """Verify that one Undo and Redo restore both ends of the completed color edit."""
        edited_color = self.color_attribute.Get()
        undo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), original_color)
        self.assertFalse(can_undo())
        redo()
        await omni.kit.ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), edited_color)
        self.assertFalse(can_redo())

    async def _open_picker_and_edit_red(self, value):
        """Open the owned popup and edit its actual red control.

        Args:
            value: Red component entered through the picker keyboard control.
        """
        await self._open_picker()
        await self._edit_picker_control("red", value)

    async def _open_picker(self):
        """Open the owned popup.

        Returns:
            Actual RGB or RGBA channel models used by the popup controls.
        """
        await omni.kit.ui_test.human_delay(human_delay_speed=2)
        swatch = omni.kit.ui_test.find(f"{self.window.title}//Frame/**/_ColorSwatch[*].identifier=='color_swatch'")
        await swatch.click()
        await omni.kit.ui_test.human_delay()
        if self._remember_picker_window() is None:
            return []
        return self._picker_component_models()

    def _remember_picker_window(self):
        """Remember the active production color popup after native event dispatch."""
        windows = [
            window for window in ui.Workspace.get_windows() if isinstance(window, ColorPickerWindow) and window.visible
        ]
        self.picker_window_title = windows[0].title if windows else None
        return windows[0] if windows else None

    def _picker_component_models(self):
        """Return the actual channel models exposed by this popup's RGB(A) controls."""
        fields = omni.kit.ui_test.find_all(f"{self.picker_window_title}//Frame/**/FloatDrag[*]")
        models = {field.widget.identifier: field.model for field in fields}
        return [
            models[f"color_picker_{channel}"]
            for channel in ("red", "green", "blue", "alpha")
            if f"color_picker_{channel}" in models
        ]

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

    async def _focus_picker_control(self, identifier):
        """Select an actual numeric or hexadecimal editor without committing its value.

        Args:
            identifier: Color control identifier.
        """
        if identifier == "hex":
            await self._picker_control("StringField", identifier).double_click()
            await omni.kit.ui_test.human_delay()
        else:
            await self._focus_picker_component(identifier)
        await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.A, KEYBOARD_MODIFIER_FLAG_CONTROL)
        await omni.kit.ui_test.human_delay()

    async def _focus_picker_component(self, identifier):
        """Enter a native FloatDrag text edit and verify that its edit gesture began.

        Args:
            identifier: Numeric color control identifier.
        """
        field = self._picker_control("FloatDrag", identifier)
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

    async def _edit_picker_control(self, identifier, value):
        """Commit a numeric or hexadecimal value through the real editor's keyboard input.

        Args:
            identifier: Color control identifier.
            value: Value entered through keyboard input.
        """
        await self._focus_picker_control(identifier)
        await omni.kit.ui_test.emulate_char_press(str(value))
        await omni.kit.ui_test.human_delay()
        await omni.kit.ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
        await omni.kit.ui_test.human_delay()

    async def _close_picker(self):
        """Dismiss this property's open popup by clicking outside its native window."""
        window = ui.Workspace.get_window(self.picker_window_title) if self.picker_window_title else None
        if window and window.visible:
            await omni.kit.ui_test.emulate_mouse_move_and_click(
                omni.kit.ui_test.Vec2(
                    ui.Workspace.get_main_window_width() - 2,
                    ui.Workspace.get_main_window_height() - 2,
                )
            )
            await omni.kit.ui_test.human_delay()

    def _assert_picker_closed(self):
        """Verify that the owned picker is absent or hidden."""
        window = ui.Workspace.get_window(self.picker_window_title) if self.picker_window_title else None
        self.assertFalse(window and window.visible)

    async def _hold_picker_control(self, identifier, start, end):
        """Move an actual plane gesture while leaving its mouse button held.

        Args:
            identifier: SV or hue control identifier.
            start: Fractional starting coordinates within the control.
            end: Fractional ending coordinates within the control.

        Returns:
            Final pointer position for further held input after cancellation.
        """
        control = self._picker_control("ImageWithProvider", identifier)
        start_position = control.position + omni.kit.ui_test.Vec2(control.size.x * start[0], control.size.y * start[1])
        end_position = control.position + omni.kit.ui_test.Vec2(control.size.x * end[0], control.size.y * end[1])
        del control
        await emulate_mouse(MouseEventType.MOVE, start_position)
        await omni.kit.ui_test.human_delay()
        await emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN)
        await omni.kit.ui_test.human_delay()
        await emulate_mouse(MouseEventType.MOVE, end_position)
        await omni.kit.ui_test.human_delay()
        return end_position

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
        component_models = self._picker_component_models()
        await emulate_mouse(MouseEventType.MOVE, start_position)
        await omni.kit.ui_test.human_delay()
        try:
            await emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN)
            await omni.kit.ui_test.human_delay()
            moved_colors = [tuple(color_attribute.Get())]
            for step in range(1, 6):
                await emulate_mouse(MouseEventType.MOVE, start_position + (end_position - start_position) * (step / 5))
                await omni.kit.ui_test.human_delay()
                await self.assertTrueWithRetry(
                    lambda: (
                        color_attribute.Get()
                        == type(color_attribute.Get())(*(model.get_value_as_float() for model in component_models))
                    )
                )
                moved_colors.append(tuple(color_attribute.Get()))
        finally:
            await emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
            await omni.kit.ui_test.human_delay()
        self.assertGreater(len(set(moved_colors)), 1, moved_colors)
