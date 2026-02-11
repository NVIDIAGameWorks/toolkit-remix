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

from typing import Any

import carb
import omni.kit.app
from omni.kit.manipulator.camera import ViewportCameraManipulator as _ViewportCameraManipulator

from .interface.i_manipulator import IManipulator


class CameraDefault(IManipulator):
    VP1_CAM_VELOCITY = "/persistent/app/viewport/camMoveVelocity"
    VP1_CAM_INERTIA_ENABLED = "/persistent/app/viewport/camInertiaEnabled"
    VP1_CAM_INERTIA_SEC = "/persistent/app/viewport/camInertiaAmount"
    VP1_CAM_ROTATIONAL_STEP = "/persistent/app/viewport/camFreeRotationStep"
    VP1_CAM_LOOK_SPEED = "/persistent/app/viewport/camYawPitchSpeed"

    VP2_FLY_ACCELERATION = "/persistent/app/viewport/manipulator/camera/flyAcceleration"
    VP2_FLY_DAMPENING = "/persistent/app/viewport/manipulator/camera/flyDampening"
    VP2_LOOK_ACCELERATION = "/persistent/app/viewport/manipulator/camera/lookAcceleration"
    VP2_LOOK_DAMPENING = "/persistent/app/viewport/manipulator/camera/lookDampening"

    def __init__(self, viewport_api):
        self.__setting_subs = None
        super().__init__(viewport_api)

    def _create_manipulator(self):
        self.__manipulator = _ViewportCameraManipulator(self.viewport_api)

        def setting_changed(value, event_type, set_fn):
            if event_type != carb.settings.ChangeEventType.CHANGED:
                return
            set_fn(value.get("", None))

        self.__setting_subs = (
            omni.kit.app.SettingChangeSubscription(
                CameraDefault.VP1_CAM_VELOCITY, lambda *args: setting_changed(*args, self.__set_flight_velocity)
            ),
            omni.kit.app.SettingChangeSubscription(
                CameraDefault.VP1_CAM_INERTIA_ENABLED, lambda *args: setting_changed(*args, self.__set_inertia_enabled)
            ),
            omni.kit.app.SettingChangeSubscription(
                CameraDefault.VP1_CAM_INERTIA_SEC, lambda *args: setting_changed(*args, self.__set_inertia_seconds)
            ),
            omni.kit.app.SettingChangeSubscription(
                CameraDefault.VP2_FLY_ACCELERATION, lambda *args: setting_changed(*args, self.__set_flight_acceleration)
            ),
            omni.kit.app.SettingChangeSubscription(
                CameraDefault.VP2_FLY_DAMPENING, lambda *args: setting_changed(*args, self.__set_flight_dampening)
            ),
            omni.kit.app.SettingChangeSubscription(
                CameraDefault.VP2_LOOK_ACCELERATION, lambda *args: setting_changed(*args, self.__set_look_acceleration)
            ),
            omni.kit.app.SettingChangeSubscription(
                CameraDefault.VP2_LOOK_DAMPENING, lambda *args: setting_changed(*args, self.__set_look_dampening)
            ),
        )
        settings = carb.settings.get_settings()
        settings.set_default(CameraDefault.VP1_CAM_VELOCITY, 5.0)
        settings.set_default(CameraDefault.VP1_CAM_INERTIA_ENABLED, False)
        settings.set_default(CameraDefault.VP1_CAM_INERTIA_SEC, 0.55)

        settings.set_default(CameraDefault.VP2_FLY_ACCELERATION, 1000.0)
        settings.set_default(CameraDefault.VP2_FLY_DAMPENING, 10.0)
        settings.set_default(CameraDefault.VP2_LOOK_ACCELERATION, 2000.0)
        settings.set_default(CameraDefault.VP2_LOOK_DAMPENING, 20.0)

        self.__set_flight_velocity(settings.get(CameraDefault.VP1_CAM_VELOCITY))
        self.__set_inertia_enabled(settings.get(CameraDefault.VP1_CAM_INERTIA_ENABLED))
        self.__set_inertia_seconds(settings.get(CameraDefault.VP1_CAM_INERTIA_SEC))

        self.__set_flight_acceleration(settings.get(CameraDefault.VP2_FLY_ACCELERATION))
        self.__set_flight_dampening(settings.get(CameraDefault.VP2_FLY_DAMPENING))
        self.__set_look_acceleration(settings.get(CameraDefault.VP2_LOOK_ACCELERATION))
        self.__set_look_dampening(settings.get(CameraDefault.VP2_LOOK_DAMPENING))

        return self.__manipulator

    def _model_changed(self, model, item):
        pass

    def __set_inertia_enabled(self, value):
        if value is not None:
            self.__manipulator.model.set_ints("inertia_enabled", [1 if value else 0])

    def __set_inertia_seconds(self, value):
        if value is not None:
            self.__manipulator.model.set_floats("inertia_seconds", [value])

    def __set_flight_velocity(self, value):
        if value is not None:
            self.__manipulator.model.set_floats("fly_speed", [value])

    def __set_flight_acceleration(self, value):
        if value is not None:
            self.__manipulator.model.set_floats("fly_acceleration", [value, value, value])

    def __set_flight_dampening(self, value):
        if value is not None:
            self.__manipulator.model.set_floats("fly_dampening", [10, 10, 10])

    def __set_look_acceleration(self, value):
        if value is not None:
            self.__manipulator.model.set_floats("look_acceleration", [value, value, value])

    def __set_look_dampening(self, value):
        if value is not None:
            self.__manipulator.model.set_floats("look_dampening", [value, value, value])

    def destroy(self):
        self.__setting_subs = None
        if self.__manipulator:
            self.__manipulator.destroy()
            self.__manipulator = None
        super().destroy()

    @property
    def categories(self):
        return ["manipulator"]

    @property
    def name(self):
        return "Camera"

    def manipulator(self):
        return self.__manipulator


def camera_default_factory(desc: dict[str, Any]):
    manip = CameraDefault(desc.get("viewport_api"))
    return manip
