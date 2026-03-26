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

Name-based style configuration for FCurve widget.

All colors are 0xAABBGGRR (omni.ui ABGR convention).
"""

from __future__ import annotations

__all__ = ["DEFAULT_STYLE"]

DEFAULT_STYLE: dict[str, dict] = {
    # ── Keyframe handles ─────────────────────────────────────────────────────
    "Rectangle::FCurveKey": {
        "background_color": 0xFFFFFFFF,
        "border_radius": 2,
    },
    "Rectangle::FCurveKeySelected": {
        "background_color": 0xFFFFAA00,
    },
    "Rectangle::FCurveKeyHovered": {
        "background_color": 0xFFCCCCCC,
    },
    "FreeLine::FCurveKeyGhost": {
        "color": 0x60FFFFFF,
        "border_width": 1.0,
    },
    # ── Tangent handles ──────────────────────────────────────────────────────
    "Rectangle::FCurveTangent": {
        "background_color": 0xFF82DCFF,
    },
    "FreeLine::FCurveTangentLine": {
        "color": 0xFF82DCFF,
        "border_width": 1.0,
    },
    # ── Curve segments ───────────────────────────────────────────────────────
    "FreeBezierCurve::FCurveSegment": {
        "border_width": 1.5,
    },
    "FreeLine::FCurveSegment": {
        "border_width": 1.5,
    },
    "FreeLine::FCurveInfinity": {
        "border_width": 1.0,
    },
}
