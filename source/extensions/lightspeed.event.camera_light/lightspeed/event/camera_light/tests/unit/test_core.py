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

from unittest.mock import AsyncMock, call, patch

import carb
import omni.kit.app
from omni.kit.test import AsyncTestCase


class TestCore(AsyncTestCase):
    @staticmethod
    async def __wait_for_camera_light_task():
        for _ in range(2):
            await omni.kit.app.get_app().next_update_async()

    async def test_set_camera_light(self):
        settings = carb.settings.get_settings()
        with patch(
            "lightspeed.event.camera_light.core._hdremix_set_configvar_async", new_callable=AsyncMock
        ) as mock_set_configvar:
            settings.set("/rtx/useViewLightingMode", False)
            await self.__wait_for_camera_light_task()
            mock_set_configvar.reset_mock()

            settings.set("/rtx/useViewLightingMode", True)
            await self.__wait_for_camera_light_task()

            mock_set_configvar.assert_has_awaits(
                [
                    call("rtx.fallbackLightMode", "2"),
                    call("rtx.fallbackLightType", "1"),
                    call("rtx.fallbackLightRadiance", "50, 50, 50"),
                ]
            )

            settings.set("/rtx/useViewLightingMode", False)
            await self.__wait_for_camera_light_task()

    async def test_reset_camera_light(self):
        settings = carb.settings.get_settings()
        with patch(
            "lightspeed.event.camera_light.core._hdremix_set_configvar_async", new_callable=AsyncMock
        ) as mock_set_configvar:
            settings.set("/rtx/useViewLightingMode", True)
            await self.__wait_for_camera_light_task()
            mock_set_configvar.reset_mock()

            settings.set("/rtx/useViewLightingMode", False)
            await self.__wait_for_camera_light_task()

            mock_set_configvar.assert_has_awaits(
                [
                    call("rtx.fallbackLightMode", "0"),
                    call("rtx.fallbackLightRadiance", "0, 0, 0"),
                ]
            )
