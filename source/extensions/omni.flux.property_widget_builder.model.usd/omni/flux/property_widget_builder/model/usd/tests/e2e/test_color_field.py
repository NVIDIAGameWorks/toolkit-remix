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

from asyncio import Event
from contextlib import AsyncExitStack, asynccontextmanager
from math import isclose
from uuid import uuid4

import omni.ui as ui
from carb.input import KEYBOARD_MODIFIER_FLAG_CONTROL, KeyboardInput, MouseEventType
from omni.flux.property_widget_builder.delegates.float_value.color_picker import ColorPickerWindow
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
)
from omni.kit import ui_test
from omni.kit.app import get_app
from omni.kit.commands import execute
from omni.kit.test import AsyncTestCase
from omni.kit.ui_test.input import emulate_mouse
from omni.kit.undo import can_redo, can_undo, clear_stack, redo, undo
from omni.usd import create_context, get_context
from pxr import Gf, Sdf, Tf, Usd, UsdLux


class TestColorField(AsyncTestCase):
    """Exercise color picker integration with USD authoring, history, and owner cleanup."""

    _WINDOW_WIDTH = ui.Pixel(400)
    _WINDOW_HEIGHT = ui.Pixel(200)

    async def setUp(self):
        """Build a production property row and register its real USD listener."""
        self.context = get_context("")
        await self.context.new_stage_async()
        prim = self.context.get_stage().DefinePrim("/World/Color", "Xform")
        self.color_attribute = prim.CreateAttribute("color", Sdf.ValueTypeNames.Color3f)
        self.color_attribute.Set(Gf.Vec3f(0.2))
        other_prim = self.context.get_stage().DefinePrim("/World/Other", "Xform")
        self.other_attribute = other_prim.CreateAttribute("intensity", Sdf.ValueTypeNames.Float)
        self.other_attribute.Set(1.0)
        self.model = USDModel(context_name="")
        self.window = ui.Window(
            f"{self.__class__.__name__}_{uuid4()}",
            height=self._WINDOW_HEIGHT,
            width=self._WINDOW_WIDTH,
            position_x=0,
            position_y=0,
        )
        self.picker = None
        self.delegate = USDDelegate()
        with self.window.frame:
            self.property_widget = USDPropertyWidget(context_name="", model=self.model, delegate=self.delegate)
        self.model.set_items([USDAttributeItem("", [self.color_attribute.GetPath()])])
        self.model.set_prim_paths([prim.GetPath()])
        self.usd_listener = get_usd_listener_instance()
        self.assertIsNotNone(self.usd_listener)
        self.usd_listener.add_model(self.model)
        self.addCleanup(clear_stack)
        self.addCleanup(self.window.destroy)
        self.addCleanup(self.model.destroy)
        self.addCleanup(self.property_widget.destroy)
        self.addCleanup(self.model.set_items, [])
        self.addCleanup(self.usd_listener.remove_model, self.model)
        await ui_test.human_delay()

    async def tearDown(self):
        """Dismiss the owned popup before releasing the property and temporary stage."""
        try:
            await self._close_picker()
        finally:
            self.doCleanups()
            await self.context.close_stage_async()

    async def test_type_color_and_dismiss_pending_hex_preserves_undo_and_cancels_later_buffer(self):
        """Typed edits and focused dismissal author separate steps; Undo discards later buffered text."""
        await self._open_picker()
        colors = [Gf.Vec3f(0.2), Gf.Vec3f(0.8, 0.2, 0.2), Gf.Vec3f(0.8, 0.5, 0.2)]
        for identifier, value, expected in (("red", "0.8", colors[1]), ("green", "0.5", colors[2])):
            await self._control(identifier).input(value)
            await ui_test.human_delay()
            self.assertEqual(self.color_attribute.Get(), expected)
        for expected in reversed(colors[:-1]):
            undo()
            await ui_test.human_delay()
            self.assertEqual(self.color_attribute.Get(), expected)
            self.assertTrue(self.picker.visible)
            self.assertEqual(
                Gf.Vec3f(*(self._control(channel).model.get_value_as_float() for channel in ("red", "green", "blue"))),
                expected,
            )
        self.assertFalse(can_undo())
        for expected in colors[1:]:
            redo()
            await ui_test.human_delay()
            self.assertEqual(self.color_attribute.Get(), expected)

        # Dismissal must commit the focused text before native controls disappear.
        await self._type_pending_hex("#4080C0")
        await self._close_picker()
        committed = Gf.Vec3f(64 / 255, 128 / 255, 192 / 255)
        self.assertEqual(self.color_attribute.Get(), committed)
        undo()
        await ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), colors[-1])
        redo()
        await ui_test.human_delay()
        await self._open_picker()
        await self._type_pending_hex("#FF0000")
        undo()
        await ui_test.human_delay()
        self.assertFalse(self.picker.visible)
        await ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
        await ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), colors[-1])
        self.assertTrue(can_redo())
        self.assertFalse(is_any_interaction_active())
        redo()
        await ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), committed)

    async def test_named_selection_commits_pending_color_only_in_owning_context(self):
        """Identical paths in two contexts retain independent selection ownership and command history."""
        context_name = f"{__name__}.named_context"
        named_context = get_context(context_name) or create_context(context_name)
        self.assertIsNone(named_context.get_stage())
        async with AsyncExitStack() as cleanup:
            cleanup.push_async_callback(named_context.close_stage_async)
            cleanup.callback(clear_stack)
            await named_context.new_stage_async()
            prim = named_context.get_stage().DefinePrim("/World/Color", "Xform")
            attribute = prim.CreateAttribute("color", Sdf.ValueTypeNames.Color3f)
            original = Gf.Vec3f(0.6, 0.4, 0.2)
            attribute.Set(original)
            named_context.get_stage().DefinePrim("/World/Other", "Xform")
            model = USDModel(context_name=context_name)
            cleanup.callback(model.destroy)
            window = ui.Window(
                "Named color context",
                width=self._WINDOW_WIDTH,
                height=self._WINDOW_HEIGHT,
                position_x=0,
                position_y=240,
            )
            cleanup.callback(window.destroy)
            delegate = USDDelegate()
            with window.frame:
                widget = USDPropertyWidget(context_name=context_name, model=model, delegate=delegate)
            cleanup.callback(widget.destroy)
            model.set_items([USDAttributeItem(context_name, [attribute.GetPath()])])
            cleanup.callback(model.set_items, [])
            model.set_prim_paths([prim.GetPath()])
            self.usd_listener.add_model(model)
            cleanup.callback(self.usd_listener.remove_model, model)
            cleanup.push_async_callback(self._close_picker)
            for context in (self.context, named_context):
                context.get_selection().set_selected_prim_paths([str(prim.GetPath())], False)
            await ui_test.human_delay()
            clear_stack()
            default_original = self.color_attribute.Get()
            default_edited = Gf.Vec3f(0.3, 0.5, 0.7)
            execute(
                "ChangeProperty",
                prop_path=self.color_attribute.GetPath(),
                value=default_edited,
                prev=default_original,
                usd_context_name="",
            )
            await ui_test.human_delay()
            await self._open_picker(window)
            await self._type_pending_hex("#4080C0")

            # A different context's selection must not dismiss or commit the named editor.
            self.context.get_selection().set_selected_prim_paths([], False)
            await self.context.selection_changed_async()
            await ui_test.human_delay()
            self.assertTrue(self.picker.visible)
            self.assertEqual(attribute.Get(), original)
            self.assertEqual(self.color_attribute.Get(), default_edited)
            interaction_ended = Event()

            def record_interaction_end(stage):
                """Observe the owning model's deferred interaction completion."""
                if stage == named_context.get_stage():
                    interaction_ended.set()

            subscription = register_interaction_end_listener(record_interaction_end)
            cleanup.callback(subscription.revoke)
            named_context.get_selection().set_selected_prim_paths(["/World/Other"], False)
            await named_context.selection_changed_async()
            await interaction_ended.wait()
            await ui_test.human_delay()
            committed = Gf.Vec3f(64 / 255, 128 / 255, 192 / 255)
            self.assertFalse(self.picker.visible)
            self.assertEqual(attribute.Get(), committed)
            self.assertEqual(self.color_attribute.Get(), default_edited)
            self.assertFalse(is_any_interaction_active())
            for named_color, default_color in ((original, default_edited), (original, default_original)):
                undo()
                await ui_test.human_delay()
                self.assertEqual(attribute.Get(), named_color)
                self.assertEqual(self.color_attribute.Get(), default_color)
            self.assertFalse(can_undo())
            for named_color, default_color in ((original, default_edited), (committed, default_edited)):
                redo()
                await ui_test.human_delay()
                self.assertEqual(attribute.Get(), named_color)
                self.assertEqual(self.color_attribute.Get(), default_color)
            self.assertFalse(can_redo())

    async def test_release_virtual_color_creates_callback_attributes_in_one_undo_step(self):
        """Virtual previews defer both real creation commands until release and undo them together."""
        stage = self.context.get_stage()
        path = Sdf.Path("/World/Color.deferred_virtual_color")
        setup_path = Sdf.Path("/World/Color.custom_color_setup")
        creations = []

        def create_color(attribute, value):
            """Author the missing color and companion setup through real commands."""
            creations.append((attribute.GetPath(), value))
            for name, value_type, authored in (
                (path.name, Sdf.ValueTypeNames.Color3f, value),
                (setup_path.name, Sdf.ValueTypeNames.Bool, True),
            ):
                execute(
                    "CreateUsdAttributeCommand",
                    prim=stage.GetPrimAtPath(path.GetPrimPath()),
                    attr_name=name,
                    attr_type=value_type,
                    attr_value=authored,
                )

        self.model.set_items(
            [
                VirtualUSDAttributeItem(
                    "",
                    [path],
                    value_type_name=Sdf.ValueTypeNames.Color3f,
                    default_value=Gf.Vec3f(0.2),
                    create_callback=create_color,
                )
            ]
        )
        await ui_test.human_delay()
        components = await self._open_picker()
        async with self._held_drag():
            preview = Gf.Vec3f(*(model.get_value_as_float() for model in components))
            self.assertNotEqual(preview, Gf.Vec3f(0.2))
            self.assertFalse(stage.GetAttributeAtPath(path).IsValid())
            self.assertFalse(stage.GetAttributeAtPath(setup_path).IsValid())
            self.assertEqual(creations, [])
            self.assertFalse(can_undo())
        await self._close_picker()
        self.assertEqual(stage.GetAttributeAtPath(path).Get(), preview)
        self.assertTrue(stage.GetAttributeAtPath(setup_path).Get())
        self.assertEqual(creations, [(path, preview)])
        undo()
        await ui_test.human_delay()
        self.assertFalse(stage.GetAttributeAtPath(path).IsValid())
        self.assertFalse(stage.GetAttributeAtPath(setup_path).IsValid())
        self.assertFalse(can_undo())
        redo()
        await ui_test.human_delay()
        self.assertEqual(stage.GetAttributeAtPath(path).Get(), preview)
        self.assertTrue(stage.GetAttributeAtPath(setup_path).Get())
        await self._open_picker()
        await self._control("red").input("0.9")
        await ui_test.human_delay()
        self.assertEqual(len(creations), 1)
        undo()
        await ui_test.human_delay()
        self.assertEqual(stage.GetAttributeAtPath(path).Get(), preview)
        self.assertTrue(stage.GetAttributeAtPath(setup_path).Get())

    async def test_remove_dragged_light_row_cancels_live_preview_with_independent_undo(self):
        """Layered light edits survive refresh; row removal cancels only the unfinished gesture."""
        stage = self.context.get_stage()
        light_layer = Sdf.Layer.CreateAnonymous("light.usda")
        authoring_layer = stage.GetRootLayer()
        authoring_layer.subLayerPaths.append(light_layer.identifier)
        with Usd.EditContext(stage, light_layer):
            light = UsdLux.SphereLight.Define(stage, "/World/Light")
            self.color_attribute = UsdLux.LightAPI(light.GetPrim()).CreateColorAttr(Gf.Vec3f(0.2))
        item = USDAttributeItem("", [self.color_attribute.GetPath()])
        for _ in range(3):
            self.model.set_items([item])
            await ui_test.human_delay()
        self.model.set_prim_paths([light.GetPath()])
        self.assertIsNone(authoring_layer.GetPropertyAtPath(self.color_attribute.GetPath()))
        components = await self._open_picker()
        writes = []

        def record_color_write(notice, _stage):
            """Observe complete USD colors and their authoritative controls in each preview frame."""
            if self.color_attribute.GetPath() in notice.GetChangedInfoOnlyPaths():
                writes.append(
                    (
                        get_app().get_update_number(),
                        self.color_attribute.Get(),
                        Gf.Vec3f(*(model.get_value_as_float() for model in components)),
                    )
                )

        listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, record_color_write, stage)
        try:
            async with self._held_drag():
                first_color = self.color_attribute.Get()
                self.assertNotEqual(first_color, Gf.Vec3f(0.2))
                self.assertFalse(can_undo())
                self.assertGreater(len(writes), 1)
                self.assertEqual(len({frame for frame, _value, _controls in writes}), len(writes), writes)
                for _frame, value, controls in writes:
                    self.assertEqual(value, controls)
        finally:
            listener.Revoke()
        self.assertTrue(self.picker.visible)
        self.assertEqual(self.color_attribute.Get(), first_color)
        undo()
        await ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2))
        self.assertIsNone(authoring_layer.GetPropertyAtPath(self.color_attribute.GetPath()))
        self.assertFalse(can_undo())
        redo()
        await ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), first_color)
        self.assertIsNotNone(authoring_layer.GetPropertyAtPath(self.color_attribute.GetPath()))

        # Removing the row cancels its unfinished preview and preserves the preceding committed gesture.
        async with self._held_drag(start=(0.2, 0.2), end=(0.5, 0.6)):
            preview = self.color_attribute.Get()
            self.assertNotEqual(preview, first_color)
            self.model.set_items([])
            await ui_test.human_delay()
            self.assertEqual(self.color_attribute.Get(), first_color)
        self.assertFalse(self.picker.visible)
        self.assertFalse(self.picker.edit_started)
        self.assertFalse(self.picker.edit_finished)
        self.assertFalse(is_any_interaction_active())
        components[0].set_value(0.9)
        await ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), first_color)
        execute("ChangeProperty", prop_path=self.other_attribute.GetPath(), value=2.0, prev=1.0, usd_context_name="")
        for intensity, color in ((1.0, first_color), (1.0, Gf.Vec3f(0.2))):
            undo()
            await ui_test.human_delay()
            self.assertEqual(self.other_attribute.Get(), intensity)
            self.assertEqual(self.color_attribute.Get(), color)
        self.assertFalse(can_undo())
        self.assertIsNone(authoring_layer.GetPropertyAtPath(self.color_attribute.GetPath()))

    async def test_undo_before_queued_color_preview_discards_input_and_preserves_unrelated_redo(self):
        """Undo during native input cancels the queued color before its first USD write."""
        execute("ChangeProperty", prop_path=self.other_attribute.GetPath(), value=2.0, prev=1.0, usd_context_name="")
        components = await self._open_picker()
        undo_applied = False

        def undo_during_native_edit(component_model):
            """Interrupt the actual red notification before the deferred authoring task runs."""
            nonlocal undo_applied
            if not undo_applied and isclose(component_model.get_value_as_float(), 0.8, abs_tol=1e-6):
                undo_applied = True
                undo()

        subscription = components[0].subscribe_value_changed_fn(undo_during_native_edit)
        try:
            await self._control("red").input("0.8")
            await ui_test.human_delay()
        finally:
            del subscription
        self.assertTrue(undo_applied)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2))
        self.assertEqual(self.other_attribute.Get(), 1.0)
        await ui_test.human_delay()
        self.assertFalse(is_any_interaction_active())
        self.assertTrue(can_redo())
        redo()
        await ui_test.human_delay()
        self.assertEqual(self.other_attribute.Get(), 2.0)
        self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2))

    async def test_undo_held_color_drag_ignores_continued_mouse_input_and_preserves_redo(self):
        """Undo cancels a published preview and later mouse movement cannot replay the abandoned drag."""
        await self._open_picker()
        await self._control("red").input("0.6")
        await ui_test.human_delay()
        committed = Gf.Vec3f(0.6, 0.2, 0.2)
        self.assertEqual(self.color_attribute.Get(), committed)
        async with self._held_drag() as end_position:
            self.assertNotEqual(self.color_attribute.Get(), committed)
            undo()
            await ui_test.human_delay()
            self.assertFalse(self.picker.visible)
            self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2))
            self.assertTrue(can_redo())
            await emulate_mouse(MouseEventType.MOVE, end_position + ui_test.Vec2(5, 5))
            await ui_test.human_delay()
            self.assertEqual(self.color_attribute.Get(), Gf.Vec3f(0.2))
        self.assertFalse(is_any_interaction_active())
        redo()
        await ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), committed)
        await self._open_picker()
        async with self._held_drag(start=(0.2, 0.2), end=(0.7, 0.7)):
            reopened = self.color_attribute.Get()
            self.assertNotEqual(reopened, committed)
        undo()
        await ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), committed)
        redo()
        await ui_test.human_delay()
        self.assertEqual(self.color_attribute.Get(), reopened)

    async def test_locked_preview_target_rolls_back_other_target_without_consuming_prior_history(self):
        """A later native preview failure restores mixed targets and leaves only the prior command in history."""
        stage = self.context.get_stage()
        session_layer = stage.GetSessionLayer()
        original = Gf.Vec3f(0.2)
        second_color = Gf.Vec3f(0.5, 0.25, 0.25)
        with Usd.EditContext(stage, session_layer):
            attribute = stage.DefinePrim("/World/LockedColor", "Xform").CreateAttribute(
                "color", Sdf.ValueTypeNames.Color3f
            )
            attribute.Set(second_color)
        self.model.set_items([USDAttributeItem("", [self.color_attribute.GetPath(), attribute.GetPath()])])
        await ui_test.human_delay()
        await self._open_picker()
        execute("ChangeProperty", prop_path=self.other_attribute.GetPath(), value=2.0, prev=1.0, usd_context_name="")
        try:
            # The first preview matches the session target; the next needs a write to its now-locked layer.
            async with self._held_drag(start=(0.5, 0.5), end=(0.5, 0.5)):
                self.assertEqual(self.color_attribute.Get(), second_color)
                self.assertEqual(attribute.Get(), second_color)
                session_layer.SetPermissionToEdit(False)
                plane = self._control("sv", "ImageWithProvider")
                await emulate_mouse(
                    MouseEventType.MOVE, plane.position + ui_test.Vec2(plane.size.x * 0.75, plane.size.y * 0.75)
                )
                await ui_test.human_delay()
                await self.assertTrueWithRetry(lambda: self.color_attribute.Get() == original)
        finally:
            session_layer.SetPermissionToEdit(True)
        await self._close_picker()
        self.assertEqual(self.color_attribute.Get(), original)
        self.assertEqual(attribute.Get(), second_color)
        self.assertEqual(self.other_attribute.Get(), 2.0)
        self.assertFalse(can_redo())
        undo()
        await ui_test.human_delay()
        self.assertEqual(self.other_attribute.Get(), 1.0)
        self.assertFalse(can_undo())
        redo()
        await ui_test.human_delay()
        self.assertEqual(self.other_attribute.Get(), 2.0)
        self.assertFalse(can_redo())
        self.assertEqual(self.color_attribute.Get(), original)
        self.assertEqual(attribute.Get(), second_color)

    async def _open_picker(self, window=None):
        """Open a real property swatch and return its native RGB control models."""
        owner = self.window if window is None else window
        swatch = ui_test.find(f"{owner.title}//Frame/**/_ColorSwatch[*].identifier=='color_swatch'")
        await swatch.click()
        await ui_test.human_delay()
        windows = [
            window for window in ui.Workspace.get_windows() if isinstance(window, ColorPickerWindow) and window.visible
        ]
        self.assertEqual(len(windows), 1)
        self.picker = windows[0]
        return [self._control(channel).model for channel in ("red", "green", "blue")]

    def _control(self, identifier, widget_type="FloatDrag"):
        """Find an owned production control by its stable picker identifier."""
        return ui_test.find(f"{self.picker.title}//Frame/**/{widget_type}[*].identifier=='color_picker_{identifier}'")

    async def _type_pending_hex(self, text):
        """Leave text focused so dismissal or Undo determines whether it commits."""
        await self._control("hex", "StringField").double_click()
        await ui_test.human_delay()
        await ui_test.emulate_keyboard_press(KeyboardInput.A, KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.human_delay()
        await ui_test.emulate_char_press(text)
        await ui_test.human_delay()

    async def _close_picker(self):
        """Dismiss the owned native popup through an outside click."""
        if self.picker and self.picker.visible:
            await ui_test.emulate_mouse_move_and_click(
                ui_test.Vec2(
                    ui.Workspace.get_main_window_width() - 2,
                    ui.Workspace.get_main_window_height() - 2,
                )
            )
            await ui_test.human_delay()

    @asynccontextmanager
    async def _held_drag(self, start=(0.3, 0.3), end=(0.7, 0.5)):
        """Hold a native SV gesture and always release its mouse button when the workflow exits."""
        control = self._control("sv", "ImageWithProvider")
        first = control.position + ui_test.Vec2(control.size.x * start[0], control.size.y * start[1])
        last = control.position + ui_test.Vec2(control.size.x * end[0], control.size.y * end[1])
        del control
        try:
            await emulate_mouse(MouseEventType.MOVE, first)
            await ui_test.human_delay()
            await emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN)
            await ui_test.human_delay()
            await emulate_mouse(MouseEventType.MOVE, last)
            await ui_test.human_delay()
            yield last
        finally:
            await emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
            await ui_test.human_delay()
