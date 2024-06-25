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
from enum import Enum
from typing import Tuple
from unittest.mock import Mock, call

import omni.ui as ui
import omni.usd
from omni.flux.wizard.widget import WizardModel, WizardPage, WizardWidget
from omni.kit import ui_test
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, wait_stage_loading

DEFAULT_PREVIOUS_TEXT = "Previous"
DEFAULT_NEXT_TEXT = "Previous"
DEFAULT_DONE_TEXT = "Done"
DEFAULT_CANCEL_TEXT = "Cancel"


class TestComponents(Enum):
    """
    Simple Enum used to find the components of interest during tests
    """

    PAGE_TITLE = 1
    REQUEST_PREVIOUS_BUTTON = 2
    REQUEST_NEXT_BUTTON = 3
    CANCEL_BUTTON = 4
    PREVIOUS_BUTTON = 5
    NEXT_BUTTON = 6


class TestPage(WizardPage):
    """
    Simple Test Page with a payload that accumulates the visit counts
    """

    def __init__(
        self,
        title: str,
        previous_page=None,
        next_page=None,
        previous_text=DEFAULT_PREVIOUS_TEXT,
        next_text=DEFAULT_NEXT_TEXT,
        done_text=DEFAULT_DONE_TEXT,
        hide_navigation=False,
        blocked=False,
    ):
        super().__init__(
            previous_page=previous_page,
            next_page=next_page,
            previous_text=previous_text,
            next_text=next_text,
            done_text=done_text,
            hide_navigation=hide_navigation,
            blocked=blocked,
        )

        self.page_title = title

    def create_ui(self):
        self.payload = {self.page_title: self.payload[self.page_title] + 1 if self.page_title in self.payload else 1}

        with ui.VStack():
            ui.Label(self.page_title, identifier="PageTitle")
            ui.Button("Previous", clicked_fn=self.request_previous, identifier="RequestPrevious")
            ui.Button("Next", clicked_fn=self.request_next, identifier="RequestNext")


class TestWizardWidget(AsyncTestCase):
    # Before running each test
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.context = omni.usd.get_context()
        self.stage = self.context.get_stage()
        self.temp_dir = tempfile.TemporaryDirectory()

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()
        self.temp_dir.cleanup()
        self.context = None
        self.stage = None
        self.temp_dir = None

    async def __setup_widget(self, model: WizardModel) -> Tuple[ui.Window, WizardWidget]:
        await arrange_windows(topleft_window="Stage")

        window = ui.Window("TestWizardWindow", width=700, height=500)
        with window.frame:
            widget = WizardWidget(model)

        await ui_test.human_delay()

        return window, widget

    async def __find_components(self, window):
        return {
            TestComponents.PAGE_TITLE: ui_test.find(f"{window.title}//Frame/**/Label[*].identifier=='PageTitle'"),
            TestComponents.REQUEST_PREVIOUS_BUTTON: ui_test.find(
                f"{window.title}//Frame/**/Button[*].identifier=='RequestPrevious'"
            ),
            TestComponents.REQUEST_NEXT_BUTTON: ui_test.find(
                f"{window.title}//Frame/**/Button[*].identifier=='RequestNext'"
            ),
            TestComponents.CANCEL_BUTTON: ui_test.find(
                f"{window.title}//Frame/**/Button[*].identifier=='CancelButton'"
            ),
            TestComponents.PREVIOUS_BUTTON: ui_test.find(
                f"{window.title}//Frame/**/Button[*].identifier=='PreviousButton'"
            ),
            TestComponents.NEXT_BUTTON: ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='NextButton'"),
        }

    async def test_setup_items_and_navigate_should_build_expected_ui(self):
        # Setup the test
        page_1_title = "page_1"
        page_2_title = "page_2"
        page_3_title = "page_3"

        page_1_next_text = "Test_1"
        page_3_previous_text = "Test_2"
        page_3_done_text = "Test_3"

        page_1 = TestPage(page_1_title, next_text=page_1_next_text, blocked=True)
        page_2 = TestPage(page_2_title, previous_page=page_1, hide_navigation=True)
        page_3 = TestPage(
            page_3_title, previous_page=page_2, previous_text=page_3_previous_text, done_text=page_3_done_text
        )

        page_1.next_page = page_2
        page_2.next_page = page_3

        model = WizardModel(page_1)
        window, _ = await self.__setup_widget(model)  # Keep in memory during test

        await ui_test.human_delay()

        # Start the test
        components = await self.__find_components(window)

        # Should render the item correctly
        self.assertIsNotNone(components[TestComponents.PAGE_TITLE])
        self.assertIsNotNone(components[TestComponents.REQUEST_PREVIOUS_BUTTON])
        self.assertIsNotNone(components[TestComponents.REQUEST_NEXT_BUTTON])
        self.assertEqual(page_1_title, components[TestComponents.PAGE_TITLE].widget.text)

        # Should have a next button
        self.assertIsNotNone(components[TestComponents.NEXT_BUTTON])
        self.assertEqual(page_1_next_text, components[TestComponents.NEXT_BUTTON].widget.text)

        # Should have a cancel button
        self.assertIsNotNone(components[TestComponents.CANCEL_BUTTON])
        self.assertEqual(DEFAULT_CANCEL_TEXT, components[TestComponents.CANCEL_BUTTON].widget.text)

        # Should not have a previous button
        self.assertIsNone(components[TestComponents.PREVIOUS_BUTTON])

        # Clicking the disabled button shouldn't do anything
        await components[TestComponents.NEXT_BUTTON].click()

        await ui_test.human_delay()

        components = await self.__find_components(window)

        # Should still be Page 1's title
        self.assertIsNotNone(components[TestComponents.PAGE_TITLE])
        self.assertEqual(page_1_title, components[TestComponents.PAGE_TITLE].widget.text)

        # Should unlock the next button
        page_1.blocked = False

        # Clicking the enabled button should go to the next page
        await components[TestComponents.NEXT_BUTTON].click()

        await ui_test.human_delay()

        components = await self.__find_components(window)

        # Page content should now be Page 2's
        self.assertIsNotNone(components[TestComponents.PAGE_TITLE])
        self.assertIsNotNone(components[TestComponents.REQUEST_PREVIOUS_BUTTON])
        self.assertIsNotNone(components[TestComponents.REQUEST_NEXT_BUTTON])
        self.assertEqual(page_2_title, components[TestComponents.PAGE_TITLE].widget.text)

        # Navigation should be hidden
        self.assertIsNone(components[TestComponents.CANCEL_BUTTON])
        self.assertIsNone(components[TestComponents.PREVIOUS_BUTTON])
        self.assertIsNone(components[TestComponents.NEXT_BUTTON])

        # Clicking request next button should go next
        await components[TestComponents.REQUEST_NEXT_BUTTON].click()

        await ui_test.human_delay()

        components = await self.__find_components(window)

        # Page content should now be Page 2's
        self.assertIsNotNone(components[TestComponents.PAGE_TITLE])
        self.assertIsNotNone(components[TestComponents.REQUEST_PREVIOUS_BUTTON])
        self.assertIsNotNone(components[TestComponents.REQUEST_NEXT_BUTTON])
        self.assertEqual(page_3_title, components[TestComponents.PAGE_TITLE].widget.text)

        # Should have a next button
        self.assertIsNotNone(components[TestComponents.NEXT_BUTTON])
        self.assertEqual(page_3_done_text, components[TestComponents.NEXT_BUTTON].widget.text)

        # Should have a cancel button
        self.assertIsNotNone(components[TestComponents.CANCEL_BUTTON])
        self.assertEqual(DEFAULT_CANCEL_TEXT, components[TestComponents.CANCEL_BUTTON].widget.text)

        # Should have a previous button
        self.assertIsNotNone(components[TestComponents.PREVIOUS_BUTTON])
        self.assertEqual(page_3_previous_text, components[TestComponents.PREVIOUS_BUTTON].widget.text)

        # Clicking previous button should go back
        await components[TestComponents.PREVIOUS_BUTTON].click()

        await ui_test.human_delay()

        components = await self.__find_components(window)

        # Page content should now be Page 2's
        self.assertIsNotNone(components[TestComponents.PAGE_TITLE])
        self.assertEqual(page_2_title, components[TestComponents.PAGE_TITLE].widget.text)

        # Clicking request previous button should go back
        await components[TestComponents.REQUEST_PREVIOUS_BUTTON].click()

        await ui_test.human_delay()

        components = await self.__find_components(window)

        # Page content should now be Page 2's
        self.assertIsNotNone(components[TestComponents.PAGE_TITLE])
        self.assertEqual(page_1_title, components[TestComponents.PAGE_TITLE].widget.text)

    async def test_click_next_no_next_item_should_complete_and_pass_payload(self):
        # Setup the test
        page = TestPage("page_1")

        model = WizardModel(page)
        window, wizard = await self.__setup_widget(model)  # Keep in memory during test

        on_wizard_complete = Mock()
        _ = wizard.subscribe_wizard_completed(on_wizard_complete)

        await ui_test.human_delay()

        # Start the test
        components = await self.__find_components(window)

        # Should have a next button
        self.assertIsNotNone(components[TestComponents.NEXT_BUTTON])

        # Go next
        await components[TestComponents.NEXT_BUTTON].click()

        await ui_test.human_delay()

        # Callback should have been called
        self.assertEqual(1, on_wizard_complete.call_count)
        self.assertEqual(call(page.payload), on_wizard_complete.call_args)

    async def test_click_next_on_complete_should_accumulate_payloads(self):
        # Setup the test
        page_1_title = "page_1"
        page_2_title = "page_2"
        page_3_title = "page_3"

        page_1 = TestPage(page_1_title)
        page_2 = TestPage(page_2_title, previous_page=page_1)
        page_3 = TestPage(page_3_title, previous_page=page_2)

        page_1.next_page = page_2
        page_2.next_page = page_3

        model = WizardModel(page_1)
        window, wizard = await self.__setup_widget(model)  # Keep in memory during test

        on_wizard_complete = Mock()
        _ = wizard.subscribe_wizard_completed(on_wizard_complete)

        await ui_test.human_delay()

        # Start the test, Page 1
        components = await self.__find_components(window)

        # Should have a next button
        self.assertIsNotNone(components[TestComponents.NEXT_BUTTON])

        # Go next
        await components[TestComponents.NEXT_BUTTON].click()

        await ui_test.human_delay()

        # Page 2
        components = await self.__find_components(window)

        # Should have a next button
        self.assertIsNotNone(components[TestComponents.NEXT_BUTTON])

        # Go next
        await components[TestComponents.NEXT_BUTTON].click()

        await ui_test.human_delay()

        # Page 3
        components = await self.__find_components(window)

        # Should have a previous button
        self.assertIsNotNone(components[TestComponents.PREVIOUS_BUTTON])

        # Go next
        await components[TestComponents.PREVIOUS_BUTTON].click()

        await ui_test.human_delay()

        # Page 2 (Again)
        components = await self.__find_components(window)

        # Should have a next button
        self.assertIsNotNone(components[TestComponents.NEXT_BUTTON])

        # Go next
        await components[TestComponents.NEXT_BUTTON].click()

        await ui_test.human_delay()

        # Page 3 (Again, but complete this time)
        components = await self.__find_components(window)

        # Should have a next button
        self.assertIsNotNone(components[TestComponents.NEXT_BUTTON])

        # Go next
        await components[TestComponents.NEXT_BUTTON].click()

        await ui_test.human_delay()

        # Callback should have been called
        self.assertEqual(1, on_wizard_complete.call_count)

        args, _ = on_wizard_complete.call_args
        self.assertEqual(str({page_1_title: 1, page_2_title: 2, page_3_title: 2}), str(args[0]))
