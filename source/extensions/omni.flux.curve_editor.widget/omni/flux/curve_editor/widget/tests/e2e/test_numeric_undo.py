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

from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

import omni.kit.app
import omni.kit.commands
import omni.kit.test
import omni.kit.ui_test as ui_test
import omni.kit.undo
import omni.usd
from carb.input import (
    KEYBOARD_MODIFIER_FLAG_CONTROL,
    KEYBOARD_MODIFIER_FLAG_SHIFT,
    KeyboardEventType,
    KeyboardInput,
    MouseEventType,
)
from omni.flux.curve_editor.widget.tests.e2e.test_primvar_integration import ALL_SUFFIXES
from omni.flux.fcurve.widget import CurveBounds, FCurveWidget, KeyReference
from omni.flux.property_widget_builder.model.usd.curve_primvar import PropertyPrimvarCurveModel
from omni.flux.property_widget_builder.model.usd.field_builders.curve import CurveFieldEditor
from omni.kit.actions.core import get_action_registry
from omni.kit.hotkeys.core import HotkeyFilter, get_hotkey_context, get_hotkey_registry

__all__ = ["TestCurveEditorNumericUndo"]


class TestCurveEditorNumericUndo(omni.kit.test.AsyncTestCase):
    """Exercise numeric editing and undo through the production curve popup."""

    _CURVE_IDS = ("opacity:x", "opacity:y")
    _SOURCE_PATH = "/World/CurveHost"
    _PENDING_REDO_PATH = "/World/PendingRedo"

    @asynccontextmanager
    async def _held_pointer(self, start):
        """Hold the settled pointer and release it when the gesture finishes."""
        await ui_test.input.emulate_mouse_move(start)
        await ui_test.human_delay()
        try:
            await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN)
            await ui_test.human_delay()
            yield start
        finally:
            await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
            await ui_test.human_delay()

    async def setUp(self):
        """Load existing curve data and add one independently valued visible channel."""
        self._editor = None
        self._context = omni.usd.get_context("")
        extension_path = (
            omni.kit.app.get_app().get_extension_manager().get_extension_path_by_module("omni.flux.curve_editor.widget")
        )
        fixture = Path(extension_path) / "data/tests/usd/primvar_curve_test_fixture.usda"
        opened, error = await self._context.open_stage_async(str(fixture))
        self.assertTrue(opened, error)
        self._stage = self._context.get_stage()
        self._stage.SetEditTarget(self._stage.GetSessionLayer())
        self._paths = [self._SOURCE_PATH]
        prim = self._stage.GetPrimAtPath(self._SOURCE_PATH)
        for suffix in ALL_SUFFIXES:
            attr = prim.GetAttribute(f"primvars:opacity:x:{suffix}")
            prim.CreateAttribute(f"primvars:opacity:y:{suffix}", attr.GetTypeName()).Set(attr.Get())
        prim.GetAttribute("primvars:opacity:x:values").Set([0.0, 0.7, 0.5])
        prim.GetAttribute("primvars:opacity:y:values").Set([0.2, 0.4, 0.6])

    async def tearDown(self):
        """Release held input and popup edits before closing the stage."""
        await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
        await ui_test.human_delay()
        await ui_test.input.emulate_keyboard(KeyboardEventType.KEY_RELEASE, KeyboardInput.LEFT_CONTROL)
        await ui_test.human_delay()
        if self._editor is not None:
            self._editor.destroy()
            await ui_test.wait_n_updates(2)
            self._editor = None
        omni.kit.undo.clear_stack()
        await self._context.close_stage_async()

    async def _open_popup(self, mixed: bool = False, with_layout: bool = False) -> None:
        """Open both channels, optionally over targets with distinct initial payloads."""
        if mixed:
            other_path = "/World/OtherCurveHost"
            other = self._stage.DefinePrim(other_path, "Xform")
            source = self._stage.GetPrimAtPath(self._SOURCE_PATH)
            for curve_id in self._CURVE_IDS:
                for suffix in ALL_SUFFIXES:
                    attr = source.GetAttribute(f"primvars:{curve_id}:{suffix}")
                    other.CreateAttribute(attr.GetName(), attr.GetTypeName()).Set(attr.Get())
                other.GetAttribute(f"primvars:{curve_id}:values").Set([0.1, 0.3, 0.8])
            self._paths.insert(0, other_path)

        self._editor = CurveFieldEditor(
            target_paths=self._paths,
            curve_ids=list(self._CURVE_IDS),
            context_name="",
            property_name="Numeric Curves",
            pre_open_fn=lambda activate: activate(),
            editor_layout={"curves": [{"id": curve_id, "display_name": curve_id} for curve_id in self._CURVE_IDS]}
            if with_layout
            else None,
            per_curve_bounds={curve_id: CurveBounds() for curve_id in self._CURVE_IDS},
        )
        self._editor.open(preferred_size=(700, 400), anchor_rect=(100.0, 100.0, 200.0, 24.0))
        await ui_test.human_delay()
        self.assertTrue(self._editor.is_open)
        omni.kit.undo.clear_stack()

    async def _select_keys(self, index: int = 1, multiple: bool = True) -> None:
        """Select matching keys from both displayed curves using Shift-click."""
        host = self._editor
        keys = ui_test.find_all(f"{host.title}//Frame/**/Rectangle[*].name=='FCurveKey'")
        self.assertEqual(len(keys), 6)
        selections = [(index, 0)]
        if multiple:
            selections.append((index + 3, KEYBOARD_MODIFIER_FLAG_SHIFT))
        for key_index, modifiers in selections:
            # Settle the pointer before pressing a draggable Placer.
            await ui_test.input.emulate_mouse_move(keys[key_index].center)
            await ui_test.human_delay()
            await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN, modifiers=modifiers)
            await ui_test.human_delay()
            await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_UP, modifiers=modifiers)
            await ui_test.human_delay()
        if multiple:
            self.assertAlmostEqual(self._field("CurveEditorValueDrag").model.as_float, 0.0)

    def _field(self, identifier: str):
        """Find one numeric field in the active popup."""
        host = self._editor
        field = ui_test.find(f"{host.title}//Frame/**/FloatDrag[*].identifier=='{identifier}'")
        self.assertIsNotNone(field, f"Missing numeric field {identifier}")
        return field

    def _snapshot(self) -> dict:
        """Capture every curve array and tangent token for all target prims."""
        payloads = {}
        for prim_path in self._paths:
            prim = self._stage.GetPrimAtPath(prim_path)
            for curve_id in self._CURVE_IDS:
                payload = {}
                for suffix in ALL_SUFFIXES:
                    value = prim.GetAttribute(f"primvars:{curve_id}:{suffix}").Get()
                    payload[suffix] = value if isinstance(value, str) else tuple(value)
                payloads[prim_path, curve_id] = payload
        return payloads

    def _install_scene_shortcuts(self) -> list[str]:
        """Register real scene Undo/Redo actions and record which shortcuts reach them."""
        actions = get_action_registry()
        hotkeys = get_hotkey_registry()
        context = get_hotkey_context()
        calls = []
        self.addCleanup(actions.deregister_all_actions_for_extension, __name__)
        self.addCleanup(hotkeys.deregister_all_hotkeys_for_extension, __name__)
        for chord, name, callback in (
            ("CTRL+Z", "undo", omni.kit.undo.undo),
            ("CTRL+Y", "redo", omni.kit.undo.redo),
        ):

            def scene_action(name=name, callback=callback):
                """Record delivery before executing the actual scene history action."""
                calls.append(name)
                callback()

            actions.register_action(__name__, name, scene_action)
            self.assertIsNotNone(
                hotkeys.register_hotkey(__name__, chord, __name__, name, filter=HotkeyFilter(context=__name__))
            )
        context.push(__name__)
        self.addCleanup(context.pop)
        return calls

    async def _create_unrelated_undo(self, prim_path: str = "/World/Unrelated") -> None:
        """Create a separate prim through the normal undoable USD command."""
        success, _ = omni.kit.commands.execute(
            "CreatePrimWithDefaultXform",
            prim_type="Xform",
            prim_path=prim_path,
            select_new_prim=False,
            context_name="",
        )
        await ui_test.human_delay()
        self.assertTrue(success)
        self.assertTrue(self._stage.GetPrimAtPath(prim_path))

    def _render_objects(self, widget: FCurveWidget) -> dict:
        """Read manager, key-handle, and tangent-handle identities for displayed curves."""
        return {
            curve_id: (
                id(manager),
                tuple(id(handle) for handle in manager.key_handles),
                tuple((id(group.in_h), id(group.out_h)) for group in manager._groups),
            )
            for curve_id, manager in widget._managers.items()
        }

    def _assert_rendered_keys_match(self, widget: FCurveWidget) -> None:
        """Compare visible key handle centers with their final model coordinates."""
        for curve_id in self._CURVE_IDS:
            key = widget.curves[curve_id].keys[1]
            expected_x, expected_y = widget.viewport.model_to_pixel(key.time, key.value)
            screen_x, screen_y = widget._managers[curve_id].key_handles[1].screen_center
            self.assertAlmostEqual(screen_x, widget._stack.screen_position_x + expected_x, delta=1.0)
            self.assertAlmostEqual(screen_y, widget._stack.screen_position_y + expected_y, delta=1.0)

    async def _check_continuous_drag_undo(self, mixed: bool) -> None:
        """Move both channels continuously and verify one complete Undo/Redo operation."""
        await self._open_popup(mixed=mixed)
        await self._select_keys()
        before = self._snapshot()
        field = self._field("CurveEditorValueDrag")
        self.assertAlmostEqual(field.model.get_value_as_float(), 0.0)
        widget = self._editor._widget.fcurve_widget
        render_objects = self._render_objects(widget)
        application_count = 0
        storage_commits = []
        set_key_positions = widget.set_key_positions
        commit_payload = PropertyPrimvarCurveModel.commit_payload

        def record_update(*args, **kwargs):
            """Count real position applications while preserving rendered handles."""
            nonlocal application_count
            self.assertEqual(self._render_objects(widget), render_objects)
            application_count += 1
            result = set_key_positions(*args, **kwargs)
            self.assertEqual(self._render_objects(widget), render_objects)
            return result

        def record_commit(model, curve_id, payload):
            """Count curve payload commits while retaining their real USD writes."""
            storage_commits.append(curve_id)
            return commit_payload(model, curve_id, payload)

        with (
            patch.object(widget, "set_key_positions", record_update),
            patch.object(PropertyPrimvarCurveModel, "commit_payload", record_commit),
        ):
            async with self._held_pointer(field.center) as start:
                # Distinct movements must reach USD while the mouse is still held.
                previous = before
                for distance in range(-12, -36, -2):
                    await ui_test.input.emulate_mouse_move(ui_test.Vec2(start.x + distance, start.y))
                    await ui_test.human_delay()
                    current = self._snapshot()
                    self.assertEqual(list(omni.kit.undo.get_undo_stack()), [])
                    for curve_id in self._CURVE_IDS:
                        key = (self._SOURCE_PATH, curve_id)
                        self.assertNotEqual(current[key]["values"], previous[key]["values"])
                        self.assertAlmostEqual(
                            current[key]["values"][1] - before[key]["values"][1], field.model.as_float
                        )
                    self.assertEqual(self._render_objects(widget), render_objects)
                    self._assert_rendered_keys_match(widget)
                    previous = current

        self.assertGreaterEqual(application_count, 12)
        self.assertGreater(len(storage_commits), 0)
        self.assertLessEqual(len(storage_commits), len(self._CURVE_IDS) * application_count)

        # The deferred render update must move the visible handles to the final USD coordinates.
        self._assert_rendered_keys_match(widget)

        after = self._snapshot()
        self.assertEqual(sum(entry.level == 0 for entry in omni.kit.undo.get_undo_stack()), 1)
        self.assertAlmostEqual(field.model.get_value_as_float(), 0.0)
        self.assertTrue(omni.kit.undo.undo())
        await ui_test.human_delay()
        self.assertEqual(self._snapshot(), before)
        self.assertTrue(omni.kit.undo.redo())
        await ui_test.human_delay()
        self.assertEqual(self._snapshot(), after)

    async def test_numeric_drag_two_channels_commits_continuously_and_undoes_once(self):
        """One drag updates both channels before release and records one undo entry."""
        await self._check_continuous_drag_undo(mixed=False)

    async def test_numeric_held_ctrl_z_restores_mixed_targets_and_preserves_previous_undo(self):
        """Cancel a held drag without consuming earlier history or accepting late movement."""
        await self._open_popup(mixed=True)
        await self._select_keys()
        scene_calls = self._install_scene_shortcuts()
        await self._create_unrelated_undo()

        # A shortcut outside the numeric field proves the scene bindings are active.
        await ui_test.input.emulate_keyboard_press(KeyboardInput.Z, KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.human_delay()
        self.assertFalse(self._stage.GetPrimAtPath("/World/Unrelated"))
        await ui_test.input.emulate_keyboard_press(KeyboardInput.Y, KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.human_delay()
        self.assertTrue(self._stage.GetPrimAtPath("/World/Unrelated"))
        self.assertEqual(scene_calls, ["undo", "redo"])
        scene_calls.clear()
        history_before = list(omni.kit.undo.get_undo_stack())
        self.assertTrue(history_before)
        before = self._snapshot()
        async with self._held_pointer(self._field("CurveEditorValueDrag").center) as start:
            for distance in (-15, -25):
                await ui_test.input.emulate_mouse_move(ui_test.Vec2(start.x + distance, start.y))
                await ui_test.human_delay()
            after = self._snapshot()
            self.assertNotEqual(after, before)

            # Native Undo must restore every target before the pointer is released.
            await ui_test.input.emulate_keyboard_press(KeyboardInput.Z, KEYBOARD_MODIFIER_FLAG_CONTROL)
            await ui_test.human_delay()
            self.assertEqual(self._snapshot(), before)
            self.assertTrue(self._stage.GetPrimAtPath("/World/Unrelated"))
            self.assertEqual(list(omni.kit.undo.get_undo_stack()), history_before)
            self.assertEqual(len(omni.kit.undo.get_redo_stack()), 1)
            self.assertEqual(scene_calls, [])
            await ui_test.input.emulate_mouse_move(ui_test.Vec2(start.x - 40, start.y))
            await ui_test.human_delay()
            self.assertEqual(self._snapshot(), before)

        self.assertEqual(self._snapshot(), before)
        self._editor.close()
        await ui_test.human_delay()
        self.assertEqual(self._snapshot(), before)
        self.assertEqual(list(omni.kit.undo.get_undo_stack()), history_before)
        self.assertEqual(len(omni.kit.undo.get_redo_stack()), 1)
        await ui_test.input.emulate_keyboard_press(KeyboardInput.Y, KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.human_delay()
        self.assertEqual(scene_calls, ["redo"])
        self.assertEqual(self._snapshot(), after)

    async def _check_native_text_undo(self, type_while_held: bool) -> None:
        """Keep native text history local during text selection or the opening Ctrl-click."""
        await self._open_popup()
        await self._select_keys(multiple=False)
        scene_calls = self._install_scene_shortcuts()
        await self._create_unrelated_undo()
        history_before = list(omni.kit.undo.get_undo_stack())
        field = self._field("CurveEditorValueDrag")
        await field.click()
        await ui_test.human_delay()
        try:
            await ui_test.input.emulate_keyboard(
                KeyboardEventType.KEY_PRESS, KeyboardInput.LEFT_CONTROL, KEYBOARD_MODIFIER_FLAG_CONTROL
            )
            await ui_test.human_delay()
            await ui_test.input.emulate_mouse_move(field.center)
            await ui_test.human_delay()
            await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN)
            await ui_test.human_delay()
            await ui_test.input.emulate_keyboard(KeyboardEventType.KEY_RELEASE, KeyboardInput.LEFT_CONTROL)
            await ui_test.human_delay()
            if not type_while_held:
                await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
                await ui_test.human_delay()
            await ui_test.input.emulate_char_press("0.42")
            await ui_test.human_delay()
            self.assertAlmostEqual(self._snapshot()[self._SOURCE_PATH, "opacity:x"]["values"][1], 0.42)
            await ui_test.input.emulate_keyboard_press(KeyboardInput.Z, KEYBOARD_MODIFIER_FLAG_CONTROL)
            await ui_test.human_delay()
            self.assertAlmostEqual(self._snapshot()[self._SOURCE_PATH, "opacity:x"]["values"][1], 0.4)
            await ui_test.input.emulate_keyboard_press(KeyboardInput.Y, KEYBOARD_MODIFIER_FLAG_CONTROL)
            await ui_test.human_delay()
            self.assertAlmostEqual(self._snapshot()[self._SOURCE_PATH, "opacity:x"]["values"][1], 0.42)

            if not type_while_held:
                # Selecting text with the mouse held must not reclassify it as a scrub.
                await ui_test.input.emulate_mouse_move(field.center)
                await ui_test.human_delay()
                await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN)
                await ui_test.human_delay()
                await ui_test.input.emulate_mouse_move(ui_test.Vec2(field.center.x - 8, field.center.y))
                await ui_test.human_delay()
                await ui_test.input.emulate_keyboard_press(KeyboardInput.Z, KEYBOARD_MODIFIER_FLAG_CONTROL)
                await ui_test.human_delay()
                self.assertAlmostEqual(self._snapshot()[self._SOURCE_PATH, "opacity:x"]["values"][1], 0.4)
                await ui_test.input.emulate_keyboard_press(KeyboardInput.Y, KEYBOARD_MODIFIER_FLAG_CONTROL)
                await ui_test.human_delay()
                self.assertAlmostEqual(self._snapshot()[self._SOURCE_PATH, "opacity:x"]["values"][1], 0.42)
            self.assertEqual(scene_calls, [])
            self.assertEqual(list(omni.kit.undo.get_undo_stack()), history_before)
            self.assertTrue(self._stage.GetPrimAtPath("/World/Unrelated"))
        finally:
            await ui_test.input.emulate_keyboard(KeyboardEventType.KEY_RELEASE, KeyboardInput.LEFT_CONTROL)
            await ui_test.human_delay()
            await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
            await ui_test.human_delay()
        await ui_test.input.emulate_keyboard_press(KeyboardInput.ENTER)
        await ui_test.human_delay()
        self.assertAlmostEqual(self._snapshot()[self._SOURCE_PATH, "opacity:x"]["values"][1], 0.42)
        self.assertEqual(sum(entry.level == 0 for entry in omni.kit.undo.get_undo_stack()), 2)

    async def test_numeric_text_undo_with_held_selection_preserves_scene_history(self):
        """Native text Undo/Redo remains local while the mouse selects text."""
        await self._check_native_text_undo(type_while_held=False)

    async def test_numeric_text_undo_before_ctrl_click_release_preserves_scene_history(self):
        """Typing before releasing the opening Ctrl-click still uses native text history."""
        await self._check_native_text_undo(type_while_held=True)

    def _set_flat_tangents(self) -> None:
        """Author canonical tangents for exact-return gestures."""
        # Flat tangents have an exact canonical payload, independent of smooth-handle roundoff.
        source = self._stage.GetPrimAtPath(self._SOURCE_PATH)
        for curve_id in self._CURVE_IDS:
            for suffix, values in (
                ("inTangentTypes", ["flat"] * 3),
                ("outTangentTypes", ["flat"] * 3),
                ("inTangentTimes", [0.0, -0.25, -0.25]),
                ("outTangentTimes", [0.25, 0.25, 0.0]),
                ("inTangentValues", [0.0] * 3),
                ("outTangentValues", [0.0] * 3),
            ):
                source.GetAttribute(f"primvars:{curve_id}:{suffix}").Set(values)

    async def _check_return_to_baseline(self, mixed: bool) -> None:
        """Finish a zero-offset scrub without losing unrelated history."""
        self._set_flat_tangents()
        await self._open_popup(mixed=mixed)
        await self._select_keys()
        field = self._field("CurveEditorValueDrag")
        await self._create_unrelated_undo()
        await self._create_unrelated_undo(self._PENDING_REDO_PATH)
        self.assertTrue(omni.kit.undo.undo())
        await ui_test.human_delay()
        history_before = list(omni.kit.undo.get_undo_stack())
        redo_before = list(omni.kit.undo.get_redo_stack())
        self.assertTrue(history_before and redo_before)
        before = self._snapshot()
        for cancel in (True,) if mixed else (False, True):
            with self.subTest(cancel=cancel):
                # Refocus through the keys so consecutive field presses cannot enter double-click text editing.
                await self._select_keys()
                async with self._held_pointer(field.center) as start:
                    await ui_test.input.emulate_mouse_move(ui_test.Vec2(start.x - 25, start.y))
                    await ui_test.human_delay()
                    self.assertNotEqual(self._snapshot(), before)
                    await ui_test.input.emulate_mouse_move(start)
                    await ui_test.human_delay()
                    returned = self._snapshot()
                    for curve_id in self._CURVE_IDS:
                        self.assertEqual(returned[self._SOURCE_PATH, curve_id], before[self._SOURCE_PATH, curve_id])
                    self.assertEqual(returned == before, not mixed)
                    if cancel:
                        # Returning the source may still flatten another target; Ctrl+Z must restore it.
                        await ui_test.input.emulate_keyboard_press(KeyboardInput.Z, KEYBOARD_MODIFIER_FLAG_CONTROL)
                        await ui_test.human_delay()
                        self.assertEqual(self._snapshot(), before)
                self.assertEqual(self._snapshot(), before)
                self.assertTrue(self._stage.GetPrimAtPath("/World/Unrelated"))
                self.assertEqual(list(omni.kit.undo.get_undo_stack()), history_before)
                if not mixed:
                    self.assertEqual(list(omni.kit.undo.get_redo_stack()), redo_before)
        self.assertTrue(omni.kit.undo.redo())
        await ui_test.human_delay()
        if mixed:
            self.assertEqual(self._snapshot(), returned)
        else:
            self.assertTrue(self._stage.GetPrimAtPath(self._PENDING_REDO_PATH))

    async def test_numeric_uniform_return_to_baseline_preserves_previous_undo(self):
        """A scrub returning to its complete baseline cannot undo the previous command."""
        await self._check_return_to_baseline(mixed=False)

    async def test_numeric_mixed_return_to_source_baseline_undoes_target_flattening(self):
        """A zero source offset still undoes changed payloads on the other target."""
        await self._check_return_to_baseline(mixed=True)

    async def test_numeric_programmatic_undo_during_drag_keeps_finalization_usable(self):
        """Public Undo during a held drag cannot orphan the gesture's history group."""
        await self._open_popup()
        await self._select_keys()
        await self._create_unrelated_undo()
        before = self._snapshot()
        async with self._held_pointer(self._field("CurveEditorValueDrag").center) as start:
            await ui_test.input.emulate_mouse_move(ui_test.Vec2(start.x - 25, start.y))
            await ui_test.human_delay()
            self.assertNotEqual(self._snapshot(), before)
            self.assertTrue(omni.kit.undo.undo())
            await ui_test.human_delay()

        # Finalization must leave an ordinary top-level operation with working replay.
        after = self._snapshot()
        self.assertEqual(sum(entry.level == 0 for entry in omni.kit.undo.get_undo_stack()), 1)
        self.assertTrue(omni.kit.undo.undo())
        await ui_test.human_delay()
        self.assertEqual(self._snapshot(), before)
        self.assertTrue(omni.kit.undo.redo())
        await ui_test.human_delay()
        self.assertEqual(self._snapshot(), after)

    async def test_numeric_value_edit_near_minimum_key_spacing_preserves_times_and_undoes_once(self):
        """Edit a value between tightly spaced keys without moving times or losing undo payloads."""
        # Preserve authored double precision where both neighboring gaps are just below the spacing limit.
        times = (0.009, 0.01 - 0.5e-12, 0.011 - 1e-12)
        source = self._stage.GetPrimAtPath(self._SOURCE_PATH)
        source.GetAttribute("primvars:opacity:x:times").Set(list(times))
        await self._open_popup()
        widget = self._editor._widget.fcurve_widget
        self.assertEqual(tuple(key.time for key in widget.curves["opacity:x"].keys), times)
        await self._select_keys(multiple=False)
        before = self._snapshot()

        await self._field("CurveEditorValueDrag").input("0.6")
        await ui_test.human_delay()

        after = self._snapshot()
        self.assertAlmostEqual(after[self._SOURCE_PATH, "opacity:x"]["values"][1], 0.6)
        self.assertEqual(after[self._SOURCE_PATH, "opacity:x"]["times"], times)
        self.assertEqual(after[self._SOURCE_PATH, "opacity:y"], before[self._SOURCE_PATH, "opacity:y"])
        self.assertEqual(sum(entry.level == 0 for entry in omni.kit.undo.get_undo_stack()), 1)

        # Undo and Redo must restore complete stored curves, including tangent arrays and modes.
        self.assertTrue(omni.kit.undo.undo())
        await ui_test.human_delay()
        self.assertEqual(self._snapshot(), before)
        self.assertTrue(omni.kit.undo.redo())
        await ui_test.human_delay()
        self.assertEqual(self._snapshot(), after)

    async def test_numeric_single_key_edits_absolute_coordinates_and_tracks_viewport_drag(self):
        """Absolute fields edit one selected key and follow subsequent viewport movement."""
        await self._open_popup()
        await self._select_keys(multiple=False)
        before = self._snapshot()
        time_field = self._field("CurveEditorTimeDrag")
        value_field = self._field("CurveEditorValueDrag")
        self.assertAlmostEqual(time_field.model.as_float, 0.5)
        self.assertAlmostEqual(value_field.model.as_float, 0.7)

        await time_field.input("0.6")
        await ui_test.human_delay()
        await value_field.input("0.6")
        await ui_test.human_delay()
        edited = self._snapshot()
        self.assertAlmostEqual(edited[self._SOURCE_PATH, "opacity:x"]["times"][1], 0.6)
        self.assertAlmostEqual(edited[self._SOURCE_PATH, "opacity:x"]["values"][1], 0.6)
        self.assertEqual(edited[self._SOURCE_PATH, "opacity:y"], before[self._SOURCE_PATH, "opacity:y"])

        # Move the same key in the viewport and read both fields before releasing.
        host = self._editor
        keys = ui_test.find_all(f"{host.title}//Frame/**/Rectangle[*].name=='FCurveKey'")
        async with self._held_pointer(keys[1].center) as start:
            await ui_test.input.emulate_mouse_move(ui_test.Vec2(start.x + 16.0, start.y + 16.0))
            await ui_test.human_delay()
            moved = self._snapshot()[self._SOURCE_PATH, "opacity:x"]
            self.assertNotAlmostEqual(moved["times"][1], 0.6)
            self.assertNotAlmostEqual(moved["values"][1], 0.6)
            self.assertAlmostEqual(time_field.model.as_float, moved["times"][1])
            self.assertAlmostEqual(value_field.model.as_float, moved["values"][1])

    async def test_viewport_unselected_key_drag_keeps_pressed_key_selected(self):
        """Select on press and keep that key selected when released over another curve."""
        await self._open_popup()
        await self._select_keys(index=0, multiple=False)
        host = self._editor
        widget = host._widget.fcurve_widget
        before = self._snapshot()
        keys = ui_test.find_all(f"{host.title}//Frame/**/Rectangle[*].name=='FCurveKey'")
        expected = [KeyReference("opacity:x", 1)]
        async with self._held_pointer(keys[1].center) as start:
            self.assertEqual(widget.selection.keys, expected)
            for amount in (0.5, 1.0):
                await ui_test.input.emulate_mouse_move(start + (keys[4].center - start) * amount)
                await ui_test.human_delay()
        self.assertEqual(widget.selection.keys, expected)
        highlighted = [
            KeyReference(curve_id, index)
            for curve_id, manager in widget._managers.items()
            for index, handle in enumerate(manager.key_handles)
            if handle.selected
        ]
        self.assertEqual(highlighted, expected)
        after = self._snapshot()
        self.assertNotEqual(
            after[self._SOURCE_PATH, "opacity:x"]["values"], before[self._SOURCE_PATH, "opacity:x"]["values"]
        )
        self.assertEqual(after[self._SOURCE_PATH, "opacity:y"], before[self._SOURCE_PATH, "opacity:y"])
        self.assertAlmostEqual(
            self._field("CurveEditorValueDrag").model.as_float, after[self._SOURCE_PATH, "opacity:x"]["values"][1]
        )

    async def test_viewport_group_drag_undo_redo_and_blank_deselection(self):
        """Move selected curves together, restore mixed targets, and deselect without consuming Redo."""
        await self._open_popup(mixed=True)
        await self._select_keys()
        host = self._editor
        widget = host._widget.fcurve_widget
        selected = [KeyReference(curve_id, 1) for curve_id in self._CURVE_IDS]
        before = self._snapshot()
        keys = ui_test.find_all(f"{host.title}//Frame/**/Rectangle[*].name=='FCurveKey'")
        async with self._held_pointer(keys[1].center) as start:
            self.assertCountEqual(widget.selection.keys, selected)
            self.assertEqual(self._snapshot(), before)
            for distance in (12, 24):
                await ui_test.input.emulate_mouse_move(start + ui_test.Vec2(distance, -distance))
                await ui_test.human_delay()
        after = self._snapshot()
        self.assertCountEqual(widget.selection.keys, selected)
        for curve_id, manager in widget._managers.items():
            self.assertEqual([handle.selected for handle in manager.key_handles], [False, True, False])
            self.assertEqual(after[self._paths[0], curve_id], after[self._SOURCE_PATH, curve_id])
        for suffix in ("times", "values"):
            delta = after[self._SOURCE_PATH, "opacity:x"][suffix][1] - before[self._SOURCE_PATH, "opacity:x"][suffix][1]
            self.assertGreater(delta, 0.0)
            for curve_id in self._CURVE_IDS:
                self.assertAlmostEqual(
                    after[self._SOURCE_PATH, curve_id][suffix][1],
                    before[self._SOURCE_PATH, curve_id][suffix][1] + delta,
                )
                for index in (0, 2):
                    self.assertEqual(
                        after[self._SOURCE_PATH, curve_id][suffix][index],
                        before[self._SOURCE_PATH, curve_id][suffix][index],
                    )
        self.assertEqual(sum(entry.level == 0 for entry in omni.kit.undo.get_undo_stack()), 1)
        self.assertTrue(omni.kit.undo.undo())
        await ui_test.human_delay()
        self.assertEqual(self._snapshot(), before)

        # A real blank click clears the restored selection without modifying data or the pending group Redo.
        await self._select_keys()
        history = (list(omni.kit.undo.get_undo_stack()), list(omni.kit.undo.get_redo_stack()))
        self.assertTrue(history[1])
        canvas = ui_test.find(f"{host.title}//Frame/**/Frame[*].identifier=='CurveEditorCanvas'").widget
        blank = ui_test.Vec2(
            canvas.screen_position_x + canvas.computed_width * 0.75,
            canvas.screen_position_y + canvas.computed_height * 0.90,
        )
        async with self._held_pointer(blank):
            pass
        self.assertTrue(widget.selection.is_empty)
        self.assertFalse(
            any(handle.selected for manager in widget._managers.values() for handle in manager.key_handles)
        )
        for identifier in ("CurveEditorTimeDrag", "CurveEditorValueDrag"):
            self.assertFalse(self._field(identifier).widget.enabled)
        for identifier in ("CurveEditorBtnDeleteKey", "CurveEditorBtnLink"):
            self.assertFalse(
                ui_test.find(f"{host.title}//Frame/**/Button[*].identifier=='{identifier}'").widget.enabled
            )
        self.assertEqual(self._snapshot(), before)
        self.assertEqual((list(omni.kit.undo.get_undo_stack()), list(omni.kit.undo.get_redo_stack())), history)
        self.assertTrue(omni.kit.undo.redo())
        await ui_test.human_delay()
        self.assertEqual(self._snapshot(), after)

    async def _check_viewport_return_to_baseline(self, mixed: bool) -> None:
        """Distinguish a complete no-op from flattening targets after a native drag returns to its origin."""
        self._set_flat_tangents()
        source = self._stage.GetPrimAtPath(self._SOURCE_PATH)
        source.GetAttribute("primvars:opacity:x:values").Set([0.0, 0.5, 0.25])
        source.GetAttribute("primvars:opacity:y:values").Set([0.25, 0.75, 0.5])
        await self._open_popup(mixed=mixed)
        # Binary fractions and an unpadded viewport make the pointer round trip exact in model space.
        self._editor._widget.set_time_range(0.0, 1.0)
        self._editor._widget.set_value_range(0.0, 1.0)
        await ui_test.human_delay()
        await self._create_unrelated_undo()
        await self._create_unrelated_undo(self._PENDING_REDO_PATH)
        self.assertTrue(omni.kit.undo.undo())
        await ui_test.human_delay()
        await self._select_keys()
        history = (list(omni.kit.undo.get_undo_stack()), list(omni.kit.undo.get_redo_stack()))
        self.assertTrue(all(history))
        before = self._snapshot()
        host = self._editor
        widget = host._widget.fcurve_widget
        selection = widget.selection.keys
        keys = ui_test.find_all(f"{host.title}//Frame/**/Rectangle[*].name=='FCurveKey'")
        async with self._held_pointer(keys[1].center) as start:
            await ui_test.input.emulate_mouse_move(start + ui_test.Vec2(0, 24))
            await ui_test.human_delay()
            self.assertNotEqual(self._snapshot(), before)
            await ui_test.input.emulate_mouse_move(start)
            await ui_test.human_delay()
        returned = self._snapshot()
        for curve_id in self._CURVE_IDS:
            self.assertEqual(returned[self._SOURCE_PATH, curve_id], before[self._SOURCE_PATH, curve_id])
        self.assertEqual(returned == before, not mixed)
        self.assertCountEqual(widget.selection.keys, selection)
        if mixed:
            self.assertEqual(sum(entry.level == 0 for entry in omni.kit.undo.get_undo_stack()), 2)
            self.assertTrue(omni.kit.undo.undo())
            await ui_test.human_delay()
            self.assertEqual(self._snapshot(), before)
            self.assertEqual(list(omni.kit.undo.get_undo_stack()), history[0])
            self.assertTrue(omni.kit.undo.redo())
            await ui_test.human_delay()
            self.assertEqual(self._snapshot(), returned)
        else:
            self.assertEqual((list(omni.kit.undo.get_undo_stack()), list(omni.kit.undo.get_redo_stack())), history)
            self.assertTrue(omni.kit.undo.redo())
            await ui_test.human_delay()
            self.assertTrue(self._stage.GetPrimAtPath(self._PENDING_REDO_PATH))
            self.assertEqual(self._snapshot(), before)

    async def test_viewport_group_return_to_baseline_preserves_undo_and_redo(self):
        """A group drag released at its complete baseline preserves both history stacks."""
        await self._check_viewport_return_to_baseline(mixed=False)

    async def test_viewport_group_return_to_source_baseline_undoes_mixed_target_flattening(self):
        """One Undo restores mixed targets even when the displayed keys returned to their baseline."""
        await self._check_viewport_return_to_baseline(mixed=True)

    async def test_numeric_channel_filter_excludes_hidden_selection_from_mode_and_edit(self):
        """Hiding one selected channel switches fields to absolute editing of the remaining key."""
        await self._open_popup(with_layout=True)
        await self._select_keys()
        before = self._snapshot()
        host = self._editor
        channel = ui_test.find(f"{host.title}//Frame/**/Label[*].identifier=='CurveTreeChannel::opacity:x'")
        self.assertIsNotNone(channel)
        await channel.click()
        await ui_test.human_delay()
        for label in ("Time", "Value"):
            self.assertIsNotNone(ui_test.find(f"{host.title}//Frame/**/Label[*].text=='{label}'"))
        time_field = self._field("CurveEditorTimeDrag")
        value_field = self._field("CurveEditorValueDrag")
        self.assertAlmostEqual(time_field.model.as_float, 0.5)
        self.assertAlmostEqual(value_field.model.as_float, 0.7)

        await value_field.input("0.2")
        await ui_test.human_delay()

        after = self._snapshot()
        self.assertAlmostEqual(after[self._SOURCE_PATH, "opacity:x"]["values"][1], 0.2)
        self.assertEqual(after[self._SOURCE_PATH, "opacity:y"], before[self._SOURCE_PATH, "opacity:y"])
        self.assertAlmostEqual(time_field.model.as_float, 0.5)
        self.assertAlmostEqual(value_field.model.as_float, 0.2)

    async def test_numeric_drag_mixed_targets_one_undo_restores_distinct_payloads(self):
        """Undo includes initial mixed-target flattening and restores all original tangents."""
        await self._check_continuous_drag_undo(mixed=True)

    async def test_numeric_offsets_typed_enter_and_focus_loss_reset_between_edits(self):
        """Each typed offset starts from the current values and resets after editing."""
        await self._open_popup()
        await self._select_keys()
        field = self._field("CurveEditorValueDrag")
        await field.input("0.1")
        await ui_test.human_delay()
        first = self._snapshot()
        self.assertAlmostEqual(first[self._SOURCE_PATH, "opacity:x"]["values"][1], 0.8)
        self.assertAlmostEqual(first[self._SOURCE_PATH, "opacity:y"]["values"][1], 0.5)
        self.assertAlmostEqual(field.model.get_value_as_float(), 0.0)

        # Tab ends the second edit through focus loss, using the first edit's result.
        await field.click()
        await ui_test.human_delay()
        await ui_test.input.emulate_keyboard(
            KeyboardEventType.KEY_PRESS, KeyboardInput.LEFT_CONTROL, KEYBOARD_MODIFIER_FLAG_CONTROL
        )
        try:
            await field.click()
        finally:
            await ui_test.input.emulate_keyboard(KeyboardEventType.KEY_RELEASE, KeyboardInput.LEFT_CONTROL)
        await ui_test.human_delay()
        # Re-entry can already be in native text mode after the preliminary click.
        await ui_test.input.emulate_keyboard_press(KeyboardInput.A, KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.input.emulate_char_press("0.1")
        await ui_test.input.emulate_keyboard_press(KeyboardInput.TAB)
        await ui_test.human_delay()
        second = self._snapshot()
        self.assertAlmostEqual(second[self._SOURCE_PATH, "opacity:x"]["values"][1], 0.9)
        self.assertAlmostEqual(second[self._SOURCE_PATH, "opacity:y"]["values"][1], 0.6)
        self.assertAlmostEqual(field.model.get_value_as_float(), 0.0)
        self.assertEqual(sum(entry.level == 0 for entry in omni.kit.undo.get_undo_stack()), 2)

    async def test_numeric_zero_offset_after_undo_preserves_both_history_stacks(self):
        """Clicking and accepting zero offset cannot erase an existing Redo."""
        await self._open_popup()
        await self._select_keys()
        field = self._field("CurveEditorValueDrag")
        await field.input("0.1")
        await ui_test.human_delay()
        self.assertTrue(omni.kit.undo.undo())
        await ui_test.human_delay()
        await self._select_keys()
        before = self._snapshot()
        undo_before = list(omni.kit.undo.get_undo_stack())
        redo_before = list(omni.kit.undo.get_redo_stack())
        self.assertTrue(redo_before)

        await field.click()
        await ui_test.human_delay()
        await field.input("0")
        await ui_test.human_delay()

        # Both final keys already sit on the hard upper time limit.
        await self._select_keys(index=2)
        time_field = self._field("CurveEditorTimeDrag")
        start = time_field.center
        await time_field.drag_and_drop(ui_test.Vec2(start.x + 30.0, start.y))
        await ui_test.human_delay()

        self.assertEqual(self._snapshot(), before)
        self.assertEqual(list(omni.kit.undo.get_undo_stack()), undo_before)
        self.assertEqual(list(omni.kit.undo.get_redo_stack()), redo_before)

    async def test_numeric_drag_popup_close_finalizes_each_curve_once(self):
        """Closing during an active numeric drag finishes its storage edits once."""
        await self._open_popup()
        await self._select_keys()
        before = self._snapshot()
        ended = []
        original_end_edit = PropertyPrimvarCurveModel.end_edit

        def record_end_edit(model, curve_id):
            """Record finalization while retaining the real USD edit lifecycle."""
            ended.append(curve_id)
            original_end_edit(model, curve_id)

        with patch.object(PropertyPrimvarCurveModel, "end_edit", record_end_edit):
            async with self._held_pointer(self._field("CurveEditorValueDrag").center) as start:
                await ui_test.input.emulate_mouse_move(ui_test.Vec2(start.x - 12.0, start.y))
                await ui_test.human_delay()
                self.assertNotEqual(self._snapshot(), before)

                # Native closure defers detachment, then finishes the editor before its model.
                await ui_test.input.emulate_keyboard_press(KeyboardInput.ESCAPE)
                await ui_test.human_delay()
                self.assertFalse(self._editor.is_open)

        self.assertCountEqual(ended, self._CURVE_IDS)
        self.assertEqual(sum(entry.level == 0 for entry in omni.kit.undo.get_undo_stack()), 1)
        self.assertTrue(omni.kit.undo.undo())
        self.assertEqual(self._snapshot(), before)
