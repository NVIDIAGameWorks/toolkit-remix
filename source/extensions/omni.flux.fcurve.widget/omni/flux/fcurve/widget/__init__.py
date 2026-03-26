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

omni.flux.fcurve.widget - Function curve widget for Flux applications.

A reusable, self-contained widget for rendering and editing bezier curves.
Can be embedded in any ui.Frame with no external dependencies on data storage.

Public API:
    FCurveWidget: Main widget class
    FCurve: Curve data container
    FCurveKey: Keyframe data
    DEFAULT_STYLE: Default style dict for visual configuration
    TangentType: Tangent interpolation modes
    InfinityType: Curve extrapolation modes
    KeyReference: Keyframe identifier
    TangentReference: Tangent handle identifier
    SelectionInfo: Selection state for UI updates

Event payloads:
    KeyChangedEvent: Keyframe modified
    KeyAddedEvent: Keyframe added
    KeyDeletedEvent: Keyframe deleted
    TangentChangedEvent: Tangent modified
    SelectionChangedEvent: Selection changed

Example:
    >>> from omni.flux.fcurve.widget import FCurveWidget, FCurve, FCurveKey
    >>>
    >>> # Create widget inside ui context (builds automatically)
    >>> with ui.Frame():
    ...     widget = FCurveWidget(time_range=(0.0, 1.0), value_range=(0.0, 1.0))
    >>>
    >>> # Set curve data
    >>> widget.set_curves({
    ...     "curve1": FCurve(
    ...         id="curve1",
    ...         keys=[FCurveKey(time=0.0, value=0.0), FCurveKey(time=1.0, value=1.0)],
    ...         color=0xFF00FF00,
    ...     )
    ... })
    >>>
    >>> # Subscribe to events
    >>> sub = widget.subscribe_key_changed(lambda e: print(f"Key changed: {e}"))
"""

from .fcurve_widget import FCurveWidget
from .model import (
    # Data types
    FCurve,
    FCurveKey,
    CurveBounds,
    TangentType,
    InfinityType,
    KeyReference,
    TangentReference,
    SelectionInfo,
    # Event payloads
    KeyChangedEvent,
    KeyAddedEvent,
    KeyDeletedEvent,
    TangentChangedEvent,
    SelectionChangedEvent,
)
from .style import DEFAULT_STYLE

__all__ = [
    "DEFAULT_STYLE",
    "CurveBounds",
    "FCurve",
    "FCurveKey",
    "FCurveWidget",
    "InfinityType",
    "KeyAddedEvent",
    "KeyChangedEvent",
    "KeyDeletedEvent",
    "KeyReference",
    "SelectionChangedEvent",
    "SelectionInfo",
    "TangentChangedEvent",
    "TangentReference",
    "TangentType",
]
