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

from ... import camera_default as _camera_default_module
from ...camera_default import _ViewportCameraManipulator


class TestCameraDefault(omni.kit.test.AsyncTestCase):
    @staticmethod
    def _make_manipulator(stage):
        manipulator = _ViewportCameraManipulator.__new__(_ViewportCameraManipulator)
        manipulator._ViewportCameraManipulator__viewport_api = SimpleNamespace(usd_context_name="", stage=stage)
        manipulator._ViewportCameraManipulator__notice_interaction = None
        manipulator._ViewportCameraManipulator__wrapped_gesture_ids = set()
        return manipulator

    async def test_wrapped_on_changed_ends_interaction_if_gesture_raises(self):
        # Arrange
        stage = object()
        token = object()
        manipulator = self._make_manipulator(stage)
        gesture = SimpleNamespace(
            on_began=Mock(),
            on_changed=Mock(side_effect=RuntimeError("gesture failed")),
            on_ended=Mock(),
        )

        with (
            patch.object(_camera_default_module, "_begin_interaction", return_value=token) as begin_interaction_mock,
            patch.object(_camera_default_module, "_end_interaction") as end_interaction_mock,
        ):
            manipulator._ViewportCameraManipulator__wrap_gesture_lifecycle(gesture)

            # Act
            with self.assertRaises(RuntimeError):
                gesture.on_changed()

        # Assert
        begin_interaction_mock.assert_called_once_with(stage)
        end_interaction_mock.assert_called_once_with(token)
        self.assertIsNone(manipulator._ViewportCameraManipulator__notice_interaction)
