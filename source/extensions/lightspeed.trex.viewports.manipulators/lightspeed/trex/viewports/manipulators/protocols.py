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

from collections.abc import Callable, Sequence
from typing import Any, Protocol

from pxr import Usd

__all__ = ["CameraGestureProtocol", "GestureScreenProtocol", "ViewportAPIProtocol"]


class ViewportAPIProtocol(Protocol):
    """Viewport API surface used by viewport manipulators.

    Attributes:
        usd_context_name: Name of the USD context owned by the viewport.
        stage: Stage currently displayed by the viewport, when one is available.
    """

    usd_context_name: str
    stage: Usd.Stage | None


class CameraGestureProtocol(Protocol):
    """Camera gesture lifecycle callbacks wrapped by the camera manipulator.

    Attributes:
        on_began: Callback fired when a gesture starts.
        on_changed: Callback fired while a gesture changes.
        on_ended: Callback fired when a gesture ends.
    """

    on_began: Callable[..., Any]
    on_changed: Callable[..., Any]
    on_ended: Callable[..., Any]


class GestureScreenProtocol(Protocol):
    """Screen object exposing camera gestures.

    Attributes:
        gestures: Camera gestures owned by the screen.
    """

    gestures: Sequence[CameraGestureProtocol]
