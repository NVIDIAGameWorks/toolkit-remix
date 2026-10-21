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

from contextlib import ExitStack
from unittest.mock import patch

import omni.kit.test
import omni.kit.ui_test as ui_test
import omni.kit.undo
import omni.usd
from carb.input import (
    KEYBOARD_MODIFIER_FLAG_ALT,
    KEYBOARD_MODIFIER_FLAG_CONTROL,
    KEYBOARD_MODIFIER_FLAG_SHIFT,
    KEYBOARD_MODIFIER_FLAG_SUPER,
    KeyboardEventType,
    KeyboardInput,
    MouseEventType,
)
from omni import ui
from omni.flux.curve_editor.widget.payload import curve_to_payload
from omni.flux.fcurve.widget import FCurve, FCurveKey, InfinityType, TangentType
from omni.flux.property_widget_builder.delegates import field_popup_window
from omni.kit.actions.core import get_action_registry
from omni.kit.hotkeys.core import HotkeyFilter, get_hotkey_context, get_hotkey_registry
from omni.kit.ui_test import Vec2
from omni.kit.ui_test.input import emulate_keyboard, emulate_mouse
from pxr import Gf, Sdf, Vt

from ... import USDAttributeItem, USDDelegate, USDLogicalGroupOutletItem, USDModel, USDPropertyWidget
from ...curve_primvar import PropertyPrimvarCurveModel
from ...field_builders.curve import CurveFieldEditor
from ...logical_group_constants import CURVE_LOGICAL_GROUP_DEFINITION, CURVE_LOGICAL_SUFFIXES

_NAMED_CONTEXT_NAME = f"{__name__}.named_context"
_EDITOR_IDENTITY = "###PropertyPanelFloatingEditor_"
_KEYBOARD_FOCUS_WINDOW_WIDTH = 160.0
_KEYBOARD_FOCUS_WINDOW_HEIGHT = 80.0
_TEXT_CAPTURE_ROW_HEIGHT = 24.0


def _find_editor_window(title: str):
    """Find the visible native window for one floating editor."""
    title = f"{title}{_EDITOR_IDENTITY}"
    return next(
        (window for window in ui.Workspace.get_windows() if window.title.startswith(title) and window.visible), None
    )


def _attribute_item(context_name: str, prim_path: str, attribute_name: str, display_name: str) -> USDAttributeItem:
    """Create one real USD property item."""
    return USDAttributeItem(
        context_name,
        [Sdf.Path(f"{prim_path}.{attribute_name}")],
        display_attr_names=[display_name],
    )


def _curve_items(context_name: str, prim_path: str, curve_id: str, display_name: str) -> list[USDAttributeItem]:
    """Create the property items for one complete Curve payload."""
    return [
        _attribute_item(context_name, prim_path, f"primvars:{curve_id}:{suffix}", display_name)
        for suffix in CURVE_LOGICAL_SUFFIXES
    ]


def _seed_curve(prim, curve_id: str, curve: FCurve | None = None) -> None:
    """Author a Curve payload on a prim."""
    curve = curve or FCurve(id=curve_id, keys=[FCurveKey(time=0.0, value=0.0), FCurveKey(time=1.0, value=1.0)])
    for suffix, value in curve_to_payload(curve).items():
        if suffix in {
            "times",
            "values",
            "inTangentTimes",
            "inTangentValues",
            "outTangentTimes",
            "outTangentValues",
        }:
            value_type = Sdf.ValueTypeNames.DoubleArray
        elif suffix in {"inTangentTypes", "outTangentTypes"}:
            value_type = Sdf.ValueTypeNames.TokenArray
        elif suffix == "tangentBrokens":
            value_type = Sdf.ValueTypeNames.BoolArray
        else:
            value_type = Sdf.ValueTypeNames.Token
        prim.CreateAttribute(f"primvars:{curve_id}:{suffix}", value_type).Set(value)


def _build_property_panel(context_name: str, title: str, items):
    """Construct one real USD model, delegate, and property widget panel."""
    model = USDModel(context_name=context_name)
    delegate = USDDelegate()
    window = ui.Window(title, width=620, height=360)
    with window.frame:
        widget = USDPropertyWidget(context_name=context_name, model=model, delegate=delegate)
    model.set_items(items)
    return window, model, delegate, widget


def _snapshot_curve_payload(prim, curve_id: str) -> dict:
    """Read every suffix in one authored Curve payload."""
    return {
        suffix: prim.GetAttribute(f"primvars:{curve_id}:{suffix}").Get()
        for suffix in CURVE_LOGICAL_GROUP_DEFINITION.suffixes
    }


def _detailed_curve(curve_id: str, middle_time: float | None = None, tangent_seed: float = 0.0) -> FCurve:
    """Build a Curve with distinct tangent and infinity values for payload checks."""
    keys = [
        FCurveKey(
            time=0.0,
            value=0.0 + tangent_seed,
            in_tangent_type=TangentType.FLAT,
            out_tangent_type=TangentType.CUSTOM,
            out_tangent_x=0.12 + tangent_seed,
            out_tangent_y=0.04 + tangent_seed,
            tangent_broken=True,
        )
    ]
    if middle_time is not None:
        keys.append(
            FCurveKey(
                time=middle_time,
                value=0.5 + tangent_seed,
                in_tangent_type=TangentType.CUSTOM,
                out_tangent_type=TangentType.CUSTOM,
                in_tangent_x=-0.15 - tangent_seed,
                in_tangent_y=-0.05 - tangent_seed,
                out_tangent_x=0.15 + tangent_seed,
                out_tangent_y=0.05 + tangent_seed,
                tangent_broken=True,
            )
        )
    keys.append(
        FCurveKey(
            time=1.0,
            value=1.0 + tangent_seed,
            in_tangent_type=TangentType.CUSTOM,
            out_tangent_type=TangentType.LINEAR,
            in_tangent_x=-0.12 - tangent_seed,
            in_tangent_y=-0.04 - tangent_seed,
            tangent_broken=True,
        )
    )
    return FCurve(
        id=curve_id,
        keys=keys,
        pre_infinity=InfinityType.LINEAR,
        post_infinity=InfinityType.CONSTANT,
    )


class TestCurvePrimvarModelMixedFirstEdit(omni.kit.test.AsyncTestCase):
    """Exercise mixed Curve edits through the public USD model API."""

    async def setUp(self):
        """Create two authored Curves with distinct payloads."""
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()
        self.prim_path = "/CurveMixedPrimA"
        self.other_prim_path = "/CurveMixedPrimB"
        self.curve_id = "test:x"
        self.model = None
        omni.kit.undo.clear_stack()
        omni.kit.undo.clear_history()

        self.stage.DefinePrim(self.prim_path, "Xform")
        self.stage.DefinePrim(self.other_prim_path, "Xform")
        _seed_curve(self.stage.GetPrimAtPath(self.prim_path), self.curve_id, _detailed_curve(self.curve_id))
        _seed_curve(
            self.stage.GetPrimAtPath(self.other_prim_path),
            self.curve_id,
            _detailed_curve(self.curve_id, middle_time=0.25, tangent_seed=0.1),
        )

    async def tearDown(self):
        """Release the model, undo history, and stage."""
        if self.model:
            self.model.destroy()
        omni.kit.undo.clear_stack()
        omni.kit.undo.clear_history()
        if self.context:
            await self.context.close_stage_async()
        self.context = None
        self.stage = None
        self.model = None

    def _build_model(self) -> None:
        """Create a model for both selected Curve prims."""
        self.model = PropertyPrimvarCurveModel(
            prim_paths=[self.prim_path, self.other_prim_path],
            curve_ids=[self.curve_id],
            usd_context_name="",
        )

    def _read_curve_payload(self, prim_path: str) -> dict:
        """Read one target's complete Curve payload."""
        return _snapshot_curve_payload(self.stage.GetPrimAtPath(prim_path), self.curve_id)

    async def test_mixed_discrete_edit_flattens_and_edits_targets(self):
        """A discrete edit writes exact data and one undo command across both targets."""
        # Arrange
        self._build_model()
        first_before = self._read_curve_payload(self.prim_path)
        second_before = self._read_curve_payload(self.other_prim_path)
        final_curve = _detailed_curve(self.curve_id, middle_time=0.5, tangent_seed=0.2)
        undo_before = tuple(omni.kit.undo.get_undo_stack())

        # Act
        self.model.commit_payload(self.curve_id, curve_to_payload(final_curve))

        # Assert
        final_payload = self._read_curve_payload(self.prim_path)
        for suffix, expected in curve_to_payload(final_curve).items():
            actual = final_payload[suffix]
            self.assertEqual(list(actual) if isinstance(expected, list) else actual, expected)
        self.assertEqual(self._read_curve_payload(self.other_prim_path), final_payload)
        self.assertEqual(len(omni.kit.undo.get_undo_stack()), len(undo_before) + 1)
        omni.kit.undo.undo()
        self.assertEqual(self._read_curve_payload(self.prim_path), first_before)
        self.assertEqual(self._read_curve_payload(self.other_prim_path), second_before)
        self.assertNotEqual(first_before, second_before)
        omni.kit.undo.redo()
        self.assertEqual(self._read_curve_payload(self.prim_path), final_payload)
        self.assertEqual(self._read_curve_payload(self.other_prim_path), final_payload)

    async def test_mixed_drag_flattens_on_write_and_undo_restores_each_target(self):
        """Commit a mixed Curve gesture once and restore each target with public history."""
        self._build_model()
        first_before = self._read_curve_payload(self.prim_path)
        second_before = self._read_curve_payload(self.other_prim_path)
        final_curve = _detailed_curve(self.curve_id, middle_time=0.5, tangent_seed=0.2)
        history_before = dict(omni.kit.undo.get_history())
        undo_before = tuple(omni.kit.undo.get_undo_stack())
        notifications = []
        subscription = self.model.subscribe(notifications.append)
        try:
            # Starting a gesture must not flatten untouched targets or add history.
            self.model.begin_edit(self.curve_id)
            self.assertEqual(notifications, [])
            self.assertEqual(self._read_curve_payload(self.prim_path), first_before)
            self.assertEqual(self._read_curve_payload(self.other_prim_path), second_before)
            self.assertEqual(omni.kit.undo.get_history(), history_before)
            self.assertEqual(tuple(omni.kit.undo.get_undo_stack()), undo_before)

            self.model.commit_payload(self.curve_id, curve_to_payload(final_curve))
            self.assertEqual(notifications, [])
            final_payload = self._read_curve_payload(self.prim_path)
            self.assertEqual(final_payload, self._read_curve_payload(self.other_prim_path))
            for suffix, expected in curve_to_payload(final_curve).items():
                actual = final_payload[suffix]
                self.assertEqual(list(actual) if isinstance(expected, list) else actual, expected)
            self.assertEqual(omni.kit.undo.get_history(), history_before)
            self.assertEqual(tuple(omni.kit.undo.get_undo_stack()), undo_before)
            self.model.end_edit(self.curve_id)
            self.assertEqual(notifications, [])
            self.assertEqual(len(omni.kit.undo.get_undo_stack()), len(undo_before) + 1)

            omni.kit.undo.undo()
            self.assertTrue(notifications)
            self.assertEqual(set(notifications), {self.curve_id})
            self.assertEqual(self._read_curve_payload(self.prim_path), first_before)
            self.assertEqual(self._read_curve_payload(self.other_prim_path), second_before)
            self.assertNotEqual(first_before, second_before)
            notifications.clear()
            omni.kit.undo.redo()
            self.assertTrue(notifications)
            self.assertEqual(set(notifications), {self.curve_id})
            self.assertEqual(self._read_curve_payload(self.prim_path), final_payload)
            self.assertEqual(self._read_curve_payload(self.other_prim_path), final_payload)
        finally:
            del subscription


class TestCurveEditorPopupLifecycle(omni.kit.test.AsyncTestCase):
    """Exercise floating Curve editors through real USD property panels."""

    async def setUp(self):
        """Create the default stage and reset shared undo state."""
        actions = get_action_registry()
        hotkeys = get_hotkey_registry()
        context = get_hotkey_context()
        self.addCleanup(actions.deregister_all_actions_for_extension, __name__)
        self.addCleanup(hotkeys.deregister_all_hotkeys_for_extension, __name__)
        for key, action, callback in (
            ("CTRL+Z", "undo", omni.kit.undo.undo),
            ("CTRL+Y", "redo", omni.kit.undo.redo),
        ):
            actions.register_action(__name__, action, callback)
            self.assertIsNotNone(
                hotkeys.register_hotkey(__name__, key, __name__, action, filter=HotkeyFilter(context=__name__))
            )
        context.push(__name__)
        self.addCleanup(context.pop)
        self._context = omni.usd.get_context("")
        await self._context.new_stage_async()
        self._panel = None
        self._named_context = None
        omni.kit.undo.clear_stack()
        omni.kit.undo.clear_history()

    async def tearDown(self):
        """Release UI, undo state, and stages while retaining the named SDK context."""
        try:
            try:
                try:
                    for key in (KeyboardInput.Z, KeyboardInput.Y, KeyboardInput.LEFT_CONTROL):
                        await emulate_keyboard(KeyboardEventType.KEY_RELEASE, key)
                finally:
                    if field_popup_window._ACTIVE_WINDOW is not None:
                        field_popup_window._ACTIVE_WINDOW.close()
                await ui_test.human_delay(1)
                for context in (self._context, self._named_context):
                    if context is not None and context.get_stage() is not None:
                        selection = context.get_selection()
                        selection.set_selected_prim_paths(
                            [] if selection.get_selected_prim_paths() else ["/World"], False
                        )
                        await context.selection_changed_async()
                        await ui_test.human_delay(1)
            finally:
                if self._panel is not None:
                    with ExitStack() as cleanup:
                        for resource in self._panel:
                            if resource is not None:
                                cleanup.callback(resource.destroy)
        finally:
            try:
                await ui_test.human_delay(1)
            finally:
                omni.kit.undo.clear_stack()
                omni.kit.undo.clear_history()
                try:
                    if self._named_context is not None and self._named_context.get_stage() is not None:
                        await self._named_context.close_stage_async()
                    if self._named_context is not None:
                        self.assertIsNone(self._named_context.get_stage())
                finally:
                    try:
                        if self._context is not None and self._context.get_stage() is not None:
                            await self._context.close_stage_async()
                    finally:
                        self._panel = None
                        self._named_context = None
                        self._context = None
                        await ui_test.human_delay(1)

    async def test_popup_key_actions_respect_keyboard_focus_and_group_undo(self):
        """Add and Delete in the production popup preserve focus ownership and grouped undo."""
        prim_path = "/World/GroupedUndo"
        prim = self._context.get_stage().DefinePrim(prim_path, "Xform")
        curve_ids = ("first", "second")
        for curve_id in curve_ids:
            _seed_curve(prim, curve_id)
        prim.GetAttribute("primvars:second:values").Set([0.2, 0.6])
        layout = {
            "display_name": "Grouped Curves",
            "curve_map": {f"primvars:{curve_id}": curve_id for curve_id in curve_ids},
        }
        grouped_items = [item for curve_id in curve_ids for item in _curve_items("", prim_path, curve_id, curve_id)]
        for item in grouped_items:
            item.edit_group_layout = layout
        self._panel = _build_property_panel(
            "", "Grouped Undo", [USDLogicalGroupOutletItem(layout, "", [prim_path]), *grouped_items]
        )
        window, _model, _delegate, _widget = self._panel
        await ui_test.human_delay()

        # Open the real property control without injecting an undo factory from the test.
        button = ui_test.find(f"{window.title}//Frame/**/Button[*].text=='Grouped Curves'")
        self.assertIsNotNone(button)
        await button.click()
        await ui_test.human_delay()
        host = _find_editor_window("Grouped Curves - Curve Editor")
        self.assertIsNotNone(host)
        omni.kit.undo.clear_stack()

        # Add on both initially selected channels through the popup toolbar.
        button = ui_test.find(f"{host.title}//Frame/**/Button[*].name=='CurveEditorBtnAddKey'")
        self.assertIsNotNone(button)
        await button.click()
        await ui_test.human_delay()
        self.assertEqual(sum(entry.level == 0 for entry in omni.kit.undo.get_undo_stack()), 1)
        for curve_id in curve_ids:
            self.assertEqual(tuple(prim.GetAttribute(f"primvars:{curve_id}:times").Get()), (0.0, 0.5, 1.0))

        # Each public Undo and Redo restores both channels together.
        self.assertTrue(omni.kit.undo.undo())
        await ui_test.human_delay()
        for curve_id in curve_ids:
            self.assertEqual(tuple(prim.GetAttribute(f"primvars:{curve_id}:times").Get()), (0.0, 1.0))
        self.assertTrue(omni.kit.undo.redo())
        await ui_test.human_delay()
        for curve_id in curve_ids:
            self.assertEqual(tuple(prim.GetAttribute(f"primvars:{curve_id}:times").Get()), (0.0, 0.5, 1.0))

        # Delete selected keys across both channels through the focused native window.
        await self._select_popup_keys(host, (2, 3))
        before_delete = {curve_id: _snapshot_curve_payload(prim, curve_id) for curve_id in curve_ids}
        undo_count = sum(entry.level == 0 for entry in omni.kit.undo.get_undo_stack())
        await ui_test.emulate_keyboard_press(KeyboardInput.DEL)
        await ui_test.human_delay()
        after_delete = {curve_id: _snapshot_curve_payload(prim, curve_id) for curve_id in curve_ids}
        self.assertEqual(sum(entry.level == 0 for entry in omni.kit.undo.get_undo_stack()), undo_count + 1)
        for curve_id in curve_ids:
            self.assertEqual(tuple(after_delete[curve_id]["times"]), (0.0, 1.0))
        for operation, expected in ((omni.kit.undo.undo, before_delete), (omni.kit.undo.redo, after_delete)):
            self.assertTrue(operation())
            await ui_test.human_delay()
            self.assertEqual({curve_id: _snapshot_curve_payload(prim, curve_id) for curve_id in curve_ids}, expected)

        await self._check_popup_delete_focus(host, prim, curve_ids)
        await self._check_popup_delete_during_gestures(host, prim, curve_ids)
        await self._check_popup_delete_noops(host, prim, curve_ids)
        await self._check_popup_delete_text_capture(host, prim, curve_ids)

        # Escape still closes through the shared popup lifecycle; a closed editor cannot receive Delete.
        before_close = self._popup_state(prim, curve_ids)
        await ui_test.emulate_keyboard_press(KeyboardInput.ESCAPE)
        await ui_test.human_delay()
        self.assertFalse(host.visible)
        await ui_test.emulate_keyboard_press(KeyboardInput.DEL)
        await ui_test.human_delay()
        self.assertEqual(self._popup_state(prim, curve_ids), before_close)

    async def test_refresh_rebuilds_curve_controls_and_editor_replacement_releases_sessions(self):
        """Open across a panel refresh, keep editing after redraw, and release replaced editor sessions."""
        prim_path = "/World/Looks/Lifecycle"
        prim = self._context.get_stage().DefinePrim(prim_path, "Xform")
        _seed_curve(prim, "curve")
        prim.CreateAttribute("primvars:color:times", Sdf.ValueTypeNames.DoubleArray).Set(Vt.DoubleArray([0.0, 1.0]))
        prim.CreateAttribute("primvars:color:values", Sdf.ValueTypeNames.Color4fArray).Set(
            Vt.Vec4fArray([Gf.Vec4f(1, 0, 0, 1), Gf.Vec4f(0, 0, 1, 1)])
        )
        prim.CreateAttribute("preview", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath())
        curve_items = _curve_items("", prim_path, "curve", "Curve")
        curve_item = next(item for item in curve_items if item.attribute_paths[0].name.endswith(":values"))
        gradient_items = [
            _attribute_item("", prim_path, "primvars:color:times", "Color"),
            _attribute_item("", prim_path, "primvars:color:values", "Gradient"),
        ]
        gradient_pre_open_calls = 0

        def refresh_gradient_then_open(open_editor) -> None:
            """Refresh the real property model before opening the Gradient."""
            nonlocal gradient_pre_open_calls
            gradient_pre_open_calls += 1
            model.refresh()
            open_editor()

        gradient_items[1].pre_open_callback = refresh_gradient_then_open
        self._panel = _build_property_panel(
            "", "Curve Lifecycle", [*curve_items, *gradient_items, _attribute_item("", prim_path, "preview", "Texture")]
        )
        window, model, _delegate, _widget = self._panel
        await ui_test.human_delay()

        curve_selector = f"{window.title}//Frame/**/Button[*].identifier=='{prim_path}.primvars:curve:values'"
        gradient_selector = (
            f"{window.title}//Frame/**/Frame[*].identifier=='{prim_path}.primvars:color:values'"
            "//Rectangle[*].name=='ColorGradientBarOverlay'"
        )
        pre_open_calls = 0

        def refresh_then_open(open_editor) -> None:
            """Refresh the production model before continuing the pending open."""
            nonlocal pre_open_calls
            pre_open_calls += 1
            model.refresh()
            open_editor()

        curve_item.pre_open_callback = refresh_then_open
        await ui_test.find(gradient_selector).click()
        await ui_test.human_delay(1)
        gradient_window = _find_editor_window("Gradient - Gradient Editor")
        self.assertIsNotNone(gradient_window)
        self.assertEqual(gradient_pre_open_calls, 1)
        curve_button = ui_test.find(curve_selector)
        self.assertIsNotNone(curve_button)

        original_destroy = PropertyPrimvarCurveModel.destroy
        with patch.object(PropertyPrimvarCurveModel, "destroy", autospec=True, side_effect=original_destroy) as destroy:
            await curve_button.click()
            await ui_test.human_delay(1)
            curve_window = _find_editor_window("Curve - Curve Editor")
            self.assertIsNotNone(curve_window)
            self.assertFalse(gradient_window.visible)
            self.assertEqual(pre_open_calls, 1)
            rebuilt_button = ui_test.find(curve_selector)
            self.assertIsNotNone(rebuilt_button)
            self.assertIsNot(curve_button.widget, rebuilt_button.widget)

            # Rebuilding the launching row must leave the active editor usable.
            model.refresh()
            await ui_test.human_delay(1)
            self.assertTrue(curve_window.visible)
            self.assertIsNot(rebuilt_button.widget, ui_test.find(curve_selector).widget)
            add_button = ui_test.find(f"{curve_window.title}//Frame/**/Button[*].name=='CurveEditorBtnAddKey'")
            self.assertIsNotNone(add_button)
            original_payload = _snapshot_curve_payload(prim, "curve")
            await add_button.click()
            await ui_test.human_delay(1)
            values = prim.GetAttribute("primvars:curve:values")
            self.assertEqual(list(values.Get()), [0.0, 0.5, 1.0])

            key_selector = f"{curve_window.title}//Frame/**/Rectangle[*].name=='FCurveKey'"
            payloads = [_snapshot_curve_payload(prim, "curve")]
            centers = [sorted(ui_test.find_all(key_selector), key=lambda key: key.center.x)[1].center]
            history_count = len(omni.kit.undo.get_undo_stack())
            click_position = centers[0]
            await emulate_mouse(MouseEventType.MOVE, click_position)
            await ui_test.human_delay(1)
            try:
                await emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN, click_position)
                await ui_test.human_delay(1)
            finally:
                await emulate_mouse(MouseEventType.LEFT_BUTTON_UP, click_position)
            await ui_test.human_delay(1)
            self.assertEqual(
                _snapshot_curve_payload(prim, "curve"),
                payloads[0],
                "A stationary Curve key click must not author payload changes",
            )
            self.assertEqual(len(omni.kit.undo.get_undo_stack()), history_count)

            # Intermediate movement stays live; each release creates only one undo entry.
            for offset in (Vec2(30, -20), Vec2(-15, 30)):
                key = sorted(ui_test.find_all(key_selector), key=lambda key: key.center.x)[1]
                start = key.center
                target = start + offset
                await emulate_mouse(MouseEventType.MOVE, start)
                await ui_test.human_delay(1)
                try:
                    await emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN, start)
                    await ui_test.human_delay(1)
                    for fraction in (0.3, 0.6, 1.0):
                        await emulate_mouse(MouseEventType.MOVE, start + offset * fraction)
                        await ui_test.human_delay(1)
                        self.assertEqual(len(omni.kit.undo.get_undo_stack()), history_count)
                    self.assertNotEqual(
                        _snapshot_curve_payload(prim, "curve"),
                        payloads[-1],
                    )
                finally:
                    await emulate_mouse(MouseEventType.LEFT_BUTTON_UP, target)
                await ui_test.human_delay(1)
                history_count += 1
                self.assertEqual(len(omni.kit.undo.get_undo_stack()), history_count)
                payload = _snapshot_curve_payload(prim, "curve")
                self.assertNotEqual(payload, payloads[-1])
                payloads.append(payload)
                centers.append(sorted(ui_test.find_all(key_selector), key=lambda key: key.center.x)[1].center)

            # Keyboard history must update both the complete USD payload and the still-open rendered Curve.
            for key, state in (
                (KeyboardInput.Z, 1),
                (KeyboardInput.Z, 0),
                (KeyboardInput.Y, 1),
                (KeyboardInput.Y, 2),
                (KeyboardInput.Z, 1),
                (KeyboardInput.Z, 0),
            ):
                await ui_test.emulate_keyboard_press(key, KEYBOARD_MODIFIER_FLAG_CONTROL)
                await ui_test.human_delay(1)
                self.assertTrue(curve_window.visible)
                self.assertEqual(
                    _snapshot_curve_payload(prim, "curve"),
                    payloads[state],
                )
                center = sorted(ui_test.find_all(key_selector), key=lambda key: key.center.x)[1].center
                self.assertAlmostEqual(center.x, centers[state].x, delta=1.0)
                self.assertAlmostEqual(center.y, centers[state].y, delta=1.0)
            await ui_test.emulate_keyboard_press(KeyboardInput.Z, KEYBOARD_MODIFIER_FLAG_CONTROL)
            await ui_test.human_delay(1)
            self.assertEqual(
                _snapshot_curve_payload(prim, "curve"),
                original_payload,
            )

            await ui_test.find(f"{window.title}//Frame/**/Image[*].name=='Preview'").click()
            await ui_test.human_delay(1)
            preview = _find_editor_window("Lifecycle.preview - Texture")
            self.assertIsNotNone(preview)
            self.assertIsNotNone(ui_test.find(f"{preview.title}//Frame/**/Label[*].text=='No texture to preview'"))
            self.assertFalse(curve_window.visible)
            destroy.assert_called_once()
            outgoing_model = destroy.call_args.args[0]
            self.assertIsNone(outgoing_model.usd_listener)
            self.assertIsNone(outgoing_model.usd_notice_token)

        await ui_test.find(gradient_selector).click()
        await ui_test.human_delay(1)
        replacement = _find_editor_window("Gradient - Gradient Editor")
        self.assertIsNotNone(replacement)
        self.assertEqual(gradient_pre_open_calls, 2)
        self.assertFalse(preview.visible)
        self.assertTrue(ui.Inspector.get_children(replacement.frame))
        self._context.get_selection().set_selected_prim_paths([prim_path], False)
        await self._context.selection_changed_async()
        await ui_test.human_delay(1)
        self.assertFalse(replacement.visible)
        self.assertEqual(ui.Inspector.get_children(replacement.frame), [])

        await ui_test.find(curve_selector).click()
        await ui_test.find(curve_selector).click()
        await ui_test.human_delay(1)
        active_editor = field_popup_window._ACTIVE_WINDOW
        self.assertIsInstance(active_editor, CurveFieldEditor)
        self.assertTrue(active_editor.is_open)
        self.assertEqual(pre_open_calls, 3)
        self.assertEqual(
            sum(
                1
                for candidate in ui.Workspace.get_windows()
                if _EDITOR_IDENTITY in candidate.title and candidate.visible
            ),
            1,
        )
        await ui_test.find(f"{active_editor.title}//Frame/**/Button[*].name=='CurveEditorBtnAddKey'").click()
        await ui_test.human_delay(1)
        self.assertEqual(list(values.Get()), [0.0, 0.5, 1.0])

    async def test_named_context_selection_delete_and_undo_stay_bound_to_named_stage(self):
        """Dismiss by the owning selection and edit only the matching path in the named stage."""
        named_context = omni.usd.get_context(_NAMED_CONTEXT_NAME)
        if named_context is None:
            named_context = omni.usd.create_context(_NAMED_CONTEXT_NAME)
        self.assertIsNone(named_context.get_stage())
        self._named_context = named_context
        await named_context.new_stage_async()

        prim_path = "/World/Looks/NamedContext"
        _seed_curve(self._context.get_stage().DefinePrim(prim_path, "Xform"), "grouped")
        _seed_curve(named_context.get_stage().DefinePrim(prim_path, "Xform"), "grouped")
        named_context.get_stage().GetPrimAtPath(prim_path).CreateAttribute("preview", Sdf.ValueTypeNames.Asset).Set(
            Sdf.AssetPath()
        )
        layout = {"display_name": "Grouped Curves", "curve_map": {"primvars:grouped": "grouped"}}
        grouped_items = _curve_items(_NAMED_CONTEXT_NAME, prim_path, "grouped", "Grouped Curve")
        for item in grouped_items:
            item.edit_group_layout = layout
        outlet = USDLogicalGroupOutletItem(layout, _NAMED_CONTEXT_NAME, [prim_path])
        self._panel = _build_property_panel(
            _NAMED_CONTEXT_NAME,
            "Named Curve Lifecycle",
            [outlet, *grouped_items, _attribute_item(_NAMED_CONTEXT_NAME, prim_path, "preview", "Texture")],
        )
        window, _model, _delegate, _widget = self._panel
        await ui_test.human_delay()

        default_values = self._context.get_stage().GetPrimAtPath(prim_path).GetAttribute("primvars:grouped:values")
        named_values = named_context.get_stage().GetPrimAtPath(prim_path).GetAttribute("primvars:grouped:values")
        default_selection = self._context.get_selection()
        named_selection = named_context.get_selection()
        default_selection.set_selected_prim_paths([prim_path], False)
        named_selection.set_selected_prim_paths([prim_path], False)
        await ui_test.human_delay()

        button_selector = f"{window.title}//Frame/**/Button[*].text=='Grouped Curves'"
        await ui_test.find(button_selector).click()
        await ui_test.human_delay(1)
        host = _find_editor_window("Grouped Curves - Curve Editor")
        self.assertIsNotNone(host)

        default_selection.set_selected_prim_paths([], False)
        await self._context.selection_changed_async()
        await ui_test.human_delay()
        self.assertTrue(host.visible)
        named_selection.set_selected_prim_paths([], False)
        await named_context.selection_changed_async()
        await ui_test.human_delay(1)
        self.assertFalse(host.visible)

        await ui_test.find(button_selector).click()
        await ui_test.human_delay(1)
        host = _find_editor_window("Grouped Curves - Curve Editor")
        self.assertIsNotNone(host)
        delete_button = ui_test.find(f"{host.title}//Frame/**/Image[*].name=='CurveEditorTreeDelete'")
        self.assertIsNotNone(delete_button)
        await delete_button.click()
        await ui_test.human_delay(1)
        self.assertEqual(list(named_values.Get()), [])
        self.assertEqual(list(default_values.Get()), [0.0, 1.0])

        omni.kit.undo.undo()
        await ui_test.human_delay(1)
        self.assertEqual(list(named_values.Get()), [0.0, 1.0])
        self.assertEqual(list(default_values.Get()), [0.0, 1.0])

        await ui_test.find(f"{window.title}//Frame/**/Image[*].name=='Preview'").click()
        await ui_test.human_delay(1)
        preview = _find_editor_window("NamedContext.preview - Texture")
        self.assertIsNotNone(preview)
        default_selection.set_selected_prim_paths([prim_path], False)
        await self._context.selection_changed_async()
        await ui_test.human_delay()
        self.assertTrue(preview.visible)
        named_selection.set_selected_prim_paths([prim_path], False)
        await named_context.selection_changed_async()
        await ui_test.human_delay(1)
        self.assertFalse(preview.visible)

    @staticmethod
    def _popup_state(prim, curve_ids) -> tuple:
        """Snapshot every channel and both history stacks for keyboard no-op checks."""
        return (
            {curve_id: _snapshot_curve_payload(prim, curve_id) for curve_id in curve_ids},
            tuple(omni.kit.undo.get_undo_stack()),
            tuple(omni.kit.undo.get_redo_stack()),
        )

    @staticmethod
    def _popup_handles(host, name="FCurveKey") -> list:
        """Locate native curve handles in screen order."""
        return sorted(
            ui_test.find_all(f"{host.title}//Frame/**/Rectangle[*].name=='{name}'"),
            key=lambda handle: (handle.center.x, handle.center.y),
        )

    async def _select_popup_keys(self, host, indices) -> None:
        """Select native key handles without coalescing pointer movement with the press."""
        for count, index in enumerate(indices):
            key = self._popup_handles(host)[index]
            await emulate_mouse(MouseEventType.MOVE, key.center)
            await ui_test.human_delay()
            if count:
                async with ui_test.KeyDownScope(KeyboardInput.LEFT_SHIFT):
                    await ui_test.emulate_mouse_click()
                    await ui_test.human_delay()
            else:
                await ui_test.emulate_mouse_click()
            await ui_test.human_delay()

    async def _check_popup_delete_focus(self, host, prim, curve_ids) -> None:
        """Verify keyboard boundaries, native window focus, and real field capture."""
        # Undo clears selection while keeping a redo action, which plain Delete must preserve.
        self.assertTrue(omni.kit.undo.undo())
        await ui_test.human_delay()
        before = self._popup_state(prim, curve_ids)
        self.assertTrue(before[2])
        await ui_test.emulate_keyboard_press(KeyboardInput.DEL)
        await ui_test.human_delay()
        self.assertEqual(self._popup_state(prim, curve_ids), before)
        await self._select_popup_keys(host, (2, 3))
        before = self._popup_state(prim, curve_ids)
        await emulate_keyboard(KeyboardEventType.KEY_RELEASE, KeyboardInput.DEL)
        await ui_test.human_delay()
        self.assertEqual(self._popup_state(prim, curve_ids), before)
        for key, modifier in (
            (KeyboardInput.LEFT_CONTROL, KEYBOARD_MODIFIER_FLAG_CONTROL),
            (KeyboardInput.LEFT_SHIFT, KEYBOARD_MODIFIER_FLAG_SHIFT),
            (KeyboardInput.LEFT_ALT, KEYBOARD_MODIFIER_FLAG_ALT),
            (KeyboardInput.LEFT_SUPER, KEYBOARD_MODIFIER_FLAG_SUPER),
        ):
            async with ui_test.KeyDownScope(key):
                await emulate_keyboard(KeyboardEventType.KEY_PRESS, KeyboardInput.DEL, modifier)
                await ui_test.human_delay()
                await emulate_keyboard(KeyboardEventType.KEY_RELEASE, KeyboardInput.DEL, modifier)
                await ui_test.human_delay()
            await ui_test.human_delay()
            self.assertEqual(self._popup_state(prim, curve_ids), before)

        # A focus change without an outside click leaves the popup open but suspends its shortcut.
        other = ui.Window(
            "Curve Keyboard Focus", width=_KEYBOARD_FOCUS_WINDOW_WIDTH, height=_KEYBOARD_FOCUS_WINDOW_HEIGHT
        )
        try:
            other.focus()
            await ui_test.human_delay()
            await ui_test.emulate_keyboard_press(KeyboardInput.DEL)
            await ui_test.human_delay()
            self.assertTrue(host.visible)
            self.assertEqual(self._popup_state(prim, curve_ids), before)
        finally:
            other.destroy()
        host.focus()
        await ui_test.human_delay()
        await emulate_mouse(MouseEventType.MOVE, Vec2(host.position_x - 4, host.position_y - 4))
        await ui_test.human_delay()
        await ui_test.emulate_keyboard_press(KeyboardInput.NUMPAD_DEL)
        await ui_test.human_delay()
        self.assertEqual(
            sum(entry.level == 0 for entry in omni.kit.undo.get_undo_stack()),
            sum(entry.level == 0 for entry in before[1]) + 1,
        )
        for curve_id in curve_ids:
            self.assertEqual(len(_snapshot_curve_payload(prim, curve_id)["times"]), 2)
        self.assertTrue(omni.kit.undo.undo())
        await ui_test.human_delay()
        self.assertEqual(self._popup_state(prim, curve_ids)[0], before[0])

    async def _check_popup_delete_text_capture(self, host, prim, curve_ids) -> None:
        """Keep Delete inside native string and numeric editing despite the pointer leaving the field."""
        self.assertTrue(omni.kit.undo.undo())
        await ui_test.human_delay()
        await self._select_popup_keys(host, (2, 3))
        # These real fields share the native popup without replacing its production editor or keyboard route.
        root = ui.Inspector.get_children(host.frame)[0]
        with host.frame:
            with ui.VStack() as contents:
                with ui.HStack(height=ui.Pixel(_TEXT_CAPTURE_ROW_HEIGHT)):
                    text = ui.StringField(identifier="CurveDeleteText", height=ui.Pixel(_TEXT_CAPTURE_ROW_HEIGHT))
                    text.model.set_value("CurveHost")
                    number = ui.FloatField(identifier="CurveDeleteNumber", height=ui.Pixel(_TEXT_CAPTURE_ROW_HEIGHT))
                    number.model.set_value(12.5)
                contents.add_child(root)
        await ui_test.human_delay()
        for field, expected in ((text, "urveHost"), (number, 2.5)):
            center = Vec2(
                field.screen_position_x + field.computed_width / 2, field.screen_position_y + field.computed_height / 2
            )
            await emulate_mouse(MouseEventType.MOVE, center)
            await ui_test.human_delay()
            await ui_test.emulate_mouse_click(double=field is number)
            await ui_test.human_delay()
            await ui_test.emulate_keyboard_press(KeyboardInput.HOME)
            await ui_test.human_delay()
            before = self._popup_state(prim, curve_ids)
            await emulate_mouse(MouseEventType.MOVE, self._popup_handles(host)[2].center)
            await ui_test.human_delay()
            await ui_test.emulate_keyboard_press(KeyboardInput.DEL)
            await ui_test.human_delay()
            self.assertEqual(self._popup_state(prim, curve_ids), before)
            await ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
            await ui_test.human_delay()
            self.assertEqual(field.model.as_string if field is text else field.model.as_float, expected)

    async def _check_popup_delete_during_gestures(self, host, prim, curve_ids) -> None:
        """Finish interrupted ordinary edits and give insertion and its deletion separate history entries."""
        # Delete preserves held handles; a sibling USD edit must finish their old transaction before rebuilding.
        for handle_name, moved in (("FCurveKey", False), ("FCurveKey", True), ("FCurveTangent", True)):
            await self._select_popup_keys(host, (2,))
            if handle_name == "FCurveTangent":
                custom = ui_test.find_all(f"{host.title}//Frame/**/Button[*].tooltip=='Custom Tangent'")
                await custom[0].click()
                await ui_test.human_delay()
            handles = self._popup_handles(host, handle_name)
            self.assertTrue(handles)
            start = handles[2 if handle_name == "FCurveKey" else 0].center
            target = start + Vec2(12, -8)
            before = self._popup_state(prim, curve_ids)
            undo_count = sum(entry.level == 0 for entry in before[1])
            await emulate_mouse(MouseEventType.MOVE, start)
            await ui_test.human_delay()
            try:
                await emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN, start)
                await ui_test.human_delay()
                if moved:
                    await emulate_mouse(MouseEventType.MOVE, target)
                    await ui_test.human_delay()
                during = self._popup_state(prim, curve_ids)
                self.assertEqual(during[0] != before[0], moved)
                await ui_test.emulate_keyboard_press(KeyboardInput.DEL)
                await ui_test.human_delay()
                self.assertEqual(self._popup_state(prim, curve_ids), during)

                values_attr = prim.GetAttribute(f"primvars:{curve_ids[1]}:values")
                values = list(values_attr.Get())
                values[0] += 0.01
                self.assertTrue(values_attr.Set(values))
                await ui_test.human_delay()
                refreshed = self._popup_state(prim, curve_ids)
                self.assertEqual(refreshed[0][curve_ids[0]], during[0][curve_ids[0]])
                self.assertEqual(
                    sum(entry.level == 0 for entry in refreshed[1]),
                    undo_count + int(moved),
                    f"Refreshing the sibling channel must finish the held {handle_name} edit (moved={moved})",
                )
                if not moved:
                    self.assertTrue(before[2])
                    self.assertEqual(refreshed[1:], before[1:])
                await emulate_mouse(MouseEventType.MOVE, target + Vec2(12, -8))
                await ui_test.human_delay()
                self.assertEqual(self._popup_state(prim, curve_ids), refreshed)
            finally:
                await emulate_mouse(MouseEventType.LEFT_BUTTON_UP, target + Vec2(12, -8))
                await ui_test.human_delay()
            self.assertEqual(self._popup_state(prim, curve_ids), refreshed)
            if moved:
                original = {**before[0], curve_ids[1]: refreshed[0][curve_ids[1]]}
                for operation, expected in (
                    (omni.kit.undo.undo, original),
                    (omni.kit.undo.redo, refreshed[0]),
                    (omni.kit.undo.undo, original),
                ):
                    self.assertTrue(operation())
                    await ui_test.human_delay(5)
                    self.assertEqual(self._popup_state(prim, curve_ids)[0], expected)

        # The sibling channel must still group multiple live moves into one ordinary drag action.
        await self._select_popup_keys(host, (3,))
        start = self._popup_handles(host)[3].center
        target = start + Vec2(24, -16)
        before = self._popup_state(prim, curve_ids)
        await emulate_mouse(MouseEventType.MOVE, start)
        await ui_test.human_delay()
        try:
            await emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN, start)
            await ui_test.human_delay()
            for position in (start + Vec2(12, -8), target):
                await emulate_mouse(MouseEventType.MOVE, position)
                await ui_test.human_delay()
                self.assertEqual(self._popup_state(prim, curve_ids)[1], before[1])
        finally:
            await emulate_mouse(MouseEventType.LEFT_BUTTON_UP, target)
            await ui_test.human_delay()
        after = self._popup_state(prim, curve_ids)
        self.assertEqual(after[0][curve_ids[0]], before[0][curve_ids[0]])
        self.assertNotEqual(after[0][curve_ids[1]], before[0][curve_ids[1]])
        self.assertEqual(sum(entry.level == 0 for entry in after[1]), sum(entry.level == 0 for entry in before[1]) + 1)
        for operation, expected in (
            (omni.kit.undo.undo, before[0]),
            (omni.kit.undo.redo, after[0]),
            (omni.kit.undo.undo, before[0]),
        ):
            self.assertTrue(operation())
            await ui_test.human_delay(5)
            self.assertEqual(self._popup_state(prim, curve_ids)[0], expected)

        # The unchanged linear first segment provides an exact native insertion target between its handles.
        keys = self._popup_handles(host)
        start = (keys[1].center + keys[2].center) * 0.5
        target = start + Vec2(10, -5)
        before = self._popup_state(prim, curve_ids)
        undo_count = sum(entry.level == 0 for entry in before[1])
        await emulate_mouse(MouseEventType.MOVE, start)
        await ui_test.human_delay()
        try:
            await emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN, start)
            await ui_test.human_delay()
            self.assertEqual(sum(len(_snapshot_curve_payload(prim, curve_id)["times"]) for curve_id in curve_ids), 7)
            await emulate_mouse(MouseEventType.MOVE, target)
            await ui_test.human_delay()
            inserted = self._popup_state(prim, curve_ids)[0]
            await ui_test.emulate_keyboard_press(KeyboardInput.DEL)
            await ui_test.human_delay()
            deleted = self._popup_state(prim, curve_ids)[0]
            self.assertEqual(sum(entry.level == 0 for entry in omni.kit.undo.get_undo_stack()), undo_count + 2)
            self.assertEqual(sum(len(payload["times"]) for payload in deleted.values()), 6)
        finally:
            await emulate_mouse(MouseEventType.LEFT_BUTTON_UP, target)
            await ui_test.human_delay()
        for operation, expected in (
            (omni.kit.undo.undo, inserted),
            (omni.kit.undo.undo, before[0]),
            (omni.kit.undo.redo, inserted),
            (omni.kit.undo.redo, deleted),
        ):
            self.assertTrue(operation())
            await ui_test.human_delay()
            self.assertEqual(self._popup_state(prim, curve_ids)[0], expected)

    async def _check_popup_delete_noops(self, host, prim, curve_ids) -> None:
        """Preserve each channel's last key and a pending redo action."""
        await self._select_popup_keys(host, range(len(self._popup_handles(host))))
        await ui_test.emulate_keyboard_press(KeyboardInput.DEL)
        await ui_test.human_delay()
        for curve_id in curve_ids:
            self.assertEqual(len(_snapshot_curve_payload(prim, curve_id)["times"]), 1)
        add = ui_test.find(f"{host.title}//Frame/**/Button[*].name=='CurveEditorBtnAddKey'")
        await add.click()
        await ui_test.human_delay()
        self.assertTrue(omni.kit.undo.undo())
        await ui_test.human_delay()
        await self._select_popup_keys(host, (0, 1))
        before = self._popup_state(prim, curve_ids)
        self.assertTrue(before[2])
        for key in (KeyboardInput.DEL, KeyboardInput.NUMPAD_DEL):
            await ui_test.emulate_keyboard_press(key)
            await ui_test.human_delay()
            self.assertEqual(self._popup_state(prim, curve_ids), before)
