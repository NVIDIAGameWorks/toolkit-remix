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

import asyncio

import omni.kit.test
import omni.ui as ui
import omni.usd
from carb.input import KeyboardInput
from lightspeed.common.constants import PARTICLE_SCHEMA_NAME, PROPERTIES_NAMES_COLUMN_WIDTH
from omni.kit import ui_test

from ... import ParticleSystemPropertyWidget
from ...particle_edit_groups import PARTICLE_EDIT_GROUPS

__all__ = ["TestParticlePaletteWorkflow"]


def _find_editor_window(title: str):
    """Find the visible native window for one particle curve editor."""
    title = f"{title}###PropertyPanelFloatingEditor_"
    return next(
        (window for window in ui.Workspace.get_windows() if window.title.startswith(title) and window.visible), None
    )


class TestParticlePaletteWorkflow(omni.kit.test.AsyncTestCase):
    """Exercise the particle panel's themed curve editors through their native controls."""

    async def setUp(self):
        """Create a real particle prim with populated size, velocity, and rotation curves."""
        self._context = omni.usd.get_context("")
        await self._context.new_stage_async()
        self._stage = self._context.get_stage()
        self._prim = self._stage.DefinePrim("/Particle", "Mesh")
        self._prim.ApplyAPI(PARTICLE_SCHEMA_NAME)
        for group_id in ("size", "velocity", "rotationSpeed"):
            for curve_id in PARTICLE_EDIT_GROUPS[group_id]["curve_map"]:
                self._prim.GetAttribute(f"{curve_id}:times").Set([0.0, 1.0])
                self._prim.GetAttribute(f"{curve_id}:values").Set([1.0, 2.0])
        self._window = None
        self._widget = None
        self._refresh_subscription = None

    async def tearDown(self):
        """Close native editors through selection before releasing the panel and stage."""
        self._refresh_subscription = None
        selection = self._context.get_selection()
        if selection.get_selected_prim_paths():
            selection.set_selected_prim_paths([], False)
            await self._context.selection_changed_async()
        await ui_test.human_delay(1)
        if self._widget is not None:
            self._widget.destroy()
        if self._window is not None:
            self._window.destroy()
        await self._context.close_stage_async()
        self._widget = None
        self._window = None
        self._prim = None
        self._stage = None
        self._context = None

    async def _open_particle_panel(self):
        """Select the particle and reveal its curve property buttons."""
        prim_path = str(self._prim.GetPath())
        self._context.get_selection().set_selected_prim_paths([prim_path], False)
        self._window = ui.Window("Particle Curve Workflow", width=800, height=700)
        with self._window.frame:
            self._widget = ParticleSystemPropertyWidget(
                context_name="",
                tree_column_widths=[PROPERTIES_NAMES_COLUMN_WIDTH, ui.Fraction(1)],
                right_aligned_labels=False,
                columns_resizable=True,
            )
            self._widget.show(True)
        refresh_done = asyncio.Event()
        self._refresh_subscription = self._widget.subscribe_refresh_done(refresh_done.set)
        self._widget.refresh([prim_path])
        await asyncio.wait_for(refresh_done.wait(), timeout=5)
        await ui_test.human_delay()
        await ui_test.find(f"{self._window.title}//Frame/**/Label[*].text=='Spawn'").click()
        await ui_test.human_delay()

    async def test_particle_size_add_then_deselect_prevents_key_deletion(self):
        """Preserve every Size channel when Delete follows deselection of a newly added key."""
        curve_id = "particle:minSize:x"
        self._prim.GetAttribute(f"primvars:{curve_id}:times").Set([])
        self._prim.GetAttribute(f"primvars:{curve_id}:values").Set([])

        # Enter through the particle property button so Create and Add use production USD storage.
        await self._open_particle_panel()
        await ui_test.find(f"{self._window.title}//Frame/**/Button[*].text=='Particle Size'").click()
        await ui_test.human_delay()
        popup = _find_editor_window("Particle Size - Curve Editor")
        self.assertIsNotNone(popup)
        self.assertTrue(popup.visible)

        # Isolate an empty channel, create its curve, and add the key whose selection controls Delete.
        await ui_test.find(f"{popup.title}//Frame/**/Label[*].identifier=='CurveTreeChannel::{curve_id}'").click()
        await ui_test.human_delay()
        await ui_test.find(f"{popup.title}//Frame/**/Image[*].identifier=='CurveEditorTreeAdd::{curve_id}'").click()
        await ui_test.human_delay()
        self.assertEqual(list(self._prim.GetAttribute(f"primvars:{curve_id}:times").Get()), [0.0, 1.0])
        await ui_test.find(f"{popup.title}//Frame/**/Button[*].identifier=='CurveEditorBtnAddKey'").click()
        await ui_test.human_delay()
        self.assertEqual(list(self._prim.GetAttribute(f"primvars:{curve_id}:times").Get()), [0.0, 0.5, 1.0])
        self.assertEqual(list(self._prim.GetAttribute(f"primvars:{curve_id}:values").Get()), [0.0, 0.5, 1.0])
        handles = sorted(
            ui_test.find_all(f"{popup.title}//Frame/**/Rectangle[*].name=='FCurveKey'"),
            key=lambda handle: handle.widget.screen_position_x,
        )
        self.assertEqual(len(handles), 3)
        self.assertEqual(handles[0].widget.style["background_color"], handles[2].widget.style["background_color"])
        self.assertNotEqual(handles[1].widget.style["background_color"], handles[0].widget.style["background_color"])
        delete_button = ui_test.find(f"{popup.title}//Frame/**/Button[*].identifier=='CurveEditorBtnDeleteKey'")
        self.assertTrue(delete_button.widget.enabled)
        size_payloads = {
            f"{channel_id}:{suffix}": list(self._prim.GetAttribute(f"{channel_id}:{suffix}").Get())
            for channel_id in PARTICLE_EDIT_GROUPS["size"]["curve_map"]
            for suffix in ("times", "values")
        }

        # Clicking blank canvas clears selection; Delete must preserve visible and hidden data.
        canvas = ui_test.find(f"{popup.title}//Frame/**/Frame[*].identifier=='CurveEditorCanvas'").widget
        await ui_test.input.emulate_mouse_move(
            ui_test.Vec2(
                canvas.screen_position_x + canvas.computed_width * 0.75,
                canvas.screen_position_y + canvas.computed_height * 0.90,
            )
        )
        await ui_test.human_delay()
        await ui_test.emulate_mouse_click()
        await ui_test.human_delay()
        self.assertFalse(delete_button.widget.enabled)
        await delete_button.click()
        await ui_test.human_delay()
        for attribute_name, values in size_payloads.items():
            self.assertEqual(list(self._prim.GetAttribute(attribute_name).Get()), values, attribute_name)
        self.assertEqual(handles[1].widget.style["background_color"], handles[0].widget.style["background_color"])

    async def test_open_particle_curve_groups_selection_preserves_themed_labels_and_curve_colors(self):
        """Resolve every production palette role and retain it while isolating channels."""
        normal_colors = {
            style_name: ui.Style.get_instance().default[f"Label::{style_name}"]["color"]
            for style_name in (
                "CurveEditorChannelX",
                "CurveEditorChannelY",
                "CurveEditorChannelZ",
                "CurveEditorRotationMinimum",
                "CurveEditorRotationMaximum",
            )
        }
        groups = {
            "size": {
                "particle:minSize:x": "CurveEditorChannelX",
                "particle:minSize:y": "CurveEditorChannelY",
                "particle:maxSize:x": "CurveEditorChannelX",
                "particle:maxSize:y": "CurveEditorChannelY",
            },
            "velocity": {
                "particle:maxVelocity:x": "CurveEditorChannelX",
                "particle:maxVelocity:y": "CurveEditorChannelY",
                "particle:maxVelocity:z": "CurveEditorChannelZ",
            },
            "rotationSpeed": {
                "particle:minRotationSpeed": "CurveEditorRotationMinimum",
                "particle:maxRotationSpeed": "CurveEditorRotationMaximum",
            },
        }

        def assert_palette(title: str, channel_styles: dict[str, str], selected: set[str]) -> None:
            """Verify real label states and rendered segment colors after a user action."""
            for curve_id, style_name in channel_styles.items():
                label = ui_test.find(f"{title}//Frame/**/Label[*].identifier=='CurveTreeChannel::{curve_id}'").widget
                self.assertEqual(style_name, label.name)
                self.assertEqual(curve_id in selected, label.selected)
                self.assertEqual(normal_colors[style_name], label.style[f"Label::{style_name}"]["color"])
            segments = ui_test.find_all(f"{title}//Frame/**/FreeBezierCurve[*].name=='FCurveSegment'")
            self.assertCountEqual(
                [normal_colors[channel_styles[curve_id]] for curve_id in selected],
                [segment.widget.style["color"] for segment in segments],
            )

        # Open the same property panel used for a selected particle and reveal its curve buttons.
        await self._open_particle_panel()

        for group_id, channel_styles in groups.items():
            with self.subTest(title=group_id):
                # Clicking a production property button runs its real layout adapter and popup constructor.
                button_text = PARTICLE_EDIT_GROUPS[group_id]["display_name"]
                await ui_test.find(f"{self._window.title}//Frame/**/Button[*].text=='{button_text}'").click()
                await ui_test.human_delay()
                popup = _find_editor_window(f"{button_text} - Curve Editor")
                self.assertIsNotNone(popup)
                self.assertTrue(popup.visible)
                self.assertTrue(popup.title.startswith(f"{button_text} - Curve Editor"))
                assert_palette(popup.title, channel_styles, set(channel_styles))

                # Isolate each channel to prove the selected label and its curve keep the same semantic role.
                for curve_id in channel_styles:
                    await ui_test.find(
                        f"{popup.title}//Frame/**/Label[*].identifier=='CurveTreeChannel::{curve_id}'"
                    ).click()
                    await ui_test.human_delay()
                    assert_palette(popup.title, channel_styles, {curve_id})

                async with ui_test.KeyDownScope(KeyboardInput.ESCAPE):
                    await ui_test.human_delay()
                await ui_test.human_delay()
                self.assertFalse(popup.visible)
