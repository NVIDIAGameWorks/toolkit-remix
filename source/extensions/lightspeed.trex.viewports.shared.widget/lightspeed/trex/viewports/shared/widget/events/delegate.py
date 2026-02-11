"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["ViewportEventDelegate"]

import contextlib
import math
import traceback

import carb


def _limit_camera_velocity(value: float, settings: carb.settings.ISettings, context_name: str):
    cam_limit = settings.get("/exts/omni.kit.viewport.window/cameraSpeedLimit")
    if context_name in cam_limit:
        vel_min = settings.get("/persistent/app/viewport/camVelocityMin")
        if vel_min is not None:
            value = max(vel_min, value)
        vel_max = settings.get("/persistent/app/viewport/camVelocityMax")
        if vel_max is not None:
            value = min(vel_max, value)
    return value


class ViewportEventDelegate:
    def __init__(self, scene_view, viewport_api):
        self.__scene_view = scene_view
        self.__viewport_api = viewport_api
        scene_view.set_mouse_wheel_fn(self.mouse_wheel)
        scene_view.set_key_pressed_fn(self.key_pressed)
        scene_view.set_accept_drop_fn(self.drop_accept)
        scene_view.set_drop_fn(self.drop)
        scene_view.scroll_only_window_hovered = True
        self.__dd_handler = None
        self.__key_down = set()

    def destroy(self):
        scene_view = self.scene_view
        if scene_view:
            scene_view.set_mouse_wheel_fn(None)
            scene_view.set_key_pressed_fn(None)
            scene_view.set_accept_drop_fn(None)
            scene_view.set_drop_fn(None)
            self.__scene_view = None

    @property
    def scene_view(self):
        with contextlib.suppress(ReferenceError):
            if self.__scene_view:
                return self.__scene_view
        return None

    @property
    def viewport_api(self):
        with contextlib.suppress(ReferenceError):
            if self.__viewport_api:
                return self.__viewport_api
        return None

    @property
    def drag_drop_handler(self):
        return self.__dd_handler

    def adjust_flight_speed(self, x: float, y: float):
        try:
            import omni.appwindow  # noqa: PLC0415

            iinput = carb.input.acquire_input_interface()
            app_window = omni.appwindow.get_default_app_window()
            mouse = app_window.get_mouse()
            mouse_value = iinput.get_mouse_value(mouse, carb.input.MouseInput.RIGHT_BUTTON)
            if mouse_value > 0:
                settings = carb.settings.get_settings()
                value = settings.get("/persistent/app/viewport/camMoveVelocity") or 1
                scaler = settings.get("/persistent/app/viewport/camVelocityScalerMultAmount") or 1.1
                scaler = 1.0 + (max(scaler, 1.0 + 1e-8) - 1.0) * abs(y)
                if y < 0:
                    value = value / scaler
                elif y > 0:
                    value = value * scaler
                if math.isfinite(value) and (value > 1e-8):
                    value = _limit_camera_velocity(value, settings, "scroll")
                    settings.set("/persistent/app/viewport/camMoveVelocity", value)
                return True

            # OM-58310: orbit + scroll does not behave well together, but when scroll is moved to omni.ui.scene
            # they cannot both exists anyway, so disable this possibility for now by returning True if any button down
            return iinput.get_mouse_value(mouse, carb.input.MouseInput.LEFT_BUTTON) or iinput.get_mouse_value(
                mouse, carb.input.MouseInput.MIDDLE_BUTTON
            )

        except Exception:  # noqa: BLE001
            carb.log_error(f"Traceback:\n{traceback.format_exc()}")

        return False

    def mouse_wheel(self, x: float, y: float, modifiers: int):
        # Do not use horizontal scroll at all (do we want to hide this behind a setting, or allow it for speed
        # but not zoom)
        x = 0
        # Try to apply flight speed first (should be applied when flight-mode key is active)
        if self.adjust_flight_speed(x, y):
            return
        # If a key is down, ignore the wheel-event (i.e. don't zoom on paint b+scroll event)
        if self.__key_down:
            import omni.appwindow  # noqa: PLC0415

            app_window = omni.appwindow.get_default_app_window()
            key_input = carb.input.acquire_input_interface()
            keyboard = app_window.get_keyboard()
            app_window.get_keyboard()
            for key in self.__key_down:
                if key_input.get_keyboard_value(keyboard, key):
                    return
            self.__key_down = set()

        try:
            from omni.kit.manipulator.camera.viewport_camera_manipulator import _zoom_operation  # noqa: PLC0415

            _zoom_operation(x, y, self.viewport_api)
        except Exception:  # noqa: BLE001
            carb.log_error(f"Traceback:\n{traceback.format_exc()}")

    def key_pressed(self, key_index: int, modifiers: int, is_down: bool):
        # Ignore all key-modifier up/down events, only care about escape or blocking scroll with real-key
        if key_index >= int(carb.input.KeyboardInput.LEFT_SHIFT):
            return
        if key_index == int(carb.input.KeyboardInput.ESCAPE):
            self.stop_drag_drop()
            return
        if is_down:
            self.__key_down.add(carb.input.KeyboardInput(key_index))
        else:
            self.__key_down.discard(carb.input.KeyboardInput(key_index))

    def mouse_moved(self, x: float, y: float, modifiers: int, is_pressed: bool, *args):
        if self.__dd_handler:
            self.__dd_handler._perform_query(self.__scene_view, (x, y))  # noqa: SLF001

    def drop_accept(self, url: str):
        return False

    def drop(self, data):
        dd_handler = self.stop_drag_drop(False)
        if dd_handler:
            dd_handler.dropped(self.__scene_view, data)

    def mouse_hovered(self, value: bool, *args):
        if not value and self.__dd_handler:
            self.stop_drag_drop()

    def stop_drag_drop(self, cancel: bool = True):
        dd_handler, self.__dd_handler = self.__dd_handler, None
        self.__scene_view.set_mouse_moved_fn(None)
        self.__scene_view.set_mouse_hovered_fn(None)
        if dd_handler and cancel:
            dd_handler.cancel(self)
        return dd_handler
