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

Internal implementation of FCurve widget.

This package contains the private implementation details of FCurveWidget.
External code should not import from this package directly.
"""

from .curve_widgets_manager import CurveWidgetsManager
from .handle_widget import HandleWidget
from .infinity_curve_widget import InfinityCurveWidget
from .segment_widget import SegmentMode, SegmentWidget
from .viewport import ViewportState

__all__ = [
    "CurveWidgetsManager",
    "HandleWidget",
    "InfinityCurveWidget",
    "SegmentMode",
    "SegmentWidget",
    "ViewportState",
]
