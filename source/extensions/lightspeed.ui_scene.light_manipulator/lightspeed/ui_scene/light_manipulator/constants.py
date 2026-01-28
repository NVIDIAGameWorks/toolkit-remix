"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from __future__ import annotations

from omni.ui import color as cl

# this INTENSITY_SCALE is to make the manipulators a reasonable length with large intensity number
INTENSITY_SCALE = 3.5  # global scaler of how big intensity appears
INTENSITY_MIN = 0.2  # min length to make sure something shows for user to grab on to (twice arrow height)
DIMENSION_MIN = 0.1  # min dimension that you can set a physical light dimension to using the manipulator
# defaults are from: `omni.flux.light_creator.widget/omni/flux/light_creator/widget/setup_ui.py`
DISTANT_LIGHT_INTENSITY = 25
SPHERE_LIGHT_INTENSITY = 100
RECT_LIGHT_INTENSITY = 400
DISK_LIGHT_INTENSITY = 500
CYLINDER_LIGHT_INTENSITY = 140

# Manipulator arrow mesh constants
ARROW_WIDTH = 0.03
ARROW_HEIGHT = 0.1
ARROW_P = [  # points
    # --- triangle 1 ---
    [ARROW_WIDTH, ARROW_WIDTH, 0],
    [-ARROW_WIDTH, ARROW_WIDTH, 0],
    [0, 0, ARROW_HEIGHT],
    # --- triangle 2 ---
    [ARROW_WIDTH, -ARROW_WIDTH, 0],
    [-ARROW_WIDTH, -ARROW_WIDTH, 0],
    [0, 0, ARROW_HEIGHT],
    # --- triangle 3 ---
    [ARROW_WIDTH, ARROW_WIDTH, 0],
    [ARROW_WIDTH, -ARROW_WIDTH, 0],
    [0, 0, ARROW_HEIGHT],
    # --- triangle 4 ---
    [-ARROW_WIDTH, ARROW_WIDTH, 0],
    [-ARROW_WIDTH, -ARROW_WIDTH, 0],
    [0, 0, ARROW_HEIGHT],
    # --- triangle 5 ---
    [ARROW_WIDTH, ARROW_WIDTH, 0],
    [-ARROW_WIDTH, ARROW_WIDTH, 0],
    [-ARROW_WIDTH, -ARROW_WIDTH, 0],
    [ARROW_WIDTH, -ARROW_WIDTH, 0],
]

ARROW_VC = [3, 3, 3, 3, 4]  # faces
ARROW_VI = list(range(sum(ARROW_VC)))  # indices
# length of line almost to tip of arrow but shorter to make sure line doesn't dull point
# when drawn
ARROW_TIP = ARROW_HEIGHT - 0.02

# Style settings, as kwargs
THICKNESS = 1
HOVER_THICKNESS = THICKNESS + 2
COLOR = cl.yellow
HOVER_COLOR = cl.yellow  # color for arrows and corner rectangles when hovered
CLEAR_COLOR = cl(0, 0, 0, 0)  # the key is that alpha is 0 here
DEFAULT_SHAPE_STYLE = {"thickness": THICKNESS, "color": COLOR}
DEFAULT_ARC_STYLE = {"thickness": THICKNESS, "color": COLOR, "wireframe": True, "sector": False}

SQUARE_WIDTH = 0.06
SQUARE_CENTER_TO_EDGE = 0.5 * SQUARE_WIDTH + 0.01 * THICKNESS
