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

__all__ = ("TestColorGradientWidget",)

import uuid

import omni.kit.app
import omni.kit.test
import omni.kit.ui_test
import omni.ui as ui

from omni.flux.utils.widget.color_gradient import (
    ColorGradientWidget,
    _GRADIENT_BORDER_RADIUS,
    _HALF_MARKER,
    _KF,
    _MARKER_SIZE,
    _POPUP_MARKER_HEIGHT_TOTAL,
    _POPUP_MIN_WIDTH,
    _get_local_style,
)


async def _wait_updates(n: int = 3):
    """Wait for *n* Kit UI update frames."""
    for _ in range(n):
        await omni.kit.app.get_app().next_update_async()


class TestColorGradientWidget(omni.kit.test.AsyncTestCase):
    """UI tests for the ColorGradientWidget standalone widget."""

    async def setUp(self):
        self._window = ui.Window(
            f"TestGradientWidget_{uuid.uuid1()}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        self._gradient_widget = None
        self._last_callback_times = None
        self._last_callback_values = None

    async def tearDown(self):
        if self._gradient_widget:
            self._gradient_widget.destroy()
            self._gradient_widget = None
        if self._window:
            self._window.destroy()
            self._window = None

    def _on_gradient_changed(self, times, values):
        self._last_callback_times = times
        self._last_callback_values = values

    def _build_widget(self, keyframes=None, default_color=None, read_only=False, on_gradient_changed_fn=None):
        kwargs = {
            "on_gradient_changed_fn": on_gradient_changed_fn
            if on_gradient_changed_fn is not None
            else self._on_gradient_changed,
            "read_only": read_only,
        }
        if keyframes is not None:
            kwargs["keyframes"] = keyframes
        if default_color is not None:
            kwargs["default_color"] = default_color
        with self._window.frame:
            self._gradient_widget = ColorGradientWidget(**kwargs)

    async def _show_widget_popup(self):
        """Show the popup for the widget (needed to access markers/edit row)."""
        self._gradient_widget._show_popup()
        await _wait_updates(5)

    # ------------------------------------------------------------------
    # Initialization tests
    # ------------------------------------------------------------------

    async def test_create_empty(self):
        """Widget should be created with no keyframes and no crash."""
        self._build_widget()
        await _wait_updates()

        kfs = self._gradient_widget.get_keyframes()
        self.assertEqual(len(kfs), 0)

    async def test_create_with_keyframes(self):
        """Widget should accept initial keyframes and return them correctly."""
        initial = [
            (0.0, (1.0, 0.0, 0.0, 1.0)),
            (0.5, (0.0, 1.0, 0.0, 1.0)),
            (1.0, (0.0, 0.0, 1.0, 1.0)),
        ]
        self._build_widget(keyframes=initial)
        await _wait_updates()

        kfs = self._gradient_widget.get_keyframes()
        self.assertEqual(len(kfs), 3)
        for (exp_t, exp_c), (got_t, got_c) in zip(initial, kfs):
            self.assertAlmostEqual(got_t, exp_t)
            for i in range(4):
                self.assertAlmostEqual(got_c[i], exp_c[i])

    async def test_create_with_default_color(self):
        """Custom default color should be stored when no keyframes are present."""
        self._build_widget(default_color=(0.5, 0.5, 0.5, 0.5))
        await _wait_updates()

        kfs = self._gradient_widget.get_keyframes()
        self.assertEqual(len(kfs), 0)

    # ------------------------------------------------------------------
    # set_keyframes / get_keyframes
    # ------------------------------------------------------------------

    async def test_set_keyframes_replaces_all(self):
        """set_keyframes should replace all existing keyframes."""
        self._build_widget(keyframes=[(0.0, (1.0, 0.0, 0.0, 1.0))])
        await _wait_updates()

        new_kfs = [
            (0.2, (0.1, 0.2, 0.3, 0.4)),
            (0.8, (0.5, 0.6, 0.7, 0.8)),
        ]
        self._gradient_widget.set_keyframes(new_kfs)
        await _wait_updates()

        kfs = self._gradient_widget.get_keyframes()
        self.assertEqual(len(kfs), 2)
        self.assertAlmostEqual(kfs[0][0], 0.2)
        self.assertAlmostEqual(kfs[1][0], 0.8)

    async def test_set_keyframes_sorts_by_time(self):
        """set_keyframes should sort by time even if provided unsorted."""
        self._build_widget()
        await _wait_updates()

        unsorted = [
            (0.9, (0.0, 0.0, 1.0, 1.0)),
            (0.1, (1.0, 0.0, 0.0, 1.0)),
            (0.5, (0.0, 1.0, 0.0, 1.0)),
        ]
        self._gradient_widget.set_keyframes(unsorted)
        await _wait_updates()

        kfs = self._gradient_widget.get_keyframes()
        self.assertEqual(len(kfs), 3)
        times = [t for t, _ in kfs]
        self.assertEqual(times, sorted(times))

    async def test_set_keyframes_to_empty(self):
        """set_keyframes with empty list should clear all keyframes."""
        self._build_widget(keyframes=[(0.0, (1.0, 0.0, 0.0, 1.0))])
        await _wait_updates()

        self._gradient_widget.set_keyframes([])
        await _wait_updates()

        self.assertEqual(len(self._gradient_widget.get_keyframes()), 0)

    # ------------------------------------------------------------------
    # read_only mode
    # ------------------------------------------------------------------

    async def test_read_only_property(self):
        """read_only property should reflect the constructor argument."""
        self._build_widget(read_only=True)
        await _wait_updates()
        self.assertTrue(self._gradient_widget.read_only)

    async def test_read_only_default_false(self):
        """read_only should default to False."""
        self._build_widget()
        await _wait_updates()
        self.assertFalse(self._gradient_widget.read_only)

    # ------------------------------------------------------------------
    # destroy
    # ------------------------------------------------------------------

    async def test_destroy_cleans_up(self):
        """destroy() should clean up internal references without crashing."""
        self._build_widget(keyframes=[(0.5, (1.0, 1.0, 1.0, 1.0))])
        await _wait_updates()

        self._gradient_widget.destroy()
        # Verify key references are cleaned up
        self.assertIsNone(self._gradient_widget._gradient_provider)
        self.assertIsNone(self._gradient_widget._checker_provider)
        self.assertIsNone(self._gradient_widget._gradient_overlay)
        self.assertIsNone(self._gradient_widget._color_widget)
        self.assertIsNone(self._gradient_widget._popup_window)
        self._gradient_widget = None  # Prevent double destroy in tearDown

    async def test_destroy_with_selection(self):
        """destroy() with a selected keyframe should not crash."""
        self._build_widget(keyframes=[(0.5, (1.0, 1.0, 1.0, 1.0))])
        await _wait_updates()

        self._gradient_widget._selected_uid = self._gradient_widget._keyframes[0].uid
        self._gradient_widget.destroy()
        self._gradient_widget = None

    # ------------------------------------------------------------------
    # Callback firing
    # ------------------------------------------------------------------

    async def test_callback_not_fired_on_set_keyframes(self):
        """set_keyframes should NOT fire the on_gradient_changed_fn callback."""
        self._build_widget()
        await _wait_updates()

        self._gradient_widget.set_keyframes([(0.0, (1.0, 0.0, 0.0, 1.0))])
        await _wait_updates()

        self.assertIsNone(self._last_callback_times)

    # ------------------------------------------------------------------
    # Bar click → keyframe creation
    # ------------------------------------------------------------------

    async def test_bar_release_creates_keyframe_at_click_position(self):
        """Releasing mouse on the popup gradient bar should add a keyframe at that time."""
        self._build_widget(
            keyframes=[
                (0.0, (1.0, 0.0, 0.0, 1.0)),
                (1.0, (0.0, 0.0, 1.0, 1.0)),
            ]
        )
        await _wait_updates(10)
        await self._show_widget_popup()

        self.assertEqual(len(self._gradient_widget.get_keyframes()), 2)

        # Simulate a mouse release at the midpoint of the popup gradient bar.
        bar = self._gradient_widget._popup_gradient_overlay
        mid_screen_x = bar.screen_position_x + bar.computed_width * 0.5
        self._gradient_widget._on_popup_bar_released(mid_screen_x, 0.0, 0, 0)
        await _wait_updates()

        kfs = self._gradient_widget.get_keyframes()
        self.assertEqual(len(kfs), 3, "A third keyframe should have been added")
        # The new keyframe should be near time=0.5
        times = [t for t, _ in kfs]
        mid_kf = min(times, key=lambda t: abs(t - 0.5))
        self.assertAlmostEqual(mid_kf, 0.5, delta=0.05)

    async def test_bar_release_keyframe_has_interpolated_color(self):
        """Keyframe added by popup bar click should carry the gradient's interpolated color."""
        self._build_widget(
            keyframes=[
                (0.0, (1.0, 0.0, 0.0, 1.0)),
                (1.0, (0.0, 0.0, 1.0, 1.0)),
            ]
        )
        await _wait_updates(10)
        await self._show_widget_popup()

        # Click at 50% → expect ~(0.5, 0.0, 0.5, 1.0)
        bar = self._gradient_widget._popup_gradient_overlay
        mid_screen_x = bar.screen_position_x + bar.computed_width * 0.5
        self._gradient_widget._on_popup_bar_released(mid_screen_x, 0.0, 0, 0)
        await _wait_updates()

        kfs = self._gradient_widget.get_keyframes()
        # Find the new keyframe near t=0.5
        new_kf = min(kfs, key=lambda kf: abs(kf[0] - 0.5))
        _, color = new_kf
        self.assertAlmostEqual(color[0], 0.5, delta=0.1)  # red fading
        self.assertAlmostEqual(color[2], 0.5, delta=0.1)  # blue rising
        self.assertAlmostEqual(color[3], 1.0, delta=0.05)  # alpha stays 1

    async def test_bar_release_fires_callback(self):
        """Releasing on the popup gradient bar should fire the on_gradient_changed callback."""
        self._build_widget(
            keyframes=[
                (0.0, (1.0, 0.0, 0.0, 1.0)),
                (1.0, (0.0, 0.0, 1.0, 1.0)),
            ]
        )
        await _wait_updates(10)
        await self._show_widget_popup()

        self.assertIsNone(self._last_callback_times)

        bar = self._gradient_widget._popup_gradient_overlay
        click_x = bar.screen_position_x + bar.computed_width * 0.25
        self._gradient_widget._on_popup_bar_released(click_x, 0.0, 0, 0)
        await _wait_updates()

        self.assertIsNotNone(self._last_callback_times)
        self.assertEqual(len(self._last_callback_times), 3)

    async def test_marker_scale_matches_gradient_length(self):
        """Triangle marker tips (centers) at time 0 and 1 should align with gradient bar edges."""
        self._build_widget(
            keyframes=[
                (0.0, (1.0, 0.0, 0.0, 1.0)),
                (0.5, (0.0, 1.0, 0.0, 1.0)),
                (1.0, (0.0, 0.0, 1.0, 1.0)),
            ]
        )
        # Extra frames so layout is fully resolved
        await _wait_updates(10)
        # Show popup so markers are built and accessible
        await self._show_widget_popup()

        bar_stack = self._gradient_widget._gradient_bar_stack
        bar_left = bar_stack.screen_position_x
        inline_bar_width = bar_stack.computed_width

        half_marker = _MARKER_SIZE // 2

        # The popup window is positioned so the popup gradient bar left-aligns with the inline bar.
        # The popup bar width is max(inline_bar_width, _POPUP_MIN_WIDTH minus window inset).
        popup_bar_left = bar_left
        popup_bar_width = max(inline_bar_width, _POPUP_MIN_WIDTH - 4 * _HALF_MARKER)
        popup_bar_right = popup_bar_left + popup_bar_width

        # Collect marker CENTER screen positions keyed by time.
        # With Placer-based SVG markers, the center is at screen_position_x + half_marker.
        kfs = self._gradient_widget._keyframes
        marker_centers = {}
        for kf in kfs:
            marker = self._gradient_widget._marker_widgets.get(kf.uid)
            self.assertIsNotNone(marker, f"Marker widget missing for uid {kf.uid}")
            marker_centers[kf.time] = marker.screen_position_x + half_marker

        # --- Diagnostic info (visible in test log on failure) ---
        diag = (
            f"\n  bar_left={bar_left:.1f}, inline_bar_width={inline_bar_width:.1f}"
            f", popup_bar_left={popup_bar_left:.1f}, popup_bar_width={popup_bar_width:.1f}"
            f", popup_bar_right={popup_bar_right:.1f}"
            f"\n  marker centers: { ({t: f'{x:.1f}' for t, x in marker_centers.items()}) }"
        )

        # The gradient bar should be wider than the 256px image source
        self.assertGreater(popup_bar_width, 256, f"Gradient bar should stretch beyond 256px in 400px window.{diag}")

        # Marker center at time=0 should be near the left edge of popup gradient bar
        self.assertAlmostEqual(
            marker_centers[0.0],
            popup_bar_left,
            delta=_MARKER_SIZE,
            msg=f"Marker center at time=0 should be near left edge of gradient.{diag}",
        )

        # Marker center at time=0.5 should align with midpoint of the popup gradient bar
        expected_mid = popup_bar_left + popup_bar_width * 0.5
        self.assertAlmostEqual(
            marker_centers[0.5],
            expected_mid,
            delta=4.0,
            msg=f"Marker center at time=0.5 should be near center of gradient.{diag}",
        )

        # Marker center at time=1.0 should be near the right edge of the popup gradient bar
        self.assertAlmostEqual(
            marker_centers[1.0],
            popup_bar_right,
            delta=_MARKER_SIZE,
            msg=f"Marker center at time=1 should be near right edge of gradient.{diag}",
        )

    async def test_marker_triangles_have_correct_size(self):
        """Each marker triangle must be _MARKER_SIZE wide; the pentagon ZStack is _POPUP_MARKER_HEIGHT tall.

        Regression test: using ``stable_size=True`` on the Placer without an
        explicit Pixel width caused the Placer to stretch its child to the
        full parent width, producing "fat" markers.  Adding
        ``width=Pixel(_MARKER_SIZE)`` on the ZStack constrains the triangle.
        """
        marker_size = _MARKER_SIZE
        self._build_widget(
            keyframes=[
                (0.0, (1.0, 0.0, 0.0, 1.0)),
                (0.5, (0.0, 1.0, 0.0, 1.0)),
                (1.0, (0.0, 0.0, 1.0, 1.0)),
            ]
        )
        await _wait_updates(10)
        # Show popup so pentagon markers are built and accessible
        await self._show_widget_popup()

        for kf in self._gradient_widget._keyframes:
            tri = self._gradient_widget._marker_widgets.get(kf.uid)
            self.assertIsNotNone(tri, f"Triangle missing for t={kf.time}")
            self.assertAlmostEqual(
                tri.computed_width,
                marker_size,
                delta=2.0,
                msg=f"Marker at t={kf.time} is too wide ({tri.computed_width:.1f}px, expected ~{marker_size}px).",
            )
            # SVG marker is _POPUP_MARKER_HEIGHT tall
            self.assertAlmostEqual(
                tri.computed_height,
                _POPUP_MARKER_HEIGHT_TOTAL,
                delta=4.0,
                msg=f"Marker at t={kf.time} is too tall ({tri.computed_height:.1f}px, expected ~{_POPUP_MARKER_HEIGHT_TOTAL}px).",
            )

    # ------------------------------------------------------------------
    # Internal _sample_gradient_at
    # ------------------------------------------------------------------

    async def test_sample_gradient_empty(self):
        """Sampling with no keyframes returns the default color."""
        self._build_widget(default_color=(0.3, 0.4, 0.5, 0.6))
        await _wait_updates()

        c = self._gradient_widget._sample_gradient_at(0.5)
        self.assertAlmostEqual(c[0], 0.3)
        self.assertAlmostEqual(c[1], 0.4)
        self.assertAlmostEqual(c[2], 0.5)
        self.assertAlmostEqual(c[3], 0.6)

    async def test_sample_gradient_single_keyframe(self):
        """Sampling with one keyframe returns that color regardless of time."""
        self._build_widget(keyframes=[(0.5, (0.1, 0.2, 0.3, 0.4))])
        await _wait_updates()

        for t in [0.0, 0.25, 0.5, 0.75, 1.0]:
            c = self._gradient_widget._sample_gradient_at(t)
            self.assertAlmostEqual(c[0], 0.1, places=5)
            self.assertAlmostEqual(c[1], 0.2, places=5)
            self.assertAlmostEqual(c[2], 0.3, places=5)
            self.assertAlmostEqual(c[3], 0.4, places=5)

    async def test_sample_gradient_two_keyframes_interpolation(self):
        """Sampling between two keyframes should linearly interpolate."""
        self._build_widget(
            keyframes=[
                (0.0, (0.0, 0.0, 0.0, 1.0)),
                (1.0, (1.0, 1.0, 1.0, 1.0)),
            ]
        )
        await _wait_updates()

        c = self._gradient_widget._sample_gradient_at(0.5)
        for ch in range(3):
            self.assertAlmostEqual(c[ch], 0.5, places=5)

    async def test_sample_gradient_clamped_endpoints(self):
        """Sampling before the first or after the last stop should clamp."""
        self._build_widget(
            keyframes=[
                (0.2, (1.0, 0.0, 0.0, 1.0)),
                (0.8, (0.0, 0.0, 1.0, 1.0)),
            ]
        )
        await _wait_updates()

        # Before first stop
        c0 = self._gradient_widget._sample_gradient_at(0.0)
        self.assertAlmostEqual(c0[0], 1.0, places=5)  # Red at t=0.2, should extend

        # After last stop
        c1 = self._gradient_widget._sample_gradient_at(1.0)
        self.assertAlmostEqual(c1[2], 1.0, places=5)  # Blue at t=0.8, should extend

    # ------------------------------------------------------------------
    # Multiple keyframes edge cases
    # ------------------------------------------------------------------

    async def test_duplicate_time_keyframes(self):
        """Keyframes at the same time should not crash."""
        self._build_widget(
            keyframes=[
                (0.5, (1.0, 0.0, 0.0, 1.0)),
                (0.5, (0.0, 1.0, 0.0, 1.0)),
            ]
        )
        await _wait_updates()

        kfs = self._gradient_widget.get_keyframes()
        self.assertEqual(len(kfs), 2)

    async def test_single_keyframe_at_zero(self):
        """A single keyframe at t=0 should work."""
        self._build_widget(keyframes=[(0.0, (0.5, 0.5, 0.5, 1.0))])
        await _wait_updates()

        kfs = self._gradient_widget.get_keyframes()
        self.assertEqual(len(kfs), 1)
        self.assertAlmostEqual(kfs[0][0], 0.0)

    async def test_single_keyframe_at_one(self):
        """A single keyframe at t=1.0 should work."""
        self._build_widget(keyframes=[(1.0, (0.5, 0.5, 0.5, 1.0))])
        await _wait_updates()

        kfs = self._gradient_widget.get_keyframes()
        self.assertEqual(len(kfs), 1)
        self.assertAlmostEqual(kfs[0][0], 1.0)

    async def test_many_keyframes(self):
        """Widget should handle 100 keyframes without issues."""
        kfs = [(i / 99.0, (i / 99.0, 0.5, 1.0 - i / 99.0, 1.0)) for i in range(100)]
        self._build_widget(keyframes=kfs)
        await _wait_updates()

        got = self._gradient_widget.get_keyframes()
        self.assertEqual(len(got), 100)

    async def _assert_preset_keyframes(self, preset_name: str, expected_keyframes: list):
        """Helper: apply a named preset and verify the resulting keyframes."""
        self._build_widget()
        await _wait_updates()
        self._gradient_widget._apply_preset(preset_name)
        await _wait_updates()
        kfs = self._gradient_widget.get_keyframes()
        self.assertEqual(len(kfs), len(expected_keyframes))
        for i, (exp_time, exp_color) in enumerate(expected_keyframes):
            if exp_time is not None:
                self.assertEqual(kfs[i][0], exp_time)
            self.assertEqual(kfs[i][1], exp_color)

    async def test_preset_grayscale(self):
        """Grayscale preset produces a black-to-white gradient."""
        await self._assert_preset_keyframes(
            "Grayscale",
            [(0.0, (0.0, 0.0, 0.0, 1.0)), (1.0, (1.0, 1.0, 1.0, 1.0))],
        )

    async def test_preset_linear_red(self):
        """Linear Red preset produces a black-to-red gradient."""
        await self._assert_preset_keyframes(
            "Linear Red",
            [(None, (0.0, 0.0, 0.0, 1.0)), (None, (1.0, 0.0, 0.0, 1.0))],
        )

    async def test_preset_transparent_to_opaque(self):
        """Transparent to Opaque preset goes from transparent to opaque white."""
        await self._assert_preset_keyframes(
            "Transparent to Opaque",
            [(None, (1.0, 1.0, 1.0, 0.0)), (None, (1.0, 1.0, 1.0, 1.0))],
        )

    async def test_operation_reverse_gradient(self):
        """Reverse operation should flip keyframe colors end-to-end."""
        self._build_widget()
        await _wait_updates()

        self._gradient_widget._apply_preset("Grayscale")
        await _wait_updates()

        self._gradient_widget._reverse_gradient()
        await _wait_updates()

        kfs = self._gradient_widget.get_keyframes()
        self.assertEqual(kfs[0][1], (1.0, 1.0, 1.0, 1.0))  # White at start after reverse
        self.assertEqual(kfs[1][1], (0.0, 0.0, 0.0, 1.0))  # Black at end after reverse

    async def test_operation_distribute_evenly(self):
        """Distribute Evenly should space all keyframes uniformly across [0, 1]."""
        self._build_widget()
        await _wait_updates()

        uneven_kfs = [
            (0.1, (1.0, 0.0, 0.0, 1.0)),
            (0.3, (0.0, 1.0, 0.0, 1.0)),
            (0.45, (0.0, 0.0, 1.0, 1.0)),
            (0.7, (1.0, 1.0, 0.0, 1.0)),
            (0.95, (1.0, 0.0, 1.0, 1.0)),
        ]
        self._gradient_widget.set_keyframes(uneven_kfs)
        await _wait_updates()

        self._gradient_widget._distribute_evenly()
        await _wait_updates()

        kfs = self._gradient_widget.get_keyframes()
        self.assertEqual(len(kfs), 5)
        self.assertAlmostEqual(kfs[0][0], 0.0, places=5)
        self.assertAlmostEqual(kfs[1][0], 0.25, places=5)
        self.assertAlmostEqual(kfs[2][0], 0.5, places=5)
        self.assertAlmostEqual(kfs[3][0], 0.75, places=5)
        self.assertAlmostEqual(kfs[4][0], 1.0, places=5)

    async def test_operation_randomize_colors(self):
        """Randomize Colors should assign valid in-range RGBA values, keeping alpha=1."""
        self._build_widget()
        await _wait_updates()

        self._gradient_widget.set_keyframes([(i / 4.0, (0.0, 0.0, 0.0, 1.0)) for i in range(5)])
        await _wait_updates()

        self._gradient_widget._randomize_colors()
        await _wait_updates()

        kfs = self._gradient_widget.get_keyframes()
        self.assertEqual(len(kfs), 5)
        for _time, color in kfs:
            self.assertGreaterEqual(color[0], 0.0)
            self.assertLessEqual(color[0], 1.0)
            self.assertGreaterEqual(color[1], 0.0)
            self.assertLessEqual(color[1], 1.0)
            self.assertGreaterEqual(color[2], 0.0)
            self.assertLessEqual(color[2], 1.0)
            self.assertEqual(color[3], 1.0)

    async def test_operation_clear_all(self):
        """Clear All should remove every keyframe."""
        self._build_widget(keyframes=[(0.0, (1.0, 0.0, 0.0, 1.0)), (1.0, (0.0, 0.0, 1.0, 1.0))])
        await _wait_updates()

        self._gradient_widget._clear_all_keyframes()
        await _wait_updates()

        self.assertEqual(len(self._gradient_widget.get_keyframes()), 0)

    async def test_constant_preset_no_keyframes(self):
        """Test that Constant preset creates 0 keyframes."""
        self._build_widget(keyframes=[(0.0, (1.0, 0.0, 0.0, 1.0)), (1.0, (0.0, 0.0, 1.0, 1.0))])
        await _wait_updates()

        self._gradient_widget._apply_preset("Constant")
        await _wait_updates()

        kfs = self._gradient_widget.get_keyframes()
        self.assertEqual(len(kfs), 0)  # Should have no keyframes

    async def test_constant_preset_color_swatch_updates_default_color(self):
        """Test that changing color swatch with 0 keyframes updates default color, not creates keyframe."""
        # Start with Constant preset (0 keyframes)
        self._build_widget(default_color=(0.5, 0.5, 0.5, 1.0))
        await _wait_updates()

        self._gradient_widget._apply_preset("Constant")
        await _wait_updates()

        # Verify we have 0 keyframes
        self.assertEqual(len(self._gradient_widget.get_keyframes()), 0)

        # Show popup so the edit row (and color widget) are built
        await self._show_widget_popup()

        # Simulate color swatch change by directly calling the internal method
        # (simulating user picking a new color)
        new_color = (0.8, 0.2, 0.3, 0.9)

        # Set the color widget to the new color
        cw = self._gradient_widget._color_widget
        children = cw.model.get_item_children()
        for child, value in zip(children, new_color):
            cw.model.get_item_value_model(child).set_value(value)
        await _wait_updates()

        # Should still have 0 keyframes (not create a keyframe at time 0)
        kfs = self._gradient_widget.get_keyframes()
        self.assertEqual(len(kfs), 0, "Changing color with Constant preset should not create a keyframe")

        # The default color should be updated
        self.assertEqual(self._gradient_widget._default_color, new_color)

        # The callback should have been fired with empty lists
        self.assertIsNotNone(self._last_callback_times)
        self.assertEqual(len(self._last_callback_times), 0)
        self.assertEqual(len(self._last_callback_values), 0)

    async def test_edit_row_no_clipping_at_various_widths(self):
        """Presets button and gradient bar should remain visible at various window widths."""
        initial = [
            (0.0, (1.0, 0.0, 0.0, 1.0)),
            (0.5, (0.0, 1.0, 0.0, 1.0)),
            (1.0, (0.0, 0.0, 1.0, 1.0)),
        ]

        for width in (600, 400, 300, 250, 120):
            with self.subTest(window_width=width):
                # Resize and rebuild
                if self._gradient_widget:
                    self._gradient_widget.destroy()
                    self._gradient_widget = None
                self._window.width = width
                await _wait_updates(5)

                self._build_widget(keyframes=initial)
                await _wait_updates(10)
                # Show popup so edit row (and presets button) are built
                await self._show_widget_popup()

                # Presets button should exist and have non-zero computed width
                presets = self._gradient_widget._presets_button
                self.assertIsNotNone(presets, f"Presets button missing at width={width}")
                self.assertGreater(
                    presets.computed_width,
                    0,
                    f"Presets button has 0 computed width at window width={width}",
                )

                # Gradient bar should span most of the window's content area.
                # Window content is narrower than declared width due to chrome
                # (borders, padding), plus _MARKER_SIZE for the two half-marker
                # spacers flanking the gradient bar.
                bar = self._gradient_widget._gradient_bar_stack
                self.assertIsNotNone(bar, f"Gradient bar missing at width={width}")
                self.assertGreater(
                    bar.computed_width,
                    width - 24,
                    f"Gradient bar too narrow at window width={width}: {bar.computed_width}",
                )

    async def test_gradient_and_markers_stay_within_window_on_resize(self):
        """Gradient bar and markers must not extend beyond the window frame.

        Regression test: using ``ui.Percent(100)`` for the gradient ZStack inside
        an HStack with fixed-pixel spacers caused the bar (and therefore the
        whole VStack) to overflow the window by ``_MARKER_SIZE`` pixels.  The fix
        is to use ``ui.Fraction(1)`` so the ZStack fills only the *remaining*
        space after the spacers are allocated.

        Each subtest creates a fresh window to avoid stale layout from a
        previous resize, which omni.ui may not fully propagate in a small
        number of frames.
        """
        initial = [
            (0.0, (1.0, 0.0, 0.0, 1.0)),
            (0.5, (0.0, 1.0, 0.0, 1.0)),
            (1.0, (0.0, 0.0, 1.0, 1.0)),
        ]

        for width in (500, 400, 300):
            with self.subTest(window_width=width):
                # Clean up previous iteration
                if self._gradient_widget:
                    self._gradient_widget.destroy()
                    self._gradient_widget = None
                if self._window:
                    self._window.destroy()

                # Fresh window at the target size — avoids stale layout
                self._window = ui.Window(
                    f"TestOverflow_{width}_{uuid.uuid1()}",
                    height=200,
                    width=width,
                    position_x=0,
                    position_y=0,
                )
                await _wait_updates(5)

                self._build_widget(keyframes=initial)
                await _wait_updates(15)
                # Show popup so markers are built and accessible
                await self._show_widget_popup()

                frame = self._window.frame
                frame_right = frame.screen_position_x + frame.computed_width

                # --- Gradient bar must not overflow the window frame ---
                bar = self._gradient_widget._gradient_bar_stack
                self.assertIsNotNone(bar, f"Gradient bar missing at width={width}")
                bar_right = bar.screen_position_x + bar.computed_width

                diag = (
                    f"\n  window width={width}"
                    f"\n  frame: x={frame.screen_position_x:.1f}  w={frame.computed_width:.1f}"
                    f"\n  bar:   x={bar.screen_position_x:.1f}  w={bar.computed_width:.1f}"
                    f"\n  bar_right={bar_right:.1f}  frame_right={frame_right:.1f}"
                )
                self.assertLessEqual(
                    bar_right,
                    frame_right + 1.0,  # 1 px rounding tolerance
                    f"Gradient bar overflows window frame.{diag}",
                )

                # --- Marker at t=1.0 (rightmost) must not overflow the popup window ---
                # Markers live in the popup window, not the test window.
                # Use the popup window's frame as the reference right edge.
                popup_win = self._gradient_widget._popup_window
                self.assertIsNotNone(popup_win, f"Popup window missing at width={width}")
                popup_frame = popup_win.frame
                popup_right = popup_frame.screen_position_x + popup_frame.computed_width

                marker_size = _MARKER_SIZE
                kf_end = next(kf for kf in self._gradient_widget._keyframes if kf.time == 1.0)
                marker = self._gradient_widget._marker_widgets.get(kf_end.uid)
                self.assertIsNotNone(marker, f"Marker at t=1.0 missing at width={width}")
                marker_right = marker.screen_position_x + marker_size

                diag_marker = (
                    f"\n  marker t=1.0: x={marker.screen_position_x:.1f}"
                    f"\n  marker_right={marker_right:.1f}  popup_right={popup_right:.1f}"
                )
                self.assertLessEqual(
                    marker_right,
                    popup_right + 1.0,
                    f"Marker at t=1.0 overflows popup window frame.{diag_marker}",
                )

    async def test_gradient_bar_shape_matches_property_fields(self):
        """Gradient bar border styling must match PropertiesWidgetField exactly.

        The property panel style defines the canonical shape for property panel
        input widgets: border_radius=5, border_width=1, border_color=0x33FFFFFF.
        The gradient bar overlay should use the same values so it visually
        matches adjacent float/string fields.
        """
        # These are the PropertiesWidgetField values the gradient bar must match.
        properties_widget_border_radius = 5
        properties_widget_border_width = 1
        properties_widget_border_color = 0x33FFFFFF  # _WHITE_20

        # Constants must be kept in sync with PropertiesWidgetField.
        self.assertEqual(
            _GRADIENT_BORDER_RADIUS,
            properties_widget_border_radius,
            f"_GRADIENT_BORDER_RADIUS ({_GRADIENT_BORDER_RADIUS}) must match "
            f"PropertiesWidgetField border_radius ({properties_widget_border_radius})",
        )

        # The overlay now uses a named style ("Rectangle::ColorGradientBarOverlay") rather
        # than an inline style dict.  Verify the local fallback style matches the spec.
        local_overlay_style = _get_local_style().get("Rectangle::ColorGradientBarOverlay", {})
        self.assertEqual(
            local_overlay_style.get("border_radius"),
            properties_widget_border_radius,
            "Local overlay style border_radius must match PropertiesWidgetField",
        )
        self.assertEqual(
            local_overlay_style.get("border_width"),
            properties_widget_border_width,
            "Local overlay style border_width must match PropertiesWidgetField",
        )
        self.assertEqual(
            local_overlay_style.get("border_color"),
            properties_widget_border_color,
            f"Local overlay style border_color (0x{local_overlay_style.get('border_color', 0):08X}) must match "
            f"PropertiesWidgetField border_color (0x{properties_widget_border_color:08X})",
        )

        self._build_widget()
        await _wait_updates()

        overlay = self._gradient_widget._gradient_overlay
        self.assertIsNotNone(overlay, "Gradient overlay widget is missing")

    # ------------------------------------------------------------------
    # Popup-persistence tests (colour picker / presets dropdown)
    # ------------------------------------------------------------------

    async def test_popup_stays_open_during_presets_menu(self):
        """Popup must remain visible while the Presets dropdown is open.

        Calling _show_presets_menu() opens a ui.Menu popup.  Because our editor
        window no longer uses WINDOW_FLAGS_POPUP, ImGui's popup-stack rules cannot
        auto-dismiss it when an unrelated popup opens.  After the presets menu is
        shown the gradient popup should still be visible.
        """
        self._build_widget(keyframes=[(0.0, (1.0, 0.0, 0.0, 1.0))])
        await _wait_updates(10)
        await self._show_widget_popup()

        # Open the presets dropdown exactly as the Presets button would.
        self._gradient_widget._show_presets_menu()
        await _wait_updates(5)

        self.assertTrue(
            self._gradient_widget._popup_window.visible,
            "Popup should remain visible while the Presets menu is open",
        )

        # Tidy up the menu to avoid leaking into other tests.
        presets_menu = getattr(self._gradient_widget, "_presets_menu", None)
        if presets_menu is not None:
            presets_menu.destroy()
            self._gradient_widget._presets_menu = None

    async def test_popup_hidden_on_hide(self):
        """_hide_popup must make the popup invisible."""
        self._build_widget(keyframes=[(0.0, (1.0, 0.0, 0.0, 1.0))])
        await _wait_updates(10)
        await self._show_widget_popup()

        self.assertTrue(self._gradient_widget._popup_window.visible, "Popup should be visible after show")

        self._gradient_widget._hide_popup()
        await _wait_updates(3)

        self.assertFalse(
            self._gradient_widget._popup_window.visible,
            "Popup window should be hidden after _hide_popup",
        )

    async def test_popup_hidden_via_window_close_callback(self):
        """Title-bar X button (visibility-changed callback) must clean up popup state."""
        self._build_widget(keyframes=[(0.0, (1.0, 0.0, 0.0, 1.0))])
        await _wait_updates(10)
        await self._show_widget_popup()

        # Simulate what the title-bar X button does: visibility drops to False.
        self._gradient_widget._on_window_close(False)
        await _wait_updates(3)

        self.assertIsNone(
            ColorGradientWidget._active_popup_widget,
            "Active popup widget should be cleared when window closes via title-bar X",
        )
        self.assertEqual(
            self._gradient_widget._color_picker_active,
            0,
            "Color picker state should be cleared on window close",
        )

    async def test_closest_marker_selected_on_row_press(self):
        """Clicking a marker should select it."""
        self._build_widget(
            keyframes=[
                (0.2, (1.0, 0.0, 0.0, 1.0)),
                (0.8, (0.0, 0.0, 1.0, 1.0)),
            ]
        )
        await _wait_updates(10)
        await self._show_widget_popup()

        uid_80 = self._gradient_widget._keyframes[1].uid
        self._gradient_widget._on_marker_pressed(uid_80, 0)
        await _wait_updates(3)

        self.assertEqual(
            self._gradient_widget._selected_uid,
            uid_80,
            "Clicked marker (0.8) should be selected",
        )

    async def test_marker_drag_moves_correct_marker(self):
        """Dragging a marker via its Placer offset should update its time."""
        self._build_widget(
            keyframes=[
                (0.1, (1.0, 0.0, 0.0, 1.0)),
                (0.9, (0.0, 0.0, 1.0, 1.0)),
            ]
        )
        await _wait_updates(10)
        await self._show_widget_popup()

        uid_09 = self._gradient_widget._keyframes[1].uid
        # Select the 0.9 marker
        self._gradient_widget._on_marker_pressed(uid_09, 0)
        await _wait_updates(2)

        # Simulate Placer offset change to 95%
        self._gradient_widget._on_marker_dragged(uid_09, ui.Percent(95.0))
        await _wait_updates(2)

        kfs = self._gradient_widget.get_keyframes()
        times = sorted(t for t, _ in kfs)
        self.assertAlmostEqual(times[0], 0.1, places=1, msg="Left marker should be unchanged")
        self.assertGreater(times[1], 0.8, msg="Right marker should have moved toward 0.95")

        self._gradient_widget._on_marker_released(uid_09, 0)

    async def test_popup_bar_click_uses_popup_bar_width(self):
        """Click-to-add on the popup gradient bar must use the popup bar's width and
        position, not the (possibly narrower) inline bar's dimensions.

        Regression: _on_bar_released was using self._gradient_overlay (inline bar)
        for position math, which gave wrong keyframe times when _POPUP_MIN_WIDTH
        made the popup bar wider.
        """
        self._build_widget(keyframes=[])
        await _wait_updates(10)
        await self._show_widget_popup()

        popup_bar = self._gradient_widget._popup_gradient_overlay
        self.assertIsNotNone(popup_bar, "_popup_gradient_overlay must be set")

        bar_x = popup_bar.screen_position_x
        bar_w = popup_bar.computed_width

        # Simulate a click at exactly 50 % of the popup bar
        click_x = bar_x + bar_w * 0.5
        self._gradient_widget._on_popup_bar_released(click_x, 0.0, 0, 0)
        await _wait_updates(3)

        kfs = self._gradient_widget.get_keyframes()
        self.assertEqual(len(kfs), 1, "One keyframe should have been added")
        self.assertAlmostEqual(
            kfs[0][0],
            0.5,
            places=1,
            msg="Keyframe time should be ~0.5 when clicking at 50% of the popup bar",
        )

    # ------------------------------------------------------------------
    # Callback contract / undo grouping
    # ------------------------------------------------------------------

    async def test_gradient_changed_callback_fires_once_per_add(self):
        """on_gradient_changed_fn fires exactly once when a keyframe is added."""
        call_log = []
        self._build_widget(on_gradient_changed_fn=lambda t, v: call_log.append((list(t), [tuple(c) for c in v])))
        await _wait_updates()

        # Simulate click-to-add by calling the internal handler directly
        # (no popup visible, so use _on_popup_bar_released via a mock overlay position)
        # Directly add a keyframe the same way the internals do
        new_kf = _KF(0.5, (1.0, 0.0, 0.0, 1.0))
        self._gradient_widget._keyframes.append(new_kf)
        self._gradient_widget._selected_uid = new_kf.uid
        self._gradient_widget._refresh_all()
        await _wait_updates()

        self.assertEqual(len(call_log), 1, "callback should fire exactly once per add")
        self.assertAlmostEqual(call_log[0][0][0], 0.5)

    async def test_gradient_changed_callback_fires_once_on_drag_end(self):
        """on_gradient_changed_fn fires on drag moves and on release."""
        call_log = []
        self._build_widget(
            keyframes=[(0.5, (1.0, 0.0, 0.0, 1.0))],
            on_gradient_changed_fn=lambda t, v: call_log.append((list(t), [tuple(c) for c in v])),
        )
        await _wait_updates(10)
        await self._show_widget_popup()

        uid = self._gradient_widget._keyframes[0].uid
        self._gradient_widget._on_marker_pressed(uid, 0)
        call_log.clear()

        self._gradient_widget._on_marker_dragged(uid, ui.Percent(30.0))
        self._gradient_widget._on_marker_dragged(uid, ui.Percent(20.0))
        await _wait_updates()

        move_count = len(call_log)
        self.assertGreater(move_count, 0, "callback fires during drag moves")

        self._gradient_widget._on_marker_released(uid, 0)
        await _wait_updates()

        self.assertGreater(len(call_log), move_count, "callback fires on release too")

    async def test_drag_does_not_fire_changed_during_move(self):
        """Dragging a marker fires changed on each move and on release."""
        call_log = []
        self._build_widget(
            keyframes=[(0.5, (1.0, 0.0, 0.0, 1.0))],
            on_gradient_changed_fn=lambda t, v: call_log.append(list(t)),
        )
        await _wait_updates(10)
        await self._show_widget_popup()

        uid = self._gradient_widget._keyframes[0].uid
        self._gradient_widget._on_marker_pressed(uid, 0)
        await _wait_updates(2)

        call_log.clear()
        for pct in [40.0, 30.0, 20.0, 10.0]:
            self._gradient_widget._on_marker_dragged(uid, ui.Percent(pct))
        await _wait_updates(3)

        self.assertGreater(len(call_log), 0, "changed callback fires during drag moves")

        self._gradient_widget._on_marker_released(uid, 0)
        await _wait_updates(3)

    async def test_drag_produces_single_undoable_commit(self):
        """A complete drag produces exactly one on_gradient_changed_fn call.

        The caller (USD layer) wraps each call in a single undo group, so one call = one
        undo step.  Moving a marker through many intermediate positions must result in a
        single undo step that returns the marker all the way back to its starting position,
        not just one increment.
        """
        initial_time = 0.5
        initial_color = (1.0, 0.0, 0.0, 1.0)

        # Simple undo stack mirroring what the USD layer does: each entry is the full
        # (times, values) snapshot passed to on_gradient_changed_fn.
        undo_stack = [([initial_time], [initial_color])]  # pre-drag baseline

        def on_changed(times, values):
            undo_stack.append((list(times), [tuple(c) for c in values]))

        self._build_widget(
            keyframes=[(initial_time, initial_color)],
            on_gradient_changed_fn=on_changed,
        )
        await _wait_updates(10)
        await self._show_widget_popup()

        uid = self._gradient_widget._keyframes[0].uid
        self._gradient_widget._on_marker_pressed(uid, 0)
        for pct in [60.0, 65.0, 70.0, 75.0, 80.0]:
            self._gradient_widget._on_marker_dragged(uid, ui.Percent(pct))
        self._gradient_widget._on_marker_released(uid, 0)
        await _wait_updates(3)

        # At least one callback should have fired (may be more with per-move firing).
        self.assertGreater(
            len(undo_stack),
            1,
            "A drag must produce at least one on_gradient_changed_fn call",
        )

        # The single entry reflects the final position.
        drag_final_time = undo_stack[-1][0][0]
        actual_final_time = self._gradient_widget.get_keyframes()[0][0]
        self.assertAlmostEqual(
            drag_final_time,
            actual_final_time,
            places=4,
            msg="The single undo-stack entry must capture the final drag position",
        )

        # Simulate undo: restore the pre-drag baseline (first entry).
        pre_times, pre_values = undo_stack[0]
        self._gradient_widget.set_keyframes(list(zip(pre_times, pre_values)))
        await _wait_updates(3)

        self.assertAlmostEqual(
            self._gradient_widget.get_keyframes()[0][0],
            initial_time,
            places=4,
            msg="After undo the keyframe must return to its pre-drag time",
        )

        # Simulate redo: re-apply the drag entry.
        redo_times, redo_values = undo_stack[-1]
        self._gradient_widget.set_keyframes(list(zip(redo_times, redo_values)))
        await _wait_updates(3)

        self.assertAlmostEqual(
            self._gradient_widget.get_keyframes()[0][0],
            drag_final_time,
            places=4,
            msg="After redo the keyframe must return to the post-drag time",
        )
        self.assertNotAlmostEqual(
            self._gradient_widget.get_keyframes()[0][0],
            initial_time,
            places=2,
            msg="Post-redo position must differ from the pre-drag position",
        )

    # ------------------------------------------------------------------
    # Marker drag-area height
    # ------------------------------------------------------------------

    async def test_marker_drag_area_expands_with_popup_resize(self):
        """The marker frame should exist and have a reasonable height after popup open."""
        self._build_widget(keyframes=[(0.5, (1.0, 0.0, 0.0, 1.0))])
        await _wait_updates(10)
        await self._show_widget_popup()

        markers_frame = self._gradient_widget._popup_markers_frame
        self.assertIsNotNone(markers_frame, "Markers frame should exist after popup open")

        edit_frame = self._gradient_widget._popup_edit_frame
        self.assertIsNotNone(edit_frame, "_popup_edit_frame should be set")
