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

import omni.ui as ui
from omni.flux.validator.mass.queue.widget import MassQueueTreeWidget as _MassQueueTreeWidget
from omni.flux.validator.mass.queue.widget.service import get_service_instance as _get_service_instance
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows


class TestManagerWidget(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await arrange_windows()

    # After running each test
    async def tearDown(self):
        pass

    async def __setup_widget(self, name):
        window = ui.Window(f"TestValidationQueueUI{name}", height=800, width=400)
        with window.frame:
            wid = _MassQueueTreeWidget()

        await ui_test.human_delay(human_delay_speed=1)

        return window, wid

    async def __destroy_setup(self, window, wid):
        await ui_test.human_delay(human_delay_speed=1)
        wid.destroy()
        window.frame.clear()
        window.destroy()
        #
        await ui_test.human_delay(human_delay_speed=1)

    async def test_can_create_widget(self):
        window, wid = await self.__setup_widget("test_can_create_widget")

        await ui_test.human_delay()

        await self.__destroy_setup(window, wid)

    async def test_service_is_running(self):
        service = _get_service_instance()

        self.assertIsNotNone(service)
