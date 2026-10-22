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

from unittest import mock

import omni.kit.test

from ... import InMemoryGroupedKeysModel, color_gradient
from ...color_gradient import DEFAULT_GRADIENT_COLOR, ColorGradientWidget, GradientPreview

__all__ = ["TestColorGradientWidgetLogic"]

_GROUP_ID = "gradient"


def _payload_from_keyframes(keyframes):
    """Convert color keyframes to a grouped-key payload.

    Args:
        keyframes: Sequence of time and color pairs.

    Returns:
        Payload containing corresponding times and values.
    """
    return {
        "times": [time for time, _color in keyframes],
        "values": [color for _time, color in keyframes],
    }


class TestColorGradientWidgetLogic(omni.kit.test.AsyncTestCase):
    """Test UI-independent color-gradient editing logic."""

    async def test_construct_from_model_returns_exact_configuration(self):
        """Return exact stored keyframes and read-only state for supported configurations."""
        populated = [
            (0.0, (0.1, 0.2, 0.3, 0.4)),
            (1.0, (0.5, 0.6, 0.7, 0.8)),
        ]
        oversized_keyframes = [
            (index // 2 / 64.0, (index / 129.0, 0.5, 1.0 - index / 129.0, 1.0)) for index in range(129, -1, -1)
        ]
        expected_limited_keyframes = [
            (time_index / 64.0, (index / 129.0, 0.5, 1.0 - index / 129.0, 1.0))
            for time_index in range(1, 65)
            for index in (2 * time_index + 1, 2 * time_index)
        ]
        cases = [
            ("empty", [], [], False),
            ("populated_read_only", populated, populated, True),
            ("first_128_then_stable_sort", oversized_keyframes, expected_limited_keyframes, False),
        ]

        for title, keyframes, expected, read_only in cases:
            with self.subTest(title=title):
                # Arrange
                model = InMemoryGroupedKeysModel(
                    group_ids=[_GROUP_ID], payloads={_GROUP_ID: _payload_from_keyframes(keyframes)}
                )
                preview = GradientPreview(
                    gradient_provider=mock.Mock(name="gradient_provider"),
                    checker_provider=mock.Mock(name="checker_provider"),
                )
                widget = None
                try:
                    # Act
                    widget = ColorGradientWidget(model, _GROUP_ID, preview, read_only=read_only)

                    # Assert
                    self.assertEqual(widget.get_keyframes(), expected)
                    self.assertEqual(widget.read_only, read_only)
                finally:
                    if widget is not None:
                        widget.destroy()
                    model.destroy()

    async def test_set_keyframes_replaces_sorts_or_clears_without_committing(self):
        """Replace, sort, or clear local keyframes without committing a model payload."""
        red = (1.0, 0.0, 0.0, 1.0)
        green = (0.0, 1.0, 0.0, 0.5)
        blue = (0.0, 0.0, 1.0, 0.25)
        cases = [
            ("sorting", [(0.9, blue), (0.1, red), (0.5, green)], [(0.1, red), (0.5, green), (0.9, blue)]),
            ("empty", [], []),
        ]

        for title, replacement, expected in cases:
            with self.subTest(title=title):
                # Arrange
                initial = [(0.0, red), (1.0, blue)]
                widget, model = self._make_widget(initial)
                with mock.patch.object(model, "commit_payload", wraps=model.commit_payload) as commit_payload:
                    # Act
                    widget.set_keyframes(replacement)

                    # Assert
                    self.assertEqual(widget.get_keyframes(), expected)
                    commit_payload.assert_not_called()

    async def test_sample_gradient_returns_expected_color(self):
        """Return default, single-stop, interpolated, or clamped colors when sampled."""
        default_color = (0.3, 0.4, 0.5, 0.6)
        single_color = (0.1, 0.2, 0.3, 0.4)
        red = (1.0, 0.0, 0.0, 1.0)
        blue = (0.0, 0.0, 1.0, 1.0)
        cases = [
            ("custom_default", [], default_color, 0.5, default_color),
            ("single", [(0.5, single_color)], default_color, 0.75, single_color),
            ("interpolation", [(0.0, red), (1.0, blue)], default_color, 0.25, (0.75, 0.0, 0.25, 1.0)),
            ("clamp_before_first", [(0.2, red), (0.8, blue)], default_color, 0.0, red),
            ("clamp_after_last", [(0.2, red), (0.8, blue)], default_color, 1.0, blue),
        ]

        for title, keyframes, case_default, sample_time, expected in cases:
            with self.subTest(title=title):
                # Arrange
                widget, _model = self._make_widget(keyframes, default_color=case_default)

                # Act
                result = widget._sample_gradient_at(sample_time)

                # Assert
                self.assertEqual(result, expected)

    async def test_destroy_ends_active_edit_and_tolerates_released_model(self):
        """Release editor subscriptions and active edits while retaining supplied preview and model state."""
        cases = [("active_edit", False, True), ("released_model", True, False)]

        for title, release_model, should_end_edit in cases:
            with self.subTest(title=title):
                # Arrange
                fallback_color = (0.3, 0.4, 0.5, 0.6)
                initial_payload = _payload_from_keyframes([(0.5, fallback_color)])
                model = InMemoryGroupedKeysModel(group_ids=[_GROUP_ID], payloads={_GROUP_ID: initial_payload})
                initial_subscription_count = len(model._on_change)
                gradient_provider = mock.Mock(name="gradient_provider")
                checker_provider = mock.Mock(name="checker_provider")
                preview = GradientPreview(
                    default_color=fallback_color,
                    time_range=(0.0, 2.0),
                    gradient_provider=gradient_provider,
                    checker_provider=checker_provider,
                )
                widget = ColorGradientWidget(model, _GROUP_ID, preview)
                editor_subscription_count = len(model._on_change)
                widget._is_editing_model = True
                if release_model:
                    widget._model = None
                try:
                    with mock.patch.object(model, "end_edit", wraps=model.end_edit) as end_edit:
                        # Act
                        widget.destroy()

                        # Assert
                        self.assertFalse(widget._is_editing_model)
                        self.assertEqual(end_edit.call_args_list, [mock.call(_GROUP_ID)] if should_end_edit else [])
                        self.assertEqual(editor_subscription_count, initial_subscription_count + 1)
                        self.assertEqual(len(model._on_change), initial_subscription_count)
                        self.assertEqual(model.get_payload(_GROUP_ID), initial_payload)
                        self.assertIs(preview.gradient_provider, gradient_provider)
                        self.assertIs(preview.checker_provider, checker_provider)
                        self.assertEqual(preview.fallback_color, fallback_color)
                        self.assertEqual(preview.time_range, (0.0, 2.0))
                        gradient_provider.destroy.assert_not_called()
                        checker_provider.destroy.assert_not_called()
                finally:
                    if not widget._destroyed:
                        widget.destroy()
                    model.destroy()

    async def test_distribute_evenly_commits_exact_times_and_unchanged_colors(self):
        """Commit evenly distributed times while preserving every keyframe color."""
        # Arrange
        colors = [
            (1.0, 0.0, 0.0, 1.0),
            (0.0, 1.0, 0.0, 0.75),
            (0.0, 0.0, 1.0, 0.5),
            (1.0, 1.0, 0.0, 0.25),
            (1.0, 0.0, 1.0, 0.0),
        ]
        initial = list(zip((0.1, 0.3, 0.45, 0.7, 0.95), colors))
        expected = list(zip((0.0, 0.25, 0.5, 0.75, 1.0), colors))
        widget, model = self._make_widget(initial)

        # Act
        widget._distribute_evenly()

        # Assert
        self.assertEqual(widget.get_keyframes(), expected)
        self.assertEqual(model.get_payload(_GROUP_ID), _payload_from_keyframes(expected))

    async def test_randomize_colors_commits_deterministic_rgb_and_preserves_times(self):
        """Commit deterministic opaque random colors without changing keyframe times."""
        # Arrange
        initial = [(0.2, (0.0, 0.0, 0.0, 0.2)), (0.8, (1.0, 1.0, 1.0, 0.8))]
        expected = [(0.2, (0.1, 0.2, 0.3, 1.0)), (0.8, (0.4, 0.5, 0.6, 1.0))]
        widget, model = self._make_widget(initial)
        with mock.patch.object(color_gradient.random, "random", side_effect=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6)):
            # Act
            widget._randomize_colors()

            # Assert
            self.assertEqual(widget.get_keyframes(), expected)
            self.assertEqual(model.get_payload(_GROUP_ID), _payload_from_keyframes(expected))

    async def test_clear_all_keyframes_commits_empty_payload(self):
        """Remove every keyframe and commit an empty grouped payload."""
        # Arrange
        initial = [(0.0, (1.0, 0.0, 0.0, 1.0)), (1.0, (0.0, 0.0, 1.0, 1.0))]
        expected_payload = {"times": [], "values": []}
        widget, model = self._make_widget(initial)

        # Act
        widget._clear_all_keyframes()

        # Assert
        self.assertEqual(widget.get_keyframes(), [])
        self.assertEqual(model.get_payload(_GROUP_ID), expected_payload)

    def _make_widget(self, keyframes, *, default_color=DEFAULT_GRADIENT_COLOR):
        """Create a model-backed widget and register both cleanup steps."""
        model = InMemoryGroupedKeysModel(
            group_ids=[_GROUP_ID], payloads={_GROUP_ID: _payload_from_keyframes(keyframes)}
        )
        self.addCleanup(model.destroy)
        preview = GradientPreview(
            default_color=default_color,
            gradient_provider=mock.Mock(name="gradient_provider"),
            checker_provider=mock.Mock(name="checker_provider"),
        )
        widget = ColorGradientWidget(model, _GROUP_ID, preview)
        self.addCleanup(widget.destroy)
        return widget, model
