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
    "CUSTOM_MANIPULATORS_CATEGORY",
    "CUSTOM_MANIPULATORS_SECTION",
    "build_collection_item",
]

import omni.ui as ui
from omni.kit.viewport.menubar.core import (
    CategoryCollectionItem,
    CategoryCustomItem,
    FloatArraySettingColorMenuItem,
    SettingModelWithDefaultValue,
    SliderMenuDelegate,
)

from .constants import (
    CONE_INNER_COLOR_DEFAULT,
    CONE_OUTER_COLOR_DEFAULT,
    CONE_SIDES_DEFAULT,
    CONE_SIDES_MAX_INPUT,
    CONE_SIDES_MIN_INPUT,
    CONE_THRESHOLD_DEFAULT,
    CONE_THRESHOLD_MIN_INPUT,
)
from .layer import (
    SETTING_SPOTLIGHT_CONE_ILLUMINANCE_THRESHOLD,
    SETTING_SPOTLIGHT_CONE_INNER_COLOR,
    SETTING_SPOTLIGHT_CONE_OUTER_COLOR,
    SETTING_SPOTLIGHT_CONE_SIDES,
)

CUSTOM_MANIPULATORS_CATEGORY = "Custom Manipulators"
CUSTOM_MANIPULATORS_SECTION = "Custom Manipulators"

_THRESHOLD_MAX_SLIDER = 10.0


def _build_light_manipulator_widgets() -> None:
    threshold_model = SettingModelWithDefaultValue(
        SETTING_SPOTLIGHT_CONE_ILLUMINANCE_THRESHOLD,
        CONE_THRESHOLD_DEFAULT,
        draggable=True,
    )
    ui.MenuItem(
        "Cone Threshold (lux)",
        hide_on_click=False,
        delegate=SliderMenuDelegate(
            model=threshold_model,
            min=CONE_THRESHOLD_MIN_INPUT,
            max=_THRESHOLD_MAX_SLIDER,
            has_reset=True,
        ),
        identifier="SpotlightConeThreshold",
    )

    subdivisions_model = SettingModelWithDefaultValue(
        SETTING_SPOTLIGHT_CONE_SIDES,
        CONE_SIDES_DEFAULT,
        draggable=True,
    )
    ui.MenuItem(
        "Cone Subdivisions",
        hide_on_click=False,
        delegate=SliderMenuDelegate(
            model=subdivisions_model,
            min=CONE_SIDES_MIN_INPUT,
            max=CONE_SIDES_MAX_INPUT,
            slider_class=ui.IntSlider,
            has_reset=True,
        ),
        identifier="SpotlightConeSubdivisions",
    )

    FloatArraySettingColorMenuItem(
        SETTING_SPOTLIGHT_CONE_OUTER_COLOR,
        list(CONE_OUTER_COLOR_DEFAULT),
        name="Outer Cone Color",
        has_reset=True,
    )

    FloatArraySettingColorMenuItem(
        SETTING_SPOTLIGHT_CONE_INNER_COLOR,
        list(CONE_INNER_COLOR_DEFAULT),
        name="Inner Cone Color",
        has_reset=True,
    )


def _build_light_manipulator_submenu() -> None:
    ui.Menu(
        "Light Manipulator",
        on_build_fn=_build_light_manipulator_widgets,
        hide_on_click=False,
        identifier="LightManipulator",
    )


def build_collection_item() -> CategoryCollectionItem:
    return CategoryCollectionItem(
        CUSTOM_MANIPULATORS_CATEGORY,
        [
            CategoryCustomItem("Light Manipulator", _build_light_manipulator_submenu),
        ],
    )
