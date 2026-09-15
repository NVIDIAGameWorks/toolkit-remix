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

import pathlib
import tempfile
from unittest.mock import patch

from lightspeed.trex.schemas.categories import (
    ASSIGNABLE_REMIX_CATEGORIES,
    DEPRECATED_REMIX_CATEGORIES,
    REMIX_CATEGORIES,
    _SCHEMA_PATH,
    load_remix_categories,
)
from omni.kit.test import AsyncTestCase

_FIXTURES_PATH = pathlib.Path(__file__).parent / "fixtures"


class TestCategories(AsyncTestCase):
    """Tests the Remix categories schema parser."""

    def test_packaged_remix_categories_schema_exists(self):
        """Keep the runtime schema path aligned with the packaged HdRemix plugin."""
        self.assertTrue(_SCHEMA_PATH.is_file(), str(_SCHEMA_PATH))

    def test_packaged_remix_categories_schema_loads_categories(self):
        """Keep Toolkit category data available when generated schemas omit optional documentation."""
        self.assertTrue(REMIX_CATEGORIES)
        self.assertIn("World UI", REMIX_CATEGORIES)

    def test_deprecated_remix_categories_returns_maintained_decal_category_names(self):
        """Expose the explicit list of deprecated Remix decal categories."""
        # Arrange
        expected_categories = (
            "Decal Dynamic",
            "Decal Single Offset",
            "Decal No Offset",
        )

        # Act
        categories = DEPRECATED_REMIX_CATEGORIES

        # Assert
        self.assertEqual(categories, expected_categories)

    def test_assignable_remix_categories_excludes_deprecated_categories_from_complete_mapping(self):
        """Keep deprecated metadata readable without allowing new assignment."""
        # Arrange
        deprecated_categories = DEPRECATED_REMIX_CATEGORIES

        # Act
        assignable_categories = ASSIGNABLE_REMIX_CATEGORIES

        # Assert
        for category in deprecated_categories:
            self.assertIn(category, REMIX_CATEGORIES)
            self.assertNotIn(category, assignable_categories)

    def test_load_remix_categories_with_schema_formats_compatibility_mapping(self):
        """Return category metadata using the existing constants dictionary shape."""
        # Arrange
        schema_path = _FIXTURES_PATH / "remix_categories.usda"

        # Act
        categories = load_remix_categories(schema_path)

        # Assert
        self.assertEqual(list(categories), ["World UI", "Sky", "Decal"])
        self.assertEqual(categories["World UI"]["attr"], "remix_category:world_ui")
        self.assertEqual(
            categories["World UI"]["tooltip"],
            "Textures on draw calls that should be treated as screen space UI elements and rendered above the ray traced scene.",
        )
        self.assertEqual(categories["Sky"]["tooltip"], "Textures on draw calls used for the sky.")
        self.assertEqual(categories["Sky"]["full_description"], ["Textures on draw calls used for the sky."])
        self.assertEqual(categories["Decal"]["attr"], "remix_category:decal_Static")
        self.assertNotIn("Decal Static", categories)

    def test_load_remix_categories_with_long_paragraphs_wraps_description_as_visual_block(self):
        """Wrap description paragraphs for the info-icon tooltip box."""
        # Arrange
        schema_path = _FIXTURES_PATH / "remix_categories.usda"

        # Act
        description = load_remix_categories(schema_path)["World UI"]["full_description"]

        # Assert
        self.assertIn("", description)
        self.assertTrue(all(len(line) <= 60 for line in description))
        self.assertGreater(len(description), 3)

    def test_load_remix_categories_with_missing_file_logs_error_and_returns_empty_mapping(self):
        """Keep Toolkit startup alive when the packaged schema file is missing."""
        # Arrange
        schema_path = _FIXTURES_PATH / "missing.usda"

        # Act
        with patch("lightspeed.trex.schemas.categories.carb.log_error") as log_error_mock:
            categories = load_remix_categories(schema_path)

        # Assert
        self.assertEqual(categories, {})
        log_error_mock.assert_called_once()

    def test_load_remix_categories_without_api_prim_logs_error_and_returns_empty_mapping(self):
        """Keep Toolkit startup alive when the schema API prim is malformed."""
        # Arrange
        schema_path = _FIXTURES_PATH / "remix_particle_system.usda"

        # Act
        with patch("lightspeed.trex.schemas.categories.carb.log_error") as log_error_mock:
            categories = load_remix_categories(schema_path)

        # Assert
        self.assertEqual(categories, {})
        log_error_mock.assert_called_once()

    def test_load_remix_categories_with_runtime_error_propagates_exception(self):
        """Do not hide parser RuntimeError programming defects behind the startup boundary."""
        # Arrange
        schema_path = _FIXTURES_PATH / "remix_categories.usda"

        # Act / Assert
        with (
            patch(
                "lightspeed.trex.schemas.categories._parse_remix_categories",
                side_effect=RuntimeError("programming defect"),
            ),
            self.assertRaisesRegex(RuntimeError, "programming defect"),
        ):
            load_remix_categories(schema_path)

    def test_load_remix_categories_with_value_error_propagates_exception(self):
        """Do not hide parser ValueError programming defects behind the startup boundary."""
        # Arrange
        schema_path = _FIXTURES_PATH / "remix_categories.usda"

        # Act / Assert
        with (
            patch(
                "lightspeed.trex.schemas.categories._parse_remix_categories",
                side_effect=ValueError("programming defect"),
            ),
            self.assertRaisesRegex(ValueError, "programming defect"),
        ):
            load_remix_categories(schema_path)

    def test_load_remix_categories_without_non_empty_documentation_logs_error_and_returns_empty_mapping(self):
        """Treat whitespace-only schema documentation as an expected validation failure."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            # Arrange
            schema_path = pathlib.Path(temporary_directory) / "empty_documentation.usda"
            schema_path.write_text(
                """#usda 1.0

class "RemixInstanceCategoryAPI"
{
    bool remix_category:sky = 0 (
        doc = "\\n   "
        displayName = "Sky"
    )
}
""",
                encoding="utf-8",
            )

            # Act
            with patch("lightspeed.trex.schemas.categories.carb.log_error") as log_error_mock:
                categories = load_remix_categories(schema_path)

            # Assert
            self.assertEqual(categories, {})
            log_error_mock.assert_called_once()

    def test_load_remix_categories_without_documentation_uses_display_name_fallback(self):
        """Keep generated schemas usable when usdGenSchema omits optional documentation."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            # Arrange
            schema_path = pathlib.Path(temporary_directory) / "missing_documentation.usda"
            schema_path.write_text(
                """#usda 1.0

class "RemixInstanceCategoryAPI"
{
    bool remix_category:sky = 0 (
        displayName = "Sky"
    )
}
""",
                encoding="utf-8",
            )

            # Act
            categories = load_remix_categories(schema_path)

            # Assert
            self.assertEqual(categories["Sky"]["tooltip"], "Remix category: Sky.")
            self.assertEqual(categories["Sky"]["full_description"], ["Remix category: Sky."])

    def test_load_remix_categories_with_programming_error_propagates_exception(self):
        """Do not hide programming errors behind the startup-safe schema boundary."""
        # Arrange
        schema_path = _FIXTURES_PATH / "remix_categories.usda"

        # Act / Assert
        with (
            patch(
                "lightspeed.trex.schemas.categories._parse_remix_categories",
                side_effect=TypeError("programming defect"),
            ),
            self.assertRaisesRegex(TypeError, "programming defect"),
        ):
            load_remix_categories(schema_path)
