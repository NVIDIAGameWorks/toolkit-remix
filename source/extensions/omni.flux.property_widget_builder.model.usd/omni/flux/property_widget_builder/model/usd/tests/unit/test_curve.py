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

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

import omni.kit.test

from ...field_builders import curve
from ...field_builders.curve import _panel_to_editor_layout

__all__ = ["TestCurveFieldEditor", "TestPanelToEditorLayout"]

_CHANNEL_STYLE_NAME = "TestCurveAdapterChannel"
_TRANSPARENT_STYLE_NAME = "TestCurveAdapterTransparent"
_MISSING_STYLE_NAME = "TestCurveAdapterMissing"
_NO_COLOR_STYLE_NAME = "TestCurveAdapterNoColor"
_NORMAL_STYLE_COLOR = 0xFF123456
_FALLBACK_COLOR = 0xFF987654


class TestCurveFieldEditor(omni.kit.test.AsyncTestCase):
    """Test ownership without constructing a live popup window."""

    async def test_release_content_repeated_calls_destroy_editor_before_model_once(self):
        """Repeated popup cleanup preserves editor-before-storage destruction and runs once."""
        # Arrange
        destroyed = []
        model = Mock()
        editor = Mock()
        popup = SimpleNamespace(_model=model, _widget=editor)
        model.destroy.side_effect = lambda: destroyed.append("model")
        editor.destroy.side_effect = lambda: destroyed.append("editor")
        curve.CurveFieldEditor._release_content(popup)

        # Act
        curve.CurveFieldEditor._release_content(popup)

        # Assert
        self.assertEqual(destroyed, ["editor", "model"])
        editor.destroy.assert_called_once_with()
        model.destroy.assert_called_once_with()

    async def test_release_content_editor_failure_still_destroys_model(self):
        """An editor finalization error still releases its retained storage model."""
        # Arrange
        destroyed = []
        model = Mock()
        editor = Mock()
        popup = SimpleNamespace(_model=model, _widget=editor)
        model.destroy.side_effect = lambda: destroyed.append("model")
        editor.destroy.side_effect = RuntimeError("finish failed")

        # Act
        with self.assertRaisesRegex(RuntimeError, "finish failed"):
            curve.CurveFieldEditor._release_content(popup)

        # Assert
        self.assertEqual(destroyed, ["model"])
        editor.destroy.assert_called_once_with()
        model.destroy.assert_called_once_with()
        self.assertIsNone(popup._model)
        self.assertIsNone(popup._widget)


class TestPanelToEditorLayout(omni.kit.test.AsyncTestCase):
    """Test channel style resolution at the property-to-editor boundary."""

    async def setUp(self):
        """Isolate named styles at the layout module's UI dependency."""
        ui_patch = patch.object(curve, "ui")
        mock_ui = ui_patch.start()
        self.addCleanup(ui_patch.stop)
        mock_ui.Style.get_instance.return_value.default = {
            f"Label::{_CHANNEL_STYLE_NAME}": {"color": _NORMAL_STYLE_COLOR},
            f"Label::{_CHANNEL_STYLE_NAME}:selected": {"color": 0xFFABCDEF},
            f"Label::{_TRANSPARENT_STYLE_NAME}": {"color": 0},
            f"Label::{_NO_COLOR_STYLE_NAME}": {"font_size": 13},
        }

    async def test_transform_named_style_overrides_numeric_color_without_changing_input(self):
        """Resolve the normal rule and preserve the original panel metadata."""
        # Arrange
        layout = {
            "display_name": "Velocity",
            "curve_map": {
                "primvars:particle:velocity:x": {
                    "path": "x",
                    "display_name": "Horizontal",
                    "display_color": _FALLBACK_COLOR,
                    "label_style_name": _CHANNEL_STYLE_NAME,
                }
            },
        }
        original_layout = deepcopy(layout)

        # Act
        result = _panel_to_editor_layout(layout)

        # Assert
        self.assertEqual(
            result,
            {
                "display_name": "Velocity",
                "curves": [
                    {
                        "id": "particle:velocity:x",
                        "display_name": "Horizontal",
                        "display_color": _NORMAL_STYLE_COLOR,
                        "label_style_name": _CHANNEL_STYLE_NAME,
                    }
                ],
                "children": {},
            },
        )
        self.assertEqual(layout, original_layout)

    async def test_transform_zero_style_color_overrides_numeric_fallback(self):
        """Treat a fully transparent named color as an explicit value."""
        # Arrange
        layout = {
            "curve_map": {
                "primvars:particle:velocity:x": {
                    "path": "x",
                    "display_color": _FALLBACK_COLOR,
                    "label_style_name": _TRANSPARENT_STYLE_NAME,
                }
            }
        }

        # Act
        result = _panel_to_editor_layout(layout)

        # Assert
        self.assertEqual(result["curves"][0]["display_color"], 0)
        self.assertEqual(result["curves"][0]["label_style_name"], _TRANSPARENT_STYLE_NAME)

    async def test_transform_missing_normal_color_retains_numeric_fallback(self):
        """Keep caller colors when a named rule or its color is unavailable."""
        for style_name in (_MISSING_STYLE_NAME, _NO_COLOR_STYLE_NAME):
            with self.subTest(title=style_name):
                # Arrange
                layout = {
                    "curve_map": {
                        "primvars:particle:velocity:x": {
                            "path": "x",
                            "display_color": _FALLBACK_COLOR,
                            "label_style_name": style_name,
                        }
                    }
                }

                # Act
                result = _panel_to_editor_layout(layout)

                # Assert
                self.assertEqual(result["curves"][0]["display_color"], _FALLBACK_COLOR)
                self.assertEqual(result["curves"][0]["label_style_name"], style_name)

    async def test_transform_unresolved_style_without_fallback_preserves_group_inheritance(self):
        """Leave leaf colors absent so the editor can inherit group colors."""
        for style_name in (_MISSING_STYLE_NAME, _NO_COLOR_STYLE_NAME):
            with self.subTest(title=style_name):
                # Arrange
                layout = {
                    "display_color": 0xFF111111,
                    "children": {"velocity": {"display_name": "Velocity", "display_color": 0xFF222222}},
                    "curve_map": {
                        "primvars:particle:velocity:x": {"path": "velocity/x", "label_style_name": style_name}
                    },
                }

                # Act
                result = _panel_to_editor_layout(layout)

                # Assert
                self.assertEqual(result["display_color"], 0xFF111111)
                self.assertEqual(result["children"]["velocity"]["display_color"], 0xFF222222)
                self.assertEqual(
                    result["children"]["velocity"]["curves"],
                    [{"id": "particle:velocity:x", "display_name": "X", "label_style_name": style_name}],
                )

    async def test_transform_numeric_and_string_entries_preserves_existing_layout(self):
        """Retain numeric callers and the shorthand string-entry format."""
        # Arrange
        layout = {
            "display_name": "Velocity",
            "tooltip": "Animated velocity channels",
            "curve_map": {
                "primvars:particle:velocity:x": "x",
                "primvars:particle:velocity:y": {"path": "y", "display_color": _FALLBACK_COLOR},
            },
        }

        # Act
        result = _panel_to_editor_layout(layout)

        # Assert
        self.assertEqual(
            result,
            {
                "display_name": "Velocity",
                "tooltip": "Animated velocity channels",
                "curves": [
                    {"id": "particle:velocity:x", "display_name": "X"},
                    {"id": "particle:velocity:y", "display_name": "Y", "display_color": _FALLBACK_COLOR},
                ],
                "children": {},
            },
        )
