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

Canvas components for the curve editor.

Contains:
- CurveEditorCanvas: Main canvas hosting FCurveWidget with pan/zoom
- GridRenderer: Adaptive grid line rendering
- TimelineRuler: Time labels at top of canvas
- ViewportState: Coordinate transformation and pan/zoom state
- Tick utilities: Shared interval calculation (ticks module)
"""

from .main import CurveEditorCanvas
from .grid import GridRenderer
from .rulers import Ruler, RulerOrientation, TimelineRuler, ValueRuler
from .viewport import ViewportState
from .ticks import TickInfo, TickConfig, compute_nice_interval, generate_ticks

__all__ = [
    "CurveEditorCanvas",
    "GridRenderer",
    "Ruler",
    "RulerOrientation",
    "TickConfig",
    "TickInfo",
    "TimelineRuler",
    "ValueRuler",
    "ViewportState",
    "compute_nice_interval",
    "generate_ticks",
]
