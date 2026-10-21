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

E2E Integration Tests - Full stack tests for curve editor.

Tests:
- Multi-curve editing
- FCurveWidget ↔ GroupedKeysModel data flow
"""

import carb.input
import omni.kit.app
import omni.kit.test
import omni.kit.ui_test as ui_test
from omni import ui

from omni.flux.utils.widget import InMemoryGroupedKeysModel
from omni.flux.fcurve.widget import FCurve, FCurveKey, InfinityType, KeyReference, TangentType

from ... import CurveEditorLayout, CurveEditorWidget
from ...panels import CurveTreePanel
from ...payload import curve_to_payload, payload_to_curve

__all__ = [
    "TestInfinityTypes",
    "TestMultiCurveEditing",
    "TestTangentTypes",
]


def _commit_payload(model, curve_id: str, curve: FCurve) -> None:
    model.commit_payload(curve_id, curve_to_payload(curve))


def _get_curve(model, curve_id: str) -> FCurve | None:
    return payload_to_curve(curve_id, model.get_payload(curve_id))


class TestMultiCurveEditing(omni.kit.test.AsyncTestCase):
    """
    Test multi-curve editing functionality.
    """

    async def setUp(self):
        """Set up test environment."""
        self.model = InMemoryGroupedKeysModel()
        self.widget = None
        self.window = None

    async def tearDown(self):
        """Clean up."""
        if self.widget:
            self.widget.destroy()
            self.widget = None
        if self.window:
            self.window.destroy()
        if self.model:
            self.model.destroy()

    async def test_multiple_curves_display(self):
        """
        Test that multiple curves can be displayed simultaneously.
        """
        # Create multiple curves
        curves = [
            FCurve(
                id="curve_r",
                keys=[FCurveKey(time=0.0, value=0.0), FCurveKey(time=1.0, value=1.0)],
                color=0xFFFF0000,  # Red
            ),
            FCurve(
                id="curve_g",
                keys=[FCurveKey(time=0.0, value=0.5), FCurveKey(time=1.0, value=0.5)],
                color=0xFF00FF00,  # Green
            ),
            FCurve(
                id="curve_b",
                keys=[FCurveKey(time=0.0, value=1.0), FCurveKey(time=1.0, value=0.0)],
                color=0xFF0000FF,  # Blue
            ),
        ]

        for curve in curves:
            _commit_payload(self.model, curve.id, curve)

        # Create widget
        self.window = ui.Window("Multi-Curve Test", width=600, height=400)
        with self.window.frame:
            self.widget = CurveEditorWidget(
                model=self.model,
                show_toolbar=True,
            )

        # Let UI build
        for _ in range(10):
            await omni.kit.app.get_app().next_update_async()

        # Verify all curves are accessible
        curve_ids = self.widget.model.group_ids
        self.assertEqual(len(curve_ids), 3)
        self.assertIn("curve_r", curve_ids)
        self.assertIn("curve_g", curve_ids)
        self.assertIn("curve_b", curve_ids)

        # Verify FCurveWidget received the curves
        if self.widget.fcurve_widget:
            fcurve_curves = self.widget.fcurve_widget.curves
            self.assertEqual(len(fcurve_curves), 3)

    async def test_tree_branch_is_only_rendered_for_populated_group(self):
        """Render only populated branches and support key deletion without a toolbar."""
        curve = FCurve(
            id="populated_curve",
            keys=[FCurveKey(time=0.0, value=0.0), FCurveKey(time=1.0, value=1.0)],
        )
        _commit_payload(self.model, curve.id, curve)
        layout: CurveEditorLayout = {
            "children": {
                "populated": {
                    "display_name": "Populated Group",
                    "curves": [{"id": curve.id, "display_name": "Populated Curve"}],
                },
                "empty": {"display_name": "Empty Group"},
            }
        }
        self.window = ui.Window("Curve Tree Branch Test", width=600, height=400)

        with self.window.frame:
            self.widget = CurveEditorWidget(model=self.model, layout=layout, show_toolbar=False)
        await ui_test.human_delay()

        labels = [
            label for label in ui_test.find_all("Curve Tree Branch Test//Frame/**/Label[*]") if label.widget.visible
        ]
        self.assertIn("Populated Group", [label.widget.text for label in labels])
        self.assertIn("Empty Group", [label.widget.text for label in labels])
        branches = [
            branch
            for branch in ui_test.find_all("Curve Tree Branch Test//Frame/**/Image[*].identifier=='property_branch'")
            if branch.widget.visible
        ]
        self.assertEqual(1, len(branches))
        curve_labels = [
            label
            for label in ui_test.find_all("Curve Tree Branch Test//Frame/**/Label[*]")
            if label.widget.visible and label.widget.text == "Populated Curve"
        ]
        self.assertEqual(1, len(curve_labels))

        # A toolbar-free host can delete the selected key through the public editor action.
        await curve_labels[0].click()
        await ui_test.human_delay()
        self.assertIn(curve.id, self.widget.fcurve_widget.curves)
        for key_count in (2, 1):
            self.widget.fcurve_widget.select_keys([KeyReference(curve.id, 0)])
            await ui_test.human_delay()
            self.assertEqual(1, len(self.widget.selection.keys))
            before = self.model.get_payload(curve.id)

            self.widget.delete_selected_keys()
            await ui_test.human_delay()

            self.assertEqual(1, len(_get_curve(self.model, curve.id).keys))
            if key_count == 2:
                self.assertNotEqual(before, self.model.get_payload(curve.id))
                self.assertTrue(self.widget.selection.is_empty)
            else:
                # The last key remains selected and its entire payload is unchanged.
                self.assertEqual(before, self.model.get_payload(curve.id))
                self.assertEqual(1, len(self.widget.selection.keys))

        self.widget.destroy()
        self.widget.delete_selected_keys()
        self.assertEqual(before, self.model.get_payload(curve.id))

    async def test_tree_selection_publishes_only_selected_channel_ids(self):
        """Use native row selection as the displayed-channel set."""
        selected_curve_ids = []
        layout: CurveEditorLayout = {
            "children": {
                "group": {
                    "display_name": "Group",
                    "curves": [
                        {"id": "x", "display_name": "X"},
                        {"id": "y", "display_name": "Y"},
                        {"id": "z", "display_name": "Z"},
                    ],
                }
            },
            "curves": [{"id": "w", "display_name": "W"}],
        }
        self.window = ui.Window("Curve Tree Selection Test", width=600, height=400)
        with self.window.frame:
            panel = CurveTreePanel(layout, on_curves_selected=selected_curve_ids.append)
        try:
            await ui_test.human_delay()
            self.assertEqual([{"w", "x", "y", "z"}], selected_curve_ids)

            # Selecting a group includes its children; Control-click removes one channel from that set.
            group = ui_test.find("Curve Tree Selection Test//Frame/**/Label[*].identifier=='CurveTreeGroup::group'")
            await group.click()
            await ui_test.human_delay()
            async with ui_test.KeyDownScope(carb.input.KeyboardInput.LEFT_CONTROL):
                await ui_test.find(
                    "Curve Tree Selection Test//Frame/**/Label[*].identifier=='CurveTreeChannel::y'"
                ).click()
            await ui_test.human_delay()
            self.assertEqual({"x", "z"}, selected_curve_ids[-1])
        finally:
            panel.destroy()

    async def test_native_channel_selection_updates_the_composed_editor(self):
        """Drive channel selection through the composed tree and canvas workflow."""
        channel_colors = {
            "x": 0xFF2030A0,
            "y": 0xFF208030,
            "z": 0xFFA03020,
            "empty": 0xFF806020,
            "future": 0xFF208080,
        }
        channel_styles = {curve_id: f"TestCurveChannel{curve_id.title()}" for curve_id in channel_colors}
        for curve_id in ("x", "y", "z"):
            _commit_payload(
                self.model,
                curve_id,
                FCurve(id=curve_id, keys=[FCurveKey(time=0.0, value=0.0), FCurveKey(time=1.0, value=1.0)]),
            )
        layout: CurveEditorLayout = {
            "children": {
                "group": {
                    "display_name": "Group",
                    "curves": [
                        {
                            "id": curve_id,
                            "display_name": curve_id.title(),
                            "display_color": color,
                            "label_style_name": channel_styles[curve_id],
                        }
                        for curve_id, color in channel_colors.items()
                    ],
                }
            }
        }

        def create_curve(curve_id: str) -> None:
            _commit_payload(
                self.model,
                curve_id,
                FCurve(id=curve_id, keys=[FCurveKey(time=0.0, value=0.0), FCurveKey(time=1.0, value=1.0)]),
            )

        self.window = ui.Window("Composed Curve Selection Test", width=600, height=400)
        self.window.frame.style = {
            selector: {"color": color}
            for curve_id, normal_color in channel_colors.items()
            for selector, color in (
                (f"Label::{channel_styles[curve_id]}", normal_color),
                (f"Label::{channel_styles[curve_id]}:selected", 0xFFE0E0E0),
            )
        }
        with self.window.frame:
            self.widget = CurveEditorWidget(model=self.model, layout=layout, on_create_curve=create_curve)
        await ui_test.human_delay()
        payloads_before_selection = {curve_id: self.model.get_payload(curve_id) for curve_id in ("x", "y", "z")}
        self.assertEqual({"x", "y", "z"}, set(self.widget.fcurve_widget.curves))

        async def click_channel(curve_id: str, modifier: carb.input.KeyboardInput | None = None) -> None:
            """Select a channel through its native row, optionally retaining or extending selection."""
            query = f"Composed Curve Selection Test//Frame/**/Label[*].identifier=='CurveTreeChannel::{curve_id}'"
            if modifier is None:
                await ui_test.find(query).click()
            else:
                async with ui_test.KeyDownScope(modifier):
                    await ui_test.find(query).click()
            await ui_test.human_delay()

        def assert_selected_labels(expected: set[str]) -> None:
            """Verify semantic label styles survive selection without recoloring curves."""
            selected = set()
            for curve_id, style_name in channel_styles.items():
                label = ui_test.find(
                    f"Composed Curve Selection Test//Frame/**/Label[*].identifier=='CurveTreeChannel::{curve_id}'"
                ).widget
                self.assertEqual(style_name, label.name)
                if label.selected:
                    selected.add(curve_id)
            self.assertEqual(expected, selected)
            self.assertEqual(
                {curve_id: channel_colors[curve_id] for curve_id in self.widget.fcurve_widget.curves},
                {curve_id: curve.color for curve_id, curve in self.widget.fcurve_widget.curves.items()},
            )

        # Native single, Control, and Shift selection determine the displayed channels without recoloring them.
        assert_selected_labels({"x", "y", "z", "empty", "future"})
        await click_channel("x")
        self.assertEqual({"x"}, set(self.widget.fcurve_widget.curves))
        assert_selected_labels({"x"})
        await click_channel("y", carb.input.KeyboardInput.LEFT_CONTROL)
        self.assertEqual({"x", "y"}, set(self.widget.fcurve_widget.curves))
        assert_selected_labels({"x", "y"})
        await click_channel("z", carb.input.KeyboardInput.LEFT_SHIFT)
        self.assertEqual({"x", "y", "z"}, set(self.widget.fcurve_widget.curves))
        assert_selected_labels({"x", "y", "z"})

        # Filtering retains keys on displayed channels, and clearing the last channel disables Add.
        self.widget.fcurve_widget.select_keys([KeyReference("x", 0), KeyReference("z", 1)])
        await click_channel("x")
        self.assertEqual([KeyReference("x", 0)], self.widget.fcurve_widget.selection.keys)
        await click_channel("x", carb.input.KeyboardInput.LEFT_CONTROL)
        self.assertEqual({}, self.widget.fcurve_widget.curves)
        assert_selected_labels(set())
        add_key = ui_test.find("Composed Curve Selection Test//Frame/**/Button[*].identifier=='CurveEditorBtnAddKey'")
        self.assertFalse(add_key.widget.enabled)
        self.assertEqual(
            payloads_before_selection,
            {curve_id: self.model.get_payload(curve_id) for curve_id in ("x", "y", "z")},
        )

        # An external reload must respect the channel filter and discard stale key selection.
        await click_channel("x")
        self.widget.fcurve_widget.select_keys([KeyReference("x", 0)])
        self.model.simulate_external_change(
            "x",
            curve_to_payload(FCurve(id="x", keys=[FCurveKey(time=0.0, value=0.2), FCurveKey(time=1.0, value=0.8)])),
        )
        await ui_test.human_delay()
        self.assertEqual({"x"}, set(self.widget.fcurve_widget.curves))
        self.assertTrue(self.widget.fcurve_widget.selection.is_empty)

        # Creating a selected empty channel loads its new data without revealing unselected channels.
        await click_channel("empty")
        assert_selected_labels({"empty"})
        await ui_test.find(
            "Composed Curve Selection Test//Frame/**/Image[*].identifier=='CurveEditorTreeAdd::empty'"
        ).click()
        await ui_test.human_delay()
        self.assertEqual({"empty"}, set(self.widget.fcurve_widget.curves))
        assert_selected_labels({"empty"})

        # Newly authored data appears for the channel already selected in the tree.
        await click_channel("future")
        self.assertEqual({}, self.widget.fcurve_widget.curves)
        assert_selected_labels({"future"})
        self.model.simulate_external_change(
            "future",
            curve_to_payload(
                FCurve(id="future", keys=[FCurveKey(time=0.0, value=0.2), FCurveKey(time=1.0, value=0.8)])
            ),
        )
        await ui_test.human_delay()
        self.assertEqual({"future"}, set(self.widget.fcurve_widget.curves))
        assert_selected_labels({"future"})


class TestTangentTypes(omni.kit.test.AsyncTestCase):
    """
    Test tangent type handling.
    """

    async def setUp(self):
        """Set up test environment."""
        self.model = InMemoryGroupedKeysModel()

    async def tearDown(self):
        """Clean up."""
        if self.model:
            self.model.destroy()

    async def test_tangent_type_preservation(self):
        """
        Test that tangent types are preserved through commit/get cycle.
        """
        # Create curve with various tangent types
        curve = FCurve(
            id="tangent_test",
            keys=[
                FCurveKey(
                    time=0.0,
                    value=0.0,
                    in_tangent_type=TangentType.FLAT,
                    out_tangent_type=TangentType.LINEAR,
                ),
                FCurveKey(
                    time=0.5,
                    value=1.0,
                    in_tangent_type=TangentType.AUTO,
                    out_tangent_type=TangentType.AUTO,
                ),
                FCurveKey(
                    time=1.0,
                    value=0.0,
                    in_tangent_type=TangentType.SMOOTH,
                    out_tangent_type=TangentType.STEP,
                ),
            ],
        )

        _commit_payload(self.model, "tangent_test", curve)
        retrieved = _get_curve(self.model, "tangent_test")

        # Verify tangent types preserved
        self.assertEqual(retrieved.keys[0].in_tangent_type, TangentType.FLAT)
        self.assertEqual(retrieved.keys[0].out_tangent_type, TangentType.LINEAR)
        self.assertEqual(retrieved.keys[1].in_tangent_type, TangentType.AUTO)
        self.assertEqual(retrieved.keys[1].out_tangent_type, TangentType.AUTO)
        self.assertEqual(retrieved.keys[2].in_tangent_type, TangentType.SMOOTH)
        self.assertEqual(retrieved.keys[2].out_tangent_type, TangentType.STEP)


class TestInfinityTypes(omni.kit.test.AsyncTestCase):
    """
    Test infinity type handling.
    """

    async def setUp(self):
        """Set up test environment."""
        self.model = InMemoryGroupedKeysModel()

    async def tearDown(self):
        """Clean up."""
        if self.model:
            self.model.destroy()

    async def test_infinity_type_preservation(self):
        """
        Test that infinity types are preserved through commit/get cycle.
        """
        curve = FCurve(
            id="infinity_test",
            keys=[
                FCurveKey(time=0.0, value=0.0),
                FCurveKey(time=1.0, value=1.0),
            ],
            pre_infinity=InfinityType.LINEAR,
            post_infinity=InfinityType.CONSTANT,
        )

        _commit_payload(self.model, "infinity_test", curve)
        retrieved = _get_curve(self.model, "infinity_test")

        self.assertEqual(retrieved.pre_infinity, InfinityType.LINEAR)
        self.assertEqual(retrieved.post_infinity, InfinityType.CONSTANT)
