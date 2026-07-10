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


class _TestableViewportCameraManipulator(_ViewportCameraManipulator):
    @property
    def model(self):
        return self._model_mock

    @model.setter
    def model(self, value):
        self._model_mock = value


class TestCameraDefault(omni.kit.test.AsyncTestCase):
    @staticmethod
    def _make_manipulator(stage):
        manipulator = _TestableViewportCameraManipulator.__new__(_TestableViewportCameraManipulator)
        manipulator._ViewportCameraManipulator__viewport_api = SimpleNamespace(
            usd_context_name="", stage=stage, camera_path="/OmniverseKit_Persp"
        )
        manipulator._ViewportCameraManipulator__ensure_editable_camera = True
        manipulator._ViewportCameraManipulator__notice_interaction = None
        manipulator._ViewportCameraManipulator__wrapped_gesture_ids = set()
        manipulator.model = Mock()
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

    async def test_wrapped_on_began_disables_rotation_for_pseudo_orthographic_camera(self):
        # Arrange
        stage = object()
        manipulator = self._make_manipulator(stage)
        manipulator._ViewportCameraManipulator__viewport_api.camera_path = "/OmniverseKit_Top"

        def base_on_began():
            manipulator.model.set_ints("disable_tumble", [0])
            manipulator.model.set_ints("disable_look", [0])
            return "began"

        gesture = SimpleNamespace(on_began=Mock(side_effect=base_on_began), on_changed=Mock(), on_ended=Mock())

        with patch.object(_camera_default_module, "_lock_pseudo_orthographic_camera_orientation") as lock_mock:
            manipulator._ViewportCameraManipulator__wrap_gesture_lifecycle(gesture)

            # Act
            result = gesture.on_began()

        # Assert
        self.assertEqual(result, "began")
        disable_tumble_calls = [
            call for call in manipulator.model.set_ints.call_args_list if call.args[0] == "disable_tumble"
        ]
        disable_look_calls = [
            call for call in manipulator.model.set_ints.call_args_list if call.args[0] == "disable_look"
        ]
        self.assertEqual(disable_tumble_calls[-1].args[1], [1])
        self.assertEqual(disable_look_calls[-1].args[1], [1])
        manipulator.model.set_ints.assert_any_call("disable_pan", [0])
        manipulator.model.set_ints.assert_any_call("disable_zoom", [0])
        lock_mock.assert_called_once_with(stage, "/OmniverseKit_Top")

    async def test_wrapped_on_began_reenables_rotation_for_regular_perspective_camera(self):
        # Arrange
        stage = object()
        manipulator = self._make_manipulator(stage)
        manipulator._ViewportCameraManipulator__viewport_api.camera_path = "/OmniverseKit_Persp"

        def base_on_began():
            manipulator.model.set_ints("disable_tumble", [1])
            manipulator.model.set_ints("disable_look", [1])
            return "began"

        gesture = SimpleNamespace(on_began=Mock(side_effect=base_on_began), on_changed=Mock(), on_ended=Mock())

        with patch.object(_camera_default_module, "_lock_pseudo_orthographic_camera_orientation") as lock_mock:
            manipulator._ViewportCameraManipulator__wrap_gesture_lifecycle(gesture)

            # Act
            result = gesture.on_began()

        # Assert
        self.assertEqual(result, "began")
        disable_tumble_calls = [
            call for call in manipulator.model.set_ints.call_args_list if call.args[0] == "disable_tumble"
        ]
        disable_look_calls = [
            call for call in manipulator.model.set_ints.call_args_list if call.args[0] == "disable_look"
        ]
        self.assertEqual(disable_tumble_calls[-1].args[1], [0])
        self.assertEqual(disable_look_calls[-1].args[1], [0])
        lock_mock.assert_not_called()

    async def test_wrapped_on_began_redirects_game_camera_before_gesture(self):
        # Arrange
        stage = object()
        manipulator = self._make_manipulator(stage)
        viewport_api = manipulator._ViewportCameraManipulator__viewport_api
        viewport_api.camera_path = "/RootNode/Camera"
        calls = []

        def ensure_editable(_viewport_api, _action_name):
            calls.append(("ensure", _viewport_api))
            _viewport_api.camera_path = "/OmniverseKit_Persp"
            return True

        def base_on_began():
            calls.append(("began", None))
            return "began"

        gesture = SimpleNamespace(on_began=Mock(side_effect=base_on_began), on_changed=Mock(), on_ended=Mock())

        with (
            patch.object(_camera_default_module, "_ensure_editable_camera", side_effect=ensure_editable),
            patch.object(_camera_default_module, "_lock_pseudo_orthographic_camera_orientation") as lock_mock,
        ):
            manipulator._ViewportCameraManipulator__wrap_gesture_lifecycle(gesture)

            # Act
            result = gesture.on_began()

        # Assert
        self.assertEqual(result, "began")
        self.assertEqual(calls, [("ensure", viewport_api), ("began", None)])
        lock_mock.assert_not_called()

    async def test_wrapped_on_began_cancels_game_camera_gesture_when_redirect_fails(self):
        # Arrange
        stage = object()
        token = object()
        manipulator = self._make_manipulator(stage)
        viewport_api = manipulator._ViewportCameraManipulator__viewport_api
        viewport_api.camera_path = "/RootNode/Camera"
        base_on_began = Mock(return_value="began")
        gesture = SimpleNamespace(on_began=base_on_began, on_changed=Mock(), on_ended=Mock())

        with (
            patch.object(_camera_default_module, "_begin_interaction", return_value=token) as begin_interaction_mock,
            patch.object(_camera_default_module, "_end_interaction") as end_interaction_mock,
            patch.object(_camera_default_module, "_ensure_editable_camera", return_value=False),
        ):
            manipulator._ViewportCameraManipulator__wrap_gesture_lifecycle(gesture)

            # Act
            result = gesture.on_began()

        # Assert
        self.assertIsNone(result)
        base_on_began.assert_not_called()
        begin_interaction_mock.assert_called_once_with(stage)
        end_interaction_mock.assert_called_once_with(token)
        self.assertIsNone(manipulator._ViewportCameraManipulator__notice_interaction)

    async def test_wrapped_on_changed_does_not_lock_pseudo_orthographic_camera_during_gesture_update(self):
        # Arrange
        stage = object()
        manipulator = self._make_manipulator(stage)
        manipulator._ViewportCameraManipulator__viewport_api.camera_path = "/OmniverseKit_Top"
        gesture = SimpleNamespace(on_began=Mock(), on_changed=Mock(return_value="changed"), on_ended=Mock())

        with patch.object(_camera_default_module, "_lock_pseudo_orthographic_camera_orientation") as lock_mock:
            manipulator._ViewportCameraManipulator__wrap_gesture_lifecycle(gesture)

            # Act
            result = gesture.on_changed()

        # Assert
        self.assertEqual(result, "changed")
        lock_mock.assert_not_called()

    async def test_wrapped_on_ended_locks_pseudo_orthographic_camera_after_gesture_update(self):
        # Arrange
        stage = object()
        manipulator = self._make_manipulator(stage)
        manipulator._ViewportCameraManipulator__viewport_api.camera_path = "/OmniverseKit_Top"
        gesture = SimpleNamespace(on_began=Mock(), on_changed=Mock(), on_ended=Mock(return_value="ended"))

        with patch.object(_camera_default_module, "_lock_pseudo_orthographic_camera_orientation") as lock_mock:
            manipulator._ViewportCameraManipulator__wrap_gesture_lifecycle(gesture)

            # Act
            result = gesture.on_ended()

        # Assert
        self.assertEqual(result, "ended")
        lock_mock.assert_called_once_with(stage, "/OmniverseKit_Top")
