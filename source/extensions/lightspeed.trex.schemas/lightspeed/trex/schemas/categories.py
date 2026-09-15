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

__all__ = [
    "ASSIGNABLE_REMIX_CATEGORIES",
    "DEPRECATED_REMIX_CATEGORIES",
    "REMIX_CATEGORIES",
    "REMIX_CATEGORIES_DISPLAY_NAMES",
    "load_remix_categories",
]

import pathlib
import textwrap

import carb
from pxr import Sdf, Tf

_DESCRIPTION_WIDTH = 60
_CATEGORY_DISPLAY_NAME_OVERRIDES = {"remix_category:decal_Static": "Decal"}
_SCHEMA_PATH = pathlib.Path(__file__).parents[3] / "usd" / "plugins" / "RemixCategories" / "generatedSchema.usda"
_SCHEMA_PRIM_PATH = Sdf.Path("/RemixInstanceCategoryAPI")

DEPRECATED_REMIX_CATEGORIES = (
    "Decal Dynamic",
    "Decal Single Offset",
    "Decal No Offset",
)


class _RemixCategoriesSchemaError(Exception):
    """Indicate an expected Remix categories schema load or validation failure."""


def _wrap_description(documentation: str) -> list[str]:
    """Wrap schema documentation into lines suitable for an info-icon tooltip."""
    description = []
    for paragraph in documentation.split("\n"):
        if paragraph:
            description.extend(textwrap.wrap(paragraph, width=_DESCRIPTION_WIDTH))
        elif description and description[-1] != "":
            description.append("")
    return description


def _parse_remix_categories(schema_path: pathlib.Path) -> dict[str, dict[str, str | list[str]]]:
    """Parse Remix category metadata from a valid USD schema layer."""
    layer = Sdf.Layer.FindOrOpen(str(schema_path))
    if not layer:
        raise _RemixCategoriesSchemaError(f"Remix categories schema layer could not be loaded: '{schema_path}'.")

    prim_spec = layer.GetPrimAtPath(_SCHEMA_PRIM_PATH)
    if not prim_spec:
        raise _RemixCategoriesSchemaError(
            f"Prim '{_SCHEMA_PRIM_PATH}' not found in Remix categories schema: '{schema_path}'."
        )

    categories = {}
    for attribute_spec in prim_spec.attributes:
        if attribute_spec.typeName != Sdf.ValueTypeNames.Bool:
            continue

        attribute_name = attribute_spec.path.name
        display_name = _CATEGORY_DISPLAY_NAME_OVERRIDES.get(attribute_name, attribute_spec.GetInfo("displayName"))
        documentation = attribute_spec.GetInfo("documentation")
        tooltip = next((line.strip() for line in documentation.splitlines() if line.strip()), None)
        if not display_name or ("documentation" in attribute_spec.ListInfoKeys() and not tooltip):
            raise _RemixCategoriesSchemaError(
                f"Remix category '{attribute_spec.path.name}' is missing displayName or documentation."
            )
        if not tooltip:
            tooltip = f"Remix category: {display_name}."

        categories[display_name] = {
            "attr": attribute_spec.path.name,
            "tooltip": tooltip,
            "full_description": _wrap_description(documentation) if documentation else [tooltip],
        }
    return categories


def load_remix_categories(schema_path: pathlib.Path) -> dict[str, dict[str, str | list[str]]]:
    """Load Remix categories without allowing schema failures to block Toolkit startup.

    Args:
        schema_path: Path to the Remix categories USD schema.

    Returns:
        Category metadata using the Toolkit's category dictionary shape, or an empty dictionary when loading fails.
    """
    try:
        return _parse_remix_categories(schema_path)
    except (OSError, Tf.ErrorException, _RemixCategoriesSchemaError) as exc:
        carb.log_error(f"[lightspeed.trex.schemas] {exc}")
        return {}


REMIX_CATEGORIES = load_remix_categories(_SCHEMA_PATH)
REMIX_CATEGORIES_DISPLAY_NAMES = {details["attr"]: name for name, details in REMIX_CATEGORIES.items()}
ASSIGNABLE_REMIX_CATEGORIES = {
    name: details for name, details in REMIX_CATEGORIES.items() if name not in DEPRECATED_REMIX_CATEGORIES
}
