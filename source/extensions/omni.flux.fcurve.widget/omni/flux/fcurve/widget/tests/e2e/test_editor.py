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

Interactive FCurve Editor for manual testing.

This is a dummy editor with toolbar controls for:
- Creating keyframes (to the right of selected keyframe, or after first if none selected)
- Deleting selected keyframes
- Changing in/out tangent types for selected keyframe
- Changing pre/post infinity types for the curve

Usage:
1. Run the test
2. Use the toolbar buttons to manipulate the curve
3. Click "Exit" when done

The wait_for_continue loop is enabled by default for interactive use.
"""

import asyncio
import unittest

import omni.kit.app
import omni.kit.test
from omni import ui

from omni.flux.fcurve.widget import FCurveWidget, FCurve, FCurveKey, TangentType, InfinityType

__all__ = ["TestEditor"]


# Window dimensions (match other e2e tests for consistent pixel calibration)
WINDOW_WIDTH = 500
WINDOW_HEIGHT = 400
CURVE_WIDTH = 400
CURVE_HEIGHT = 280
PADDING = 30
TOOLBAR_HEIGHT = 40
STATUS_HEIGHT = 30

# Tangent types in order
TANGENT_TYPES = [
    TangentType.FLAT,
    TangentType.STEP,
    TangentType.LINEAR,
    TangentType.AUTO,
    TangentType.SMOOTH,
    TangentType.CUSTOM,
]

# Infinity types (only supported ones)
INFINITY_TYPES = [
    InfinityType.CONSTANT,
    InfinityType.LINEAR,
]

# Button styling
BUTTON_STYLE = {
    "Button": {
        "background_color": 0xFF3A3A3A,
        "border_radius": 4,
        "padding": 6,
    },
    "Button:hovered": {
        "background_color": 0xFF4A4A4A,
    },
    "Button:pressed": {
        "background_color": 0xFF2A2A2A,
    },
}

ACTIVE_BUTTON_STYLE = {
    "Button": {
        "background_color": 0xFF2266AA,
        "border_radius": 4,
        "padding": 6,
    },
    "Button:hovered": {
        "background_color": 0xFF3377BB,
    },
    "Button:pressed": {
        "background_color": 0xFF1155AA,
    },
}

COMBOBOX_STYLE = {
    "ComboBox": {
        "background_color": 0xFF3A3A3A,
        "border_radius": 4,
        "padding": 4,
        "font_size": 14,
    },
}

LABEL_STYLE = {
    "font_size": 14,
    "color": 0xFFAAAAAA,
}


@unittest.skip("Interactive sandbox — run manually, not in CI")
class TestEditor(omni.kit.test.AsyncTestCase):
    """Interactive FCurve editor for manual testing."""

    async def setUp(self):
        """Create window with FCurveWidget and toolbar."""
        self._exit_clicked = False
        self._curve_id = "test"
        self._updating_ui = False  # Flag to prevent callback loops
        self._selection_subscription = None  # Will hold the subscription reference

        self.window = ui.Window(
            "FCurve Editor",
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
        )

        with self.window.frame:
            with ui.VStack(spacing=4):
                # ─────────────────────────────────────────────────────────────
                # Toolbar Row 1: Keyframe operations and tangent types
                # ─────────────────────────────────────────────────────────────
                with ui.HStack(height=ui.Pixel(TOOLBAR_HEIGHT), spacing=8):
                    ui.Spacer(width=10)

                    # Keyframe operations
                    ui.Label("Keys:", style=LABEL_STYLE, width=40)
                    ui.Button(
                        "Add Key",
                        width=80,
                        clicked_fn=self._on_add_key,
                        style=BUTTON_STYLE,
                        tooltip="Add keyframe to the right of selection (or after first key)",
                    )
                    ui.Button(
                        "Delete",
                        width=60,
                        clicked_fn=self._on_delete_key,
                        style=BUTTON_STYLE,
                        tooltip="Delete selected keyframes",
                    )

                    ui.Spacer(width=30)

                    # In tangent type combo box
                    ui.Label("In Tangent:", style=LABEL_STYLE, width=80)
                    self._in_tangent_combo = ui.ComboBox(
                        0,  # Initial index
                        *[tt.name for tt in TANGENT_TYPES],
                        width=120,
                        style=COMBOBOX_STYLE,
                        tooltip="Set in-tangent type for selected keyframe",
                    )
                    self._in_tangent_combo.model.add_item_changed_fn(self._on_in_tangent_changed)

                    ui.Spacer(width=20)

                    # Out tangent type combo box
                    ui.Label("Out Tangent:", style=LABEL_STYLE, width=90)
                    self._out_tangent_combo = ui.ComboBox(
                        0,  # Initial index
                        *[tt.name for tt in TANGENT_TYPES],
                        width=120,
                        style=COMBOBOX_STYLE,
                        tooltip="Set out-tangent type for selected keyframe",
                    )
                    self._out_tangent_combo.model.add_item_changed_fn(self._on_out_tangent_changed)

                    ui.Spacer()

                # ─────────────────────────────────────────────────────────────
                # Toolbar Row 2: Infinity and exit
                # ─────────────────────────────────────────────────────────────
                with ui.HStack(height=ui.Pixel(TOOLBAR_HEIGHT), spacing=8):
                    ui.Spacer(width=10)

                    # Pre-infinity
                    ui.Label("Pre-Infinity:", style=LABEL_STYLE, width=80)
                    self._pre_infinity_buttons = {}
                    for it in INFINITY_TYPES:
                        btn = ui.Button(
                            it.name,
                            width=90,
                            clicked_fn=lambda t=it: self._on_set_pre_infinity(t),
                            style=BUTTON_STYLE,
                            tooltip=f"Set pre-infinity to {it.name}",
                        )
                        self._pre_infinity_buttons[it] = btn

                    ui.Spacer(width=30)

                    # Post-infinity
                    ui.Label("Post-Infinity:", style=LABEL_STYLE, width=90)
                    self._post_infinity_buttons = {}
                    for it in INFINITY_TYPES:
                        btn = ui.Button(
                            it.name,
                            width=90,
                            clicked_fn=lambda t=it: self._on_set_post_infinity(t),
                            style=BUTTON_STYLE,
                            tooltip=f"Set post-infinity to {it.name}",
                        )
                        self._post_infinity_buttons[it] = btn

                    ui.Spacer(width=30)

                    # Break / Mirror tangent
                    ui.Label("Tangents:", style=LABEL_STYLE, width=60)
                    self._break_btn = ui.Button(
                        "Break",
                        width=70,
                        clicked_fn=self._on_break_tangent,
                        style=BUTTON_STYLE,
                        tooltip="Break tangents (independent in/out angles)",
                    )
                    self._mirror_btn = ui.Button(
                        "Mirror",
                        width=70,
                        clicked_fn=self._on_mirror_tangent,
                        style=BUTTON_STYLE,
                        tooltip="Mirror tangents (linked in/out angles)",
                    )

                    ui.Spacer()

                    # Exit button
                    ui.Button(
                        "Exit",
                        width=80,
                        clicked_fn=self._on_exit_clicked,
                        style={
                            "Button": {
                                "background_color": 0xFF2222AA,
                                "border_radius": 4,
                                "padding": 6,
                            },
                            "Button:hovered": {
                                "background_color": 0xFF3333BB,
                            },
                        },
                        tooltip="Exit the editor",
                    )
                    ui.Spacer(width=10)

                # ─────────────────────────────────────────────────────────────
                # Curve area
                # ─────────────────────────────────────────────────────────────
                with ui.HStack():
                    ui.Spacer(width=PADDING)
                    with ui.ZStack(
                        width=ui.Pixel(CURVE_WIDTH),
                        height=ui.Pixel(CURVE_HEIGHT),
                    ):
                        ui.Rectangle(style={"background_color": 0xFF1A1A1A})
                        self._canvas_frame = ui.CanvasFrame(
                            width=CURVE_WIDTH,
                            height=CURVE_HEIGHT,
                            style={"background_color": 0x0},
                        )
                        with self._canvas_frame:
                            self.widget = FCurveWidget(
                                time_range=(0.0, 1.0),
                                value_range=(0.0, 1.0),
                            )
                        self._canvas_frame.set_zoom_changed_fn(lambda z: self.widget.set_zoom(z))
                        self._canvas_frame.set_computed_content_size_changed_fn(self._on_canvas_size_changed)
                    ui.Spacer(width=PADDING)

                # ─────────────────────────────────────────────────────────────
                # Status bar
                # ─────────────────────────────────────────────────────────────
                with ui.HStack(height=ui.Pixel(STATUS_HEIGHT)):
                    ui.Spacer(width=10)
                    self._status_label = ui.Label(
                        "Ready. Select a keyframe to edit tangents.",
                        style={"font_size": 12, "color": 0xFF888888},
                    )
                    ui.Spacer()

                ui.Spacer(height=10)

        await omni.kit.app.get_app().next_update_async()

        # Set up initial curve
        self._setup_initial_curve()

        # Let layout settle so computed_content_size callback fires
        await omni.kit.app.get_app().next_update_async()

        # Subscribe to selection changes (keep reference to prevent garbage collection)
        self._selection_subscription = self.widget.subscribe_selection_changed(self._on_selection_changed)

        # Update UI state
        self._update_ui_state()

    def _setup_initial_curve(self):
        """Create initial curve with a few keyframes."""
        self.widget.set_curves(
            {
                self._curve_id: FCurve(
                    id=self._curve_id,
                    keys=[
                        FCurveKey(
                            time=0.0,
                            value=0.3,
                            out_tangent_type=TangentType.LINEAR,
                        ),
                        FCurveKey(
                            time=0.3,
                            value=0.7,
                            in_tangent_type=TangentType.LINEAR,
                            out_tangent_type=TangentType.LINEAR,
                        ),
                        FCurveKey(
                            time=0.7,
                            value=0.4,
                            in_tangent_type=TangentType.LINEAR,
                            out_tangent_type=TangentType.LINEAR,
                        ),
                        FCurveKey(
                            time=1.0,
                            value=0.6,
                            in_tangent_type=TangentType.LINEAR,
                        ),
                    ],
                    color=0xFF00FF00,  # Green (ABGR)
                    pre_infinity=InfinityType.LINEAR,
                    post_infinity=InfinityType.LINEAR,
                )
            }
        )

    def _on_canvas_size_changed(self):
        if self._canvas_frame and self.widget:
            w = self._canvas_frame.computed_content_width
            h = self._canvas_frame.computed_content_height
            if w > 0 and h > 0:
                self.widget.set_viewport_size(w, h)

    def _on_exit_clicked(self):
        """Handle exit button click."""
        self._exit_clicked = True

    def _on_selection_changed(self, event):
        """Handle selection change to update UI state."""
        self._update_ui_state()

    def _update_ui_state(self):
        """Update combo boxes and buttons based on current selection."""
        self._updating_ui = True  # Prevent callback loops
        try:
            selected = self.widget.selected_keys
            curve = self._get_curve()

            if not selected or not curve:
                self._status_label.text = "No keyframe selected. Click a keyframe to select it."
                # Reset combo boxes to first item (or leave as-is)
            else:
                # Get first selected key's tangent types
                key_ref = selected[0]
                if key_ref.key_index < len(curve.keys):
                    key = curve.keys[key_ref.key_index]
                    broken_str = "broken" if key.tangent_broken else "mirrored"
                    self._status_label.text = (
                        f"Key {key_ref.key_index}: time={key.time:.2f}, value={key.value:.2f} | "
                        f"In: {key.in_tangent_type.name}, Out: {key.out_tangent_type.name} | {broken_str}"
                    )

                    # Update combo box selections to match selected key
                    in_idx = TANGENT_TYPES.index(key.in_tangent_type) if key.in_tangent_type in TANGENT_TYPES else 0
                    out_idx = TANGENT_TYPES.index(key.out_tangent_type) if key.out_tangent_type in TANGENT_TYPES else 0

                    # Set combo box model values
                    in_model = self._in_tangent_combo.model
                    out_model = self._out_tangent_combo.model
                    in_model.get_item_value_model().set_value(in_idx)
                    out_model.get_item_value_model().set_value(out_idx)

            # Highlight active break/mirror button
            if selected and curve:
                key_ref = selected[0]
                if key_ref.key_index < len(curve.keys):
                    broken = curve.keys[key_ref.key_index].tangent_broken
                    self._break_btn.style = ACTIVE_BUTTON_STYLE if broken else BUTTON_STYLE
                    self._mirror_btn.style = ACTIVE_BUTTON_STYLE if not broken else BUTTON_STYLE
            else:
                self._break_btn.style = BUTTON_STYLE
                self._mirror_btn.style = BUTTON_STYLE

            # Highlight active infinity type buttons
            if curve:
                for it, btn in self._pre_infinity_buttons.items():
                    btn.style = ACTIVE_BUTTON_STYLE if it == curve.pre_infinity else BUTTON_STYLE
                for it, btn in self._post_infinity_buttons.items():
                    btn.style = ACTIVE_BUTTON_STYLE if it == curve.post_infinity else BUTTON_STYLE
        finally:
            self._updating_ui = False

    def _get_curve(self):
        """Get the current curve data using public API."""
        curves = self.widget.curves
        return curves.get(self._curve_id)

    def _on_add_key(self):
        """Add a keyframe to the right of the selected key (or after first key)."""
        curve = self._get_curve()
        if not curve or len(curve.keys) == 0:
            return

        selected = self.widget.selected_keys

        # Default values
        new_time = 0.5
        new_value = 0.5

        if selected:
            # Add after the first selected key
            key_ref = selected[0]
            if key_ref.key_index < len(curve.keys):
                ref_key = curve.keys[key_ref.key_index]
                # Find the next key's time (or use 0.1 offset if last key)
                if key_ref.key_index + 1 < len(curve.keys):
                    next_key = curve.keys[key_ref.key_index + 1]
                    new_time = (ref_key.time + next_key.time) / 2
                    new_value = (ref_key.value + next_key.value) / 2
                else:
                    # Last key - add 0.1 offset (clamped to bounds)
                    new_time = min(ref_key.time + 0.1, 1.0)
                    new_value = ref_key.value
        # No selection - add after first key
        elif len(curve.keys) >= 2:
            key0 = curve.keys[0]
            key1 = curve.keys[1]
            new_time = (key0.time + key1.time) / 2
            new_value = (key0.value + key1.value) / 2

        self.widget.add_key(self._curve_id, new_time, new_value)
        self._status_label.text = f"Added keyframe at time={new_time:.2f}, value={new_value:.2f}"
        self._update_ui_state()

    def _on_delete_key(self):
        """Delete selected keyframes."""
        deleted = self.widget.delete_selected_keys()
        if deleted > 0:
            self._status_label.text = f"Deleted {deleted} keyframe(s)"
        else:
            self._status_label.text = "No keyframes to delete (select a keyframe first)"
        self._update_ui_state()

    def _on_in_tangent_changed(self, model, item):
        """Handle in-tangent combo box selection change."""
        if self._updating_ui:
            return  # Ignore changes triggered by UI updates

        selected = self.widget.selected_keys
        if not selected:
            self._status_label.text = "Select a keyframe first"
            return

        idx = model.get_item_value_model().get_value_as_int()
        if 0 <= idx < len(TANGENT_TYPES):
            tangent_type = TANGENT_TYPES[idx]
            for key_ref in selected:
                self.widget.set_key_tangent_type(
                    key_ref.curve_id,
                    key_ref.key_index,
                    in_tangent_type=tangent_type,
                )
            self._status_label.text = f"Set in-tangent to {tangent_type.name}"
            self._update_ui_state()

    def _on_out_tangent_changed(self, model, item):
        """Handle out-tangent combo box selection change."""
        if self._updating_ui:
            return  # Ignore changes triggered by UI updates

        selected = self.widget.selected_keys
        if not selected:
            self._status_label.text = "Select a keyframe first"
            return

        idx = model.get_item_value_model().get_value_as_int()
        if 0 <= idx < len(TANGENT_TYPES):
            tangent_type = TANGENT_TYPES[idx]
            for key_ref in selected:
                self.widget.set_key_tangent_type(
                    key_ref.curve_id,
                    key_ref.key_index,
                    out_tangent_type=tangent_type,
                )
            self._status_label.text = f"Set out-tangent to {tangent_type.name}"
            self._update_ui_state()

    def _on_set_pre_infinity(self, infinity_type: InfinityType):
        """Set the pre-infinity type for the curve."""
        self.widget.set_curve_infinity(self._curve_id, pre_infinity=infinity_type)
        self._status_label.text = f"Set pre-infinity to {infinity_type.name}"
        self._update_ui_state()

    def _on_set_post_infinity(self, infinity_type: InfinityType):
        """Set the post-infinity type for the curve."""
        self.widget.set_curve_infinity(self._curve_id, post_infinity=infinity_type)
        self._status_label.text = f"Set post-infinity to {infinity_type.name}"
        self._update_ui_state()

    def _on_break_tangent(self):
        count = self.widget.set_selected_keys_tangent_broken(True)
        if count:
            self._status_label.text = f"Broke tangents on {count} key(s)"
        else:
            self._status_label.text = "Select a keyframe first"
        self._update_ui_state()

    def _on_mirror_tangent(self):
        count = self.widget.set_selected_keys_tangent_broken(False, source="out")
        if count:
            self._status_label.text = f"Mirrored tangents on {count} key(s)"
        else:
            self._status_label.text = "Select a keyframe first"
        self._update_ui_state()

    def _print_curve(self, label: str = "CURVE STATE"):
        """
        Print all curve data for test case generation.

        Prints keyframes, tangent types, handle positions, infinity types, etc.
        in a format that can be used to create test cases.
        """
        curve = self._get_curve()
        if not curve:
            print(f"\n{'=' * 60}")
            print(f"{label}: No curve found")
            print(f"{'=' * 60}\n")
            return

        print(f"\n{'=' * 60}")
        print(f"{label}")
        print(f"{'=' * 60}")
        print(f"Curve ID: {curve.id}")
        print(f"Color: 0x{curve.color:08X}")
        print(f"Pre-Infinity: {curve.pre_infinity.name} ({curve.pre_infinity.value})")
        print(f"Post-Infinity: {curve.post_infinity.name} ({curve.post_infinity.value})")
        print(f"Visible: {curve.visible}")
        print(f"Locked: {curve.locked}")
        print(f"Number of Keys: {len(curve.keys)}")
        print()

        for i, key in enumerate(curve.keys):
            print(f"  Key [{i}]:")
            print(f"    Position: time={key.time:.6f}, value={key.value:.6f}")
            print("    In Tangent:")
            print(f"      Type: {key.in_tangent_type.name}")
            print(f"      Offset: x={key.in_tangent_x:.6f}, y={key.in_tangent_y:.6f}")
            print(f"      Handle Position: ({key.time + key.in_tangent_x:.6f}, {key.value + key.in_tangent_y:.6f})")
            print("    Out Tangent:")
            print(f"      Type: {key.out_tangent_type.name}")
            print(f"      Offset: x={key.out_tangent_x:.6f}, y={key.out_tangent_y:.6f}")
            print(f"      Handle Position: ({key.time + key.out_tangent_x:.6f}, {key.value + key.out_tangent_y:.6f})")
            print(f"    Tangent Broken: {key.tangent_broken}")
            print()

        # Print in a copy-pasteable format for test cases
        print("-" * 60)
        print("COPY-PASTE FORMAT FOR TEST CASES:")
        print("-" * 60)
        print("FCurve(")
        print(f'    id="{curve.id}",')
        print("    keys=[")
        for i, key in enumerate(curve.keys):
            print("        FCurveKey(")
            print(f"            time={key.time}, value={key.value},")
            print(f"            in_tangent_type=TangentType.{key.in_tangent_type.name},")
            print(f"            in_tangent_x={key.in_tangent_x}, in_tangent_y={key.in_tangent_y},")
            print(f"            out_tangent_type=TangentType.{key.out_tangent_type.name},")
            print(f"            out_tangent_x={key.out_tangent_x}, out_tangent_y={key.out_tangent_y},")
            print(f"            tangent_broken={key.tangent_broken},")
            comma = "," if i < len(curve.keys) - 1 else ""
            print(f"        ){comma}")
        print("    ],")
        print(f"    color=0x{curve.color:08X},")
        print(f"    pre_infinity=InfinityType.{curve.pre_infinity.name},")
        print(f"    post_infinity=InfinityType.{curve.post_infinity.name},")
        print(")")
        print(f"{'=' * 60}\n")

    async def _wait_for_exit(self):
        """Wait for the exit button to be clicked."""
        self._exit_clicked = False
        while not self._exit_clicked:
            await asyncio.sleep(0.1)

    async def tearDown(self):
        self._selection_subscription = None
        if self.widget:
            self.widget.destroy()
            self.widget = None
        self._canvas_frame = None
        if self.window:
            self.window.destroy()
            self.window = None

    # =========================================================================
    # Test: Interactive Editor
    # =========================================================================
    async def test_interactive_editor(self):
        """
        Interactive FCurve editor for manual testing.

        This test opens an interactive editor window and waits for the user
        to click the Exit button. Use this for:
        - Manual testing of tangent behaviors
        - Debugging curve rendering issues
        - Exploring the widget API

        Instructions:
        1. Click keyframes to select them
        2. Use combo boxes to modify tangent types
        3. Use Add Key / Delete buttons to manage keyframes
        4. Use infinity buttons to change extrapolation modes
        5. Click Exit when done

        The curve state is printed to console at start and after Exit,
        allowing you to capture before/after states for test cases.
        """
        # Print initial state
        self._print_curve("INITIAL STATE (before interaction)")

        self._status_label.text = "Interactive editor ready. Click Exit to end test."

        # Wait for user to exit
        await self._wait_for_exit()

        # Print final state (after user interactions)
        self._print_curve("FINAL STATE (after interaction)")

        # If we get here, the test passed
        self.assertTrue(True, "Editor exited successfully")
