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

import math

from pxr import Gf

from .camera_default import _ViewportCameraManipulator

__all__ = ["zoom_operation"]


class _ZoomEvents:
    def __init__(self, viewport_api):
        self.__mouse = [0, 0]
        self.__manipulator = _ViewportCameraManipulator(viewport_api, bindings={"ZoomGesture": "LeftButton"})
        self.__manipulator.on_build()
        # Upstream's mouse-wheel zoom helper uses these private members; there is no public API to get the
        # synthetic zoom gesture or disable its flight-mode setup.
        self.__zoom_gesture = self.__manipulator._screen.gestures[0]  # noqa: SLF001
        self.__zoom_gesture._disable_flight()  # noqa: SLF001
        self.__zoom_gesture.on_began(self.__mouse)

    def update(self, x, y):
        coi = Gf.Vec3d(*self.__manipulator.model.get_as_floats("center_of_interest"))
        scale = math.log10(max(10, coi.GetLength())) / 40
        self.__mouse = [self.__mouse[0] + x * scale, self.__mouse[1] + y * scale]
        self.__zoom_gesture.on_changed(self.__mouse)

    def destroy(self):
        self.__zoom_gesture.on_ended()
        self.__manipulator.destroy()


def zoom_operation(x, y, viewport_api):
    """Apply a mouse-wheel zoom through the camera manipulator gesture.

    Args:
        x: Horizontal mouse-wheel delta.
        y: Vertical mouse-wheel delta.
        viewport_api: Viewport API whose active camera should be zoomed.

    Returns:
        True when zoom was applied, or None when no viewport API was available.
    """

    if not viewport_api:
        return None
    zoom_events = _ZoomEvents(viewport_api)
    try:
        zoom_events.update(x, y)
    finally:
        zoom_events.destroy()
    return True
