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

__all__ = ("TestDlssSettings",)

import tomllib
from pathlib import Path
from types import SimpleNamespace

from omni.kit.test import AsyncTestCase

from ...dlss_settings import (
    DLSS_ADVANCED_SETTINGS,
    DLSS_AUTO_MASK,
    DLSS_CHARACTER_INTENSITY,
    DLSS_ENABLE,
    DLSS_HIGHLIGHT_RECOVERY_THRESHOLDS,
    DLSS_INTENSITY,
    DLSS_MAIN_SETTINGS,
    DLSS_MODEL,
    DLSS_SETTINGS,
    DLSS_SETTINGS_TITLE,
    DLSS_STRUCTURE_INTENSITY,
    DLSS_TONE_INTENSITY,
    DLSS_VOLUMETRIC_IMPROVEMENT,
    coerce_dlss_value,
    format_dlss_value,
)

_EXTENSION_CONFIG = Path(__file__).parents[5] / "config" / "extension.toml"


class TestDlssSettings(AsyncTestCase):
    """Verify the shared DLSS descriptor and value conversion contract."""

    def test_setting_contract_matches_runtime_and_toml_defaults(self):
        """The shared descriptors should match the runtime keys and persisted defaults."""
        # Arrange
        expected_runtime_names = (
            "enable model intensity toneStrength structuralStrength useAutoMask "
            "skinStructureStrength enableHighlightRecovery highlightRecoveryThresholds enableVolumetricControlMask"
        )
        expected_strength_defaults = {
            "dlssNeuralRenderingToneIntensity": 0.3,
            "dlssNeuralRenderingStructureIntensity": 0.7,
            "dlssNeuralRenderingCharacterIntensity": 0.5,
        }
        with _EXTENSION_CONFIG.open("rb") as config_file:
            config = tomllib.load(config_file)["settings"]["persistent"]["exts"]
        configured_defaults = config["lightspeed.hdremix.renderer_settings"]
        expected_defaults = {setting.identifier: configured_defaults[setting.identifier] for setting in DLSS_SETTINGS}

        # Act
        contract = (
            " ".join(setting.runtime_key.removeprefix("rtx.dlssNeuralRendering.") for setting in DLSS_SETTINGS),
            {
                setting.identifier: list(setting.default) if isinstance(setting.default, tuple) else setting.default
                for setting in DLSS_SETTINGS
            },
        )

        # Assert
        self.assertEqual(contract, (expected_runtime_names, expected_defaults))
        self.assertFalse(DLSS_ENABLE.default)
        self.assertEqual(DLSS_SETTINGS_TITLE, "DLSS 3D-Guided Neural Generation [Experimental]")
        self.assertEqual(DLSS_ENABLE.label, "DLSS 3D-Guided Neural Generation")
        self.assertEqual(DLSS_MODEL.options, ("Model A", "Model B", "Model C"))
        self.assertEqual(
            DLSS_MAIN_SETTINGS,
            (
                DLSS_ENABLE,
                DLSS_MODEL,
                DLSS_STRUCTURE_INTENSITY,
                DLSS_TONE_INTENSITY,
                DLSS_AUTO_MASK,
                DLSS_CHARACTER_INTENSITY,
            ),
        )
        self.assertNotIn(DLSS_INTENSITY, DLSS_MAIN_SETTINGS + DLSS_ADVANCED_SETTINGS)
        self.assertIn(DLSS_VOLUMETRIC_IMPROVEMENT, DLSS_ADVANCED_SETTINGS)
        self.assertEqual(
            {identifier: expected_defaults[identifier] for identifier in expected_strength_defaults},
            expected_strength_defaults,
        )

    def test_values_are_coerced_and_formatted_for_runtime(self):
        """Representative persisted values should produce valid runtime strings."""
        # Arrange
        cases = (
            ("invalid Boolean uses disabled default", (DLSS_ENABLE, "invalid", "False")),
            ("scalar is clamped to maximum", (DLSS_INTENSITY, 2.0, "1.0")),
            (
                "vector components use bounds and defaults",
                (DLSS_HIGHLIGHT_RECOVERY_THRESHOLDS, "-1, 64, nan, 0.5", "0.0, 32.0, 0.75, 0.5"),
            ),
        )

        for title, case in cases:
            with self.subTest(title=title):
                # Arrange
                setting, raw_value, expected = case

                # Act
                value = format_dlss_value(coerce_dlss_value(setting, raw_value))

                # Assert
                self.assertEqual(value, expected)

    def test_model_values_are_coerced_and_formatted_for_runtime(self):
        """Model values should remain integer enum indices and reject unsupported selections."""
        # Arrange
        cases = (
            ("Model A", 0, "0"),
            ("string Model B", "1", "1"),
            ("Model C", 2, "2"),
            ("negative value uses default", -1, "0"),
            ("out-of-range value uses default", 3, "0"),
            ("invalid value uses default", "invalid", "0"),
            ("missing value uses default", None, "0"),
        )

        for title, raw_value, expected in cases:
            with self.subTest(title=title):
                # Act
                value = format_dlss_value(coerce_dlss_value(DLSS_MODEL, raw_value))

                # Assert
                self.assertEqual(value, expected)

    def test_bool_string_tokens_are_coerced_to_exact_values(self):
        """Recognized Boolean strings should retain their exact truth value."""
        # Arrange
        cases = (
            ("trimmed true token", (" true ", True)),
            ("uppercase false token", ("FALSE", False)),
            ("yes token", ("yes", True)),
            ("off token", ("off", False)),
        )

        for title, case in cases:
            with self.subTest(title=title):
                # Arrange
                raw_value, expected = case

                # Act
                value = coerce_dlss_value(DLSS_ENABLE, raw_value)

                # Assert
                self.assertIs(value, expected)

    def test_invalid_scalar_values_use_setting_default(self):
        """Invalid scalar inputs should fall back to the descriptor default."""
        # Arrange
        cases = (
            ("nonnumeric string", "not-a-number"),
            ("missing value", None),
            ("not-a-number float", float("nan")),
            ("positive infinity", float("inf")),
            ("negative infinity", -float("inf")),
        )

        for title, case_value in cases:
            with self.subTest(title=title):
                # Arrange
                setting = DLSS_INTENSITY
                raw_value = case_value

                # Act
                value = coerce_dlss_value(setting, raw_value)

                # Assert
                self.assertEqual(value, setting.default)

    def test_vector_boundaries_are_coerced_to_exact_values(self):
        """Malformed and out-of-range vectors should follow the descriptor contract."""
        # Arrange
        cases = (
            ("too few components", "1, 2, 3", None),
            ("too many components", [1, 2, 3, 4, 5], None),
            ("non-iterable", 42, None),
            (
                "component attributes",
                SimpleNamespace(x=-1, y=64, z=float("nan"), w=0.5),
                [0.0, 32.0, 0.75, 0.5],
            ),
        )

        for title, case_value, case_expected in cases:
            with self.subTest(title=title):
                # Arrange
                setting = DLSS_HIGHLIGHT_RECOVERY_THRESHOLDS
                raw_value = case_value
                expected = list(setting.default) if case_expected is None else case_expected

                # Act
                value = coerce_dlss_value(setting, raw_value)

                # Assert
                self.assertEqual(value, expected)
