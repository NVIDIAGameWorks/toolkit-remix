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

import tempfile

import omni.ui as ui
import omni.usd
from omni.flux.wizard.widget import WizardModel, WizardPage
from omni.flux.wizard.window import WizardWindow
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows


class TestPage(WizardPage):
    """
    Simple Test Page with a payload that accumulates the visit counts
    """

    def __init__(self, title: str):
        super().__init__()

        self.page_title = title

    def create_ui(self):
        with ui.VStack():
            ui.Label(self.page_title, identifier="PageTitle")


class TestWizardWindow(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.context = omni.usd.get_context()
        self.stage = self.context.get_stage()
        self.temp_dir = tempfile.TemporaryDirectory()

    # After running each test
    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()
        self.temp_dir.cleanup()
        self.context = None
        self.stage = None
        self.temp_dir = None

    async def __setup_widget(self, model: WizardModel) -> tuple[ui.Window, WizardWindow]:
        await arrange_windows(topleft_window="Stage")

        window = ui.Window("TestWizardWindow", width=700, height=500)
        with window.frame:
            wizard = WizardWindow(model, title="TextWizardPopup")

        await ui_test.human_delay()

        return window, wizard

    async def test_window_should_show_and_hide(self):
        # Setup the test
        page_1_title = "page_1"
        page_1 = TestPage(page_1_title)

        _, wizard = await self.__setup_widget(WizardModel(page_1))  # Keep in memory during test
        wizard_window = wizard._window

        # Start the test
        wizard.show_wizard(reset_page=True)

        await ui_test.human_delay()

        # Wizard should be visible
        self.assertTrue(wizard_window.visible)

        wizard.hide_wizard()

        await ui_test.human_delay()

        # Wizard should be visible
        self.assertFalse(wizard_window.visible)

    async def test_window_should_hide_on_wizard_completed(self):
        await self.__run_test_window_should_hide("NextButton")

    async def test_window_should_hide_on_wizard_cancelled(self):
        await self.__run_test_window_should_hide("CancelButton")

    async def __run_test_window_should_hide(self, identifier: str):
        # Setup the test
        page_1_title = "page_1"
        page_1 = TestPage(page_1_title)

        _, wizard = await self.__setup_widget(WizardModel(page_1))  # Keep in memory during test
        wizard_window = wizard._window

        # Start the test
        wizard.show_wizard(reset_page=True)

        await ui_test.human_delay()

        self.assertTrue(wizard_window.visible)

        button = ui_test.find(f"{wizard_window.title}//Frame/**/Button[*].identifier=='{identifier}'")

        self.assertIsNotNone(button)

        await button.click()

        await ui_test.human_delay()

        self.assertFalse(wizard_window.visible)
