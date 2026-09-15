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

import carb.windowing
import omni.appwindow
import omni.kit.test

from ... import camera_default as _camera_default_module
from ...camera_default import CameraDefault, _ViewportCameraManipulator


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
        manipulator._ViewportCameraManipulator__cursor_window = None
        manipulator._ViewportCameraManipulator__cursor_windowing = None
        manipulator._ViewportCameraManipulator__previous_cursor_mode = None
        manipulator.model = Mock()
        return manipulator

    async def test_camera_drag_captures_cursor_until_gesture_ends(self):
        # Arrange
        manipulator = self._make_manipulator(object())
        native_window = object()
        app_window = Mock()
        app_window.get_window.return_value = native_window
        windowing = Mock()
        windowing.get_cursor_mode.return_value = carb.windowing.CursorMode.HIDDEN
        calls = []
        windowing.set_cursor_mode.side_effect = lambda _window, mode: calls.append(mode)
        gesture = SimpleNamespace(
            on_began=Mock(side_effect=lambda: calls.append("began")),
            on_changed=Mock(),
            on_ended=Mock(side_effect=lambda: calls.append("ended")),
        )

        with (
            patch.object(_camera_default_module, "_CameraGestureBase", SimpleNamespace, create=True),
            patch.object(omni.appwindow, "get_default_app_window", return_value=app_window),
            patch.object(carb.windowing, "acquire_windowing_interface", return_value=windowing),
            patch.object(_camera_default_module, "_ensure_editable_camera", return_value=True),
            patch.object(manipulator, "_begin_interaction"),
            patch.object(manipulator, "_end_interaction"),
        ):
            manipulator._ViewportCameraManipulator__wrap_gesture_lifecycle(gesture)

            # Act
            gesture.on_began()
            gesture.on_ended()

        # Assert
        self.assertEqual(
            calls,
            [carb.windowing.CursorMode.DISABLED, "began", "ended", carb.windowing.CursorMode.HIDDEN],
        )
        windowing.get_cursor_mode.assert_called_once_with(native_window)

    async def test_camera_drag_repeated_capture_restores_original_cursor_mode(self):
        """Preserve the original cursor mode when another drag starts before cleanup."""

        # Arrange
        manipulator = self._make_manipulator(object())
        app_window = Mock()
        windowing = Mock()
        windowing.get_cursor_mode.side_effect = [carb.windowing.CursorMode.HIDDEN, carb.windowing.CursorMode.DISABLED]
        first_gesture = SimpleNamespace(on_began=Mock(), on_changed=Mock(), on_ended=Mock())
        second_gesture = SimpleNamespace(on_began=Mock(), on_changed=Mock(), on_ended=Mock())

        with (
            patch.object(_camera_default_module, "_CameraGestureBase", SimpleNamespace),
            patch.object(omni.appwindow, "get_default_app_window", return_value=app_window),
            patch.object(carb.windowing, "acquire_windowing_interface", return_value=windowing),
            patch.object(_camera_default_module, "_ensure_editable_camera", return_value=True),
            patch.object(manipulator, "_begin_interaction"),
            patch.object(manipulator, "_end_interaction"),
        ):
            manipulator._ViewportCameraManipulator__wrap_gesture_lifecycle(first_gesture)
            manipulator._ViewportCameraManipulator__wrap_gesture_lifecycle(second_gesture)
            first_gesture.on_began()

            # Act
            second_gesture.on_began()
            first_gesture.on_ended()
            second_gesture.on_ended()

        # Assert
        self.assertEqual(
            [call.args[1] for call in windowing.set_cursor_mode.call_args_list],
            [carb.windowing.CursorMode.DISABLED, carb.windowing.CursorMode.HIDDEN],
        )
        windowing.get_cursor_mode.assert_called_once_with(app_window.get_window.return_value)
        second_gesture.on_began.__wrapped__.assert_called_once_with()
        self.assertIsNone(manipulator._ViewportCameraManipulator__cursor_window)

    async def test_camera_scroll_gesture_does_not_capture_cursor(self):
        # Arrange
        class CameraDragGestureBase:
            pass

        class CameraScrollGesture(SimpleNamespace):
            pass

        manipulator = self._make_manipulator(object())
        gesture = CameraScrollGesture(on_began=Mock(), on_changed=Mock(), on_ended=Mock())

        with (
            patch.object(_camera_default_module, "_CameraGestureBase", CameraDragGestureBase),
            patch.object(omni.appwindow, "get_default_app_window") as get_default_app_window_mock,
            patch.object(carb.windowing, "acquire_windowing_interface") as acquire_windowing_interface_mock,
            patch.object(_camera_default_module, "_ensure_editable_camera", return_value=True),
            patch.object(manipulator, "_begin_interaction"),
            patch.object(manipulator, "_end_interaction"),
        ):
            manipulator._ViewportCameraManipulator__wrap_gesture_lifecycle(gesture)

            # Act
            gesture.on_began()
            gesture.on_ended()

        # Assert
        gesture.on_began.__wrapped__.assert_called_once_with()
        gesture.on_ended.__wrapped__.assert_called_once_with()
        get_default_app_window_mock.assert_not_called()
        acquire_windowing_interface_mock.assert_not_called()

    async def test_camera_drag_without_native_window_does_not_capture_cursor(self):
        # Arrange
        manipulator = self._make_manipulator(object())
        app_window = Mock()
        app_window.get_window.return_value = None
        gesture = SimpleNamespace(on_began=Mock(), on_changed=Mock(), on_ended=Mock())

        with (
            patch.object(_camera_default_module, "_CameraGestureBase", SimpleNamespace),
            patch.object(omni.appwindow, "get_default_app_window", return_value=app_window),
            patch.object(carb.windowing, "acquire_windowing_interface") as acquire_windowing_interface_mock,
            patch.object(_camera_default_module, "_ensure_editable_camera", return_value=True),
            patch.object(manipulator, "_begin_interaction"),
            patch.object(manipulator, "_end_interaction"),
        ):
            manipulator._ViewportCameraManipulator__wrap_gesture_lifecycle(gesture)

            # Act
            gesture.on_began()
            gesture.on_ended()

        # Assert
        gesture.on_began.__wrapped__.assert_called_once_with()
        gesture.on_ended.__wrapped__.assert_called_once_with()
        app_window.get_window.assert_called_once_with()
        acquire_windowing_interface_mock.assert_not_called()

    async def test_camera_drag_cursor_mode_read_error_ends_interaction_without_setting_cursor(self):
        """Preserve the mode read failure and end the interaction without restoring an unknown cursor mode."""

        # Arrange
        stage = object()
        token = object()
        manipulator = self._make_manipulator(stage)
        app_window = Mock()
        windowing = Mock()
        windowing.get_cursor_mode.side_effect = RuntimeError("cursor mode read failed")
        base_on_began = Mock()
        gesture = SimpleNamespace(on_began=base_on_began, on_changed=Mock(), on_ended=Mock())

        with (
            patch.object(_camera_default_module, "_CameraGestureBase", SimpleNamespace),
            patch.object(omni.appwindow, "get_default_app_window", return_value=app_window),
            patch.object(carb.windowing, "acquire_windowing_interface", return_value=windowing),
            patch.object(_camera_default_module, "_ensure_editable_camera", return_value=True),
            patch.object(_camera_default_module, "_begin_interaction", return_value=token),
            patch.object(_camera_default_module, "_end_interaction") as end_interaction_mock,
        ):
            manipulator._ViewportCameraManipulator__wrap_gesture_lifecycle(gesture)

            # Act
            with self.assertRaisesRegex(RuntimeError, "cursor mode read failed"):
                gesture.on_began()

        # Assert
        windowing.get_cursor_mode.assert_called_once_with(app_window.get_window.return_value)
        windowing.set_cursor_mode.assert_not_called()
        base_on_began.assert_not_called()
        end_interaction_mock.assert_called_once_with(token)
        self.assertIsNone(manipulator._ViewportCameraManipulator__notice_interaction)

    async def test_camera_drag_on_began_error_restores_cursor(self):
        # Arrange
        manipulator = self._make_manipulator(object())
        native_window = object()
        app_window = Mock()
        app_window.get_window.return_value = native_window
        windowing = Mock()
        windowing.get_cursor_mode.return_value = carb.windowing.CursorMode.HIDDEN
        gesture = SimpleNamespace(
            on_began=Mock(side_effect=RuntimeError("gesture failed")), on_changed=Mock(), on_ended=Mock()
        )

        with (
            patch.object(_camera_default_module, "_CameraGestureBase", SimpleNamespace),
            patch.object(omni.appwindow, "get_default_app_window", return_value=app_window),
            patch.object(carb.windowing, "acquire_windowing_interface", return_value=windowing),
            patch.object(_camera_default_module, "_ensure_editable_camera", return_value=True),
            patch.object(manipulator, "_begin_interaction"),
            patch.object(manipulator, "_end_interaction"),
        ):
            manipulator._ViewportCameraManipulator__wrap_gesture_lifecycle(gesture)

            # Act
            with self.assertRaises(RuntimeError):
                gesture.on_began()

        # Assert
        self.assertEqual(
            [call.args[1] for call in windowing.set_cursor_mode.call_args_list],
            [carb.windowing.CursorMode.DISABLED, carb.windowing.CursorMode.HIDDEN],
        )
        self.assertIsNone(manipulator._ViewportCameraManipulator__cursor_window)

    async def test_camera_drag_on_changed_error_restores_cursor(self):
        # Arrange
        manipulator = self._make_manipulator(object())
        native_window = object()
        app_window = Mock()
        app_window.get_window.return_value = native_window
        windowing = Mock()
        windowing.get_cursor_mode.return_value = carb.windowing.CursorMode.HIDDEN
        gesture = SimpleNamespace(
            on_began=Mock(), on_changed=Mock(side_effect=RuntimeError("gesture failed")), on_ended=Mock()
        )

        with (
            patch.object(_camera_default_module, "_CameraGestureBase", SimpleNamespace),
            patch.object(omni.appwindow, "get_default_app_window", return_value=app_window),
            patch.object(carb.windowing, "acquire_windowing_interface", return_value=windowing),
            patch.object(_camera_default_module, "_ensure_editable_camera", return_value=True),
            patch.object(manipulator, "_begin_interaction"),
            patch.object(manipulator, "_end_interaction"),
        ):
            manipulator._ViewportCameraManipulator__wrap_gesture_lifecycle(gesture)
            gesture.on_began()

            # Act
            with self.assertRaises(RuntimeError):
                gesture.on_changed()

        # Assert
        self.assertEqual(
            [call.args[1] for call in windowing.set_cursor_mode.call_args_list],
            [carb.windowing.CursorMode.DISABLED, carb.windowing.CursorMode.HIDDEN],
        )
        self.assertIsNone(manipulator._ViewportCameraManipulator__cursor_window)

    async def test_camera_drag_restore_error_still_ends_interaction(self):
        # Arrange
        manipulator = self._make_manipulator(object())
        gesture = SimpleNamespace(
            on_began=Mock(), on_changed=Mock(side_effect=RuntimeError("gesture failed")), on_ended=Mock()
        )

        with (
            patch.object(_camera_default_module, "_CameraGestureBase", SimpleNamespace),
            patch.object(_camera_default_module, "_ensure_editable_camera", return_value=True),
            patch.object(manipulator, "_begin_interaction"),
            patch.object(manipulator, "_end_interaction") as end_interaction_mock,
            patch.object(manipulator, "_ViewportCameraManipulator__capture_cursor"),
            patch.object(
                manipulator,
                "_ViewportCameraManipulator__restore_cursor",
                side_effect=RuntimeError("cursor restore failed"),
            ),
        ):
            manipulator._ViewportCameraManipulator__wrap_gesture_lifecycle(gesture)
            gesture.on_began()

            # Act
            with self.assertRaisesRegex(RuntimeError, "cursor restore failed"):
                gesture.on_changed()

        # Assert
        end_interaction_mock.assert_called_once_with()

    async def test_destroy_restores_cursor_from_active_camera_drag(self):
        # Arrange
        manipulator = self._make_manipulator(object())
        native_window = object()
        app_window = Mock()
        app_window.get_window.return_value = native_window
        windowing = Mock()
        windowing.get_cursor_mode.return_value = carb.windowing.CursorMode.HIDDEN
        gesture = SimpleNamespace(on_began=Mock(), on_changed=Mock(), on_ended=Mock())

        with (
            patch.object(_camera_default_module, "_CameraGestureBase", SimpleNamespace),
            patch.object(omni.appwindow, "get_default_app_window", return_value=app_window),
            patch.object(carb.windowing, "acquire_windowing_interface", return_value=windowing),
            patch.object(_camera_default_module, "_ensure_editable_camera", return_value=True),
            patch.object(manipulator, "_begin_interaction"),
            patch.object(manipulator, "_end_interaction"),
            patch.object(_camera_default_module._BaseViewportCameraManipulator, "destroy"),
        ):
            manipulator._ViewportCameraManipulator__wrap_gesture_lifecycle(gesture)
            gesture.on_began()

            # Act
            manipulator.destroy()

        # Assert
        self.assertEqual(
            [call.args[1] for call in windowing.set_cursor_mode.call_args_list],
            [carb.windowing.CursorMode.DISABLED, carb.windowing.CursorMode.HIDDEN],
        )
        self.assertIsNone(manipulator._ViewportCameraManipulator__cursor_window)

    async def test_destroy_end_interaction_error_still_destroys_base_manipulator(self):
        # Arrange
        manipulator = self._make_manipulator(object())

        with (
            patch.object(manipulator, "_end_interaction", side_effect=RuntimeError("end interaction failed")),
            patch.object(_camera_default_module._BaseViewportCameraManipulator, "destroy") as destroy_mock,
        ):
            # Act
            with self.assertRaisesRegex(RuntimeError, "end interaction failed"):
                manipulator.destroy()

        # Assert
        destroy_mock.assert_called_once_with()

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

    async def test_camera_default_leaves_scroll_zoom_to_shared_viewport_delegate(self):
        """The default camera manipulator should not also own mouse-wheel zoom."""

        # Arrange
        viewport_api = object()
        camera_default = CameraDefault.__new__(CameraDefault)
        camera_default._IManipulator__viewport_api = viewport_api
        model = SimpleNamespace(
            set_floats=Mock(),
            set_ints=Mock(),
        )
        manipulator = SimpleNamespace(model=model)

        with (
            patch.object(_camera_default_module, "_ViewportCameraManipulator", return_value=manipulator) as factory,
            patch("omni.kit.app.SettingChangeSubscription", return_value=object()),
        ):
            # Act
            camera_default._create_manipulator()

        # Assert
        factory.assert_called_once()
        self.assertIs(factory.call_args.args[0], viewport_api)
        self.assertIn("bindings", factory.call_args.kwargs)
        bindings = factory.call_args.kwargs["bindings"]
        self.assertIn("PanGesture", bindings)
        self.assertNotIn("ZoomScrollGesture", bindings)
