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

from types import SimpleNamespace
from unittest.mock import Mock, patch

import omni.kit.test

from ... import zoom as _zoom_module


class TestZoomOperation(omni.kit.test.AsyncTestCase):
    async def test_zoom_operation_cancels_when_game_camera_redirect_fails(self):
        # Arrange
        viewport_api = object()

        with (
            patch.object(_zoom_module, "_ensure_editable_camera", return_value=False) as ensure_editable_mock,
            patch.object(_zoom_module, "_ViewportCameraManipulator") as manipulator_mock,
        ):
            # Act
            result = _zoom_module.zoom_operation(0, 1.0, viewport_api)

        # Assert
        self.assertFalse(result)
        ensure_editable_mock.assert_called_once_with(viewport_api, "Mouse-wheel zoom")
        manipulator_mock.assert_not_called()

    async def test_zoom_operation_uses_single_redirect_guard_before_synthetic_gesture(self):
        # Arrange
        viewport_api = object()
        gesture = SimpleNamespace(
            _disable_flight=Mock(),
            on_began=Mock(),
            on_changed=Mock(),
            on_ended=Mock(),
        )
        manipulator = SimpleNamespace(
            _screen=SimpleNamespace(gestures=[gesture]),
            model=Mock(),
            on_build=Mock(),
            destroy=Mock(),
        )
        manipulator.model.get_as_floats.return_value = [0.0, 0.0, -10.0]

        with (
            patch.object(_zoom_module, "_ensure_editable_camera", return_value=True) as ensure_editable_mock,
            patch.object(_zoom_module, "_ViewportCameraManipulator", return_value=manipulator) as manipulator_mock,
        ):
            # Act
            result = _zoom_module.zoom_operation(2.0, 4.0, viewport_api)

        # Assert
        self.assertTrue(result)
        ensure_editable_mock.assert_called_once_with(viewport_api, "Mouse-wheel zoom")
        manipulator_mock.assert_called_once_with(
            viewport_api,
            bindings={"ZoomGesture": "LeftButton"},
            ensure_editable_camera=False,
        )
        manipulator.on_build.assert_called_once()
        gesture._disable_flight.assert_called_once()
        gesture.on_began.assert_called_once_with([0, 0])
        gesture.on_changed.assert_called_once()
        gesture.on_ended.assert_called_once()
        manipulator.destroy.assert_called_once()
